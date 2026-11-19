# -*- coding: utf-8 -*-
"""T-196 CDP 校验：分类快速勾选（负责事项/参与事项）。

夹具：1 看板 1 板块（col owner 不设——admin 走 can_edit 恒有权）+ 4 事项：
  甲 owner=admin            → 负责
  乙 owner=张三  cc=admin    → 参与
  丙 owner=张三  cc=李四     → 两类都不命中（全选对比用）
  丁 owner=admin  cc=admin   → 两类都命中
步骤：启用勾选 → 三钮可见且描边配色互异 → 负责事项勾甲丁（2）→ 再点取消 →
      参与事项勾乙丁（2）→ 再点取消 → 全选当前 4 个+板块 → 取消全选 →
      交互组合：全选后再点负责事项 → 仅取消甲丁、乙丙保留。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9549
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

N = []
P = '__t196_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def setup():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT INTO boards(board_id,board_name,owner) VALUES(?,?,?)",
              (BID, P + '看板', 'admin'))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,year,completion) VALUES(?,?,?,?,?,?,?,?,?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-13', 'admin', '日常', '2026', 'open'))
    rows = [
        (P + 'a', P + '事项甲', 'admin', ''),
        (P + 'b', P + '事项乙', '张三', 'admin'),
        (P + 'c', P + '事项丙', '张三', '李四'),
        (P + 'd', P + '事项丁', 'admin', 'admin'),
    ]
    for cid, name, owner, cc in rows:
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,"
                  "status,owner,cc,created,deleted,parent_id) "
                  "VALUES(?,?,?,?,?,?,'open',?,?,?,0,'')",
                  (cid, BID, P + '看板', P + 'cid', P + '板块', name, owner, cc, '2026-11-13'))
    c.commit(); c.close()


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t196')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending, seq = {}, [0]

    async def send(m, p=None):
        seq[0] += 1
        fut = asyncio.get_event_loop().create_future()
        pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:200])
            return {'__err__': True}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    # 进入夹具看板
    await ev("""(async function(){curBoards=new Set(['%s']);curBoard='%s';await reload(1);return 'ok'})()"""
             % (BID, BID), True)
    await asyncio.sleep(1.5)

    print('【① 勾选模式默认关闭；启用后三钮可见且样式一致】', flush=True)
    pre = await ev("""(function(){
      return {mode:typeof CHK_MODE!=='undefined'?CHK_MODE:null,
        btnTxt:document.getElementById('chkModeBtn').textContent};})()""")
    print('  pre:', json.dumps(pre, ensure_ascii=True), flush=True)
    ok(isinstance(pre, dict) and pre.get('mode') is False and pre.get('btnTxt') == '启用勾选',
       '#201：页面加载后勾选模式默认关闭（按钮=「启用勾选」）')
    r1 = await ev("""(async function(){
      toggleChkMode();
      await new Promise(r=>setTimeout(r,1200));
      const g=id=>document.getElementById(id);
      const all=g('chkAllBtn'),ow=g('chkMineOwnerBtn'),cc=g('chkMineCcBtn');
      const st=e=>{const c=getComputedStyle(e);return c.color+'/'+c.borderColor;};
      return {vis:all.style.display!=='none'&&ow.style.display!=='none'&&cc.style.display!=='none',
        allC:st(all), owC:st(ow), ccC:st(cc),
        txt:[all.textContent,ow.textContent,cc.textContent]};})()""", True)
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('vis'), '勾选模式启用后【全选当前】【负责事项】【参与事项】全部可见')
    ok(isinstance(r1, dict) and r1.get('txt') == ['全选当前', '负责事项', '参与事项'], '按钮文案正确')
    ok(isinstance(r1, dict) and r1.get('allC') == r1.get('owC') == r1.get('ccC'),
       '#201：三钮样式完全一致（复刻【全选当前】蓝描边形态）')
    ok(isinstance(r1, dict) and r1.get('owC') == 'rgb(0, 45, 116)/rgb(0, 45, 116)',
       '负责/参与事项配色 = 品牌蓝（与全选当前相同）')

    await asyncio.sleep(0.8)
    print('【② 负责事项 → 勾选甲、丁（2 个）】', flush=True)
    r2 = await ev("""(function(){
      selectCategoryCards('owner');
      const on=[...document.querySelectorAll('.item-chk:checked')].map(x=>x.dataset.ck);
      const col=document.querySelector('.col-chk');
      return {n:on.length,on:on,colChecked:col?col.checked:null,colInd:col?col.indeterminate:null};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('n') == 2
       and (P + 'a') in (r2.get('on') or []) and (P + 'd') in (r2.get('on') or []),
       '负责事项 → 甲、丁被勾选（owner 含 admin）')
    ok(isinstance(r2, dict) and r2.get('colChecked') is False,
       '板块不随勾（仅 2/4 事项被勾，板块联动需全部勾选）')

    print('【③ 再点负责事项 → 取消该类】', flush=True)
    r3 = await ev("""(function(){
      selectCategoryCards('owner');
      return {n:document.querySelectorAll('.item-chk:checked').length};})()""")
    ok(isinstance(r3, dict) and r3.get('n') == 0, '再点负责事项 → 该类勾选全部取消')

    await asyncio.sleep(0.5)
    print('【④ 参与事项 → 勾选乙、丁（2 个）】', flush=True)
    r4 = await ev("""(function(){
      selectCategoryCards('cc');
      const on=[...document.querySelectorAll('.item-chk:checked')].map(x=>x.dataset.ck);
      return {n:on.length,on:on};})()""")
    print('  ', json.dumps(r4, ensure_ascii=True), flush=True)
    ok(isinstance(r4, dict) and r4.get('n') == 2
       and (P + 'b') in (r4.get('on') or []) and (P + 'd') in (r4.get('on') or []),
       '参与事项 → 乙、丁被勾选（cc 含 admin）')

    print('【⑤ 再点参与事项 → 取消；全选当前 → 4 个全勾+板块随勾】', flush=True)
    r5 = await ev("""(function(){
      selectCategoryCards('cc');
      const zero=document.querySelectorAll('.item-chk:checked').length;
      selectAllCurrent();
      const on=[...document.querySelectorAll('.item-chk:checked')].map(x=>x.dataset.ck);
      const col=document.querySelector('.col-chk');
      return {zero:zero,n:on.length,colChecked:col?col.checked:null};})()""")
    ok(isinstance(r5, dict) and r5.get('zero') == 0, '参与事项二次点击 → 取消')
    ok(isinstance(r5, dict) and r5.get('n') == 4 and r5.get('colChecked') is True,
       '全选当前 → 4 个事项全勾且板块随勾（既有功能不受影响）')

    await asyncio.sleep(0.5)
    print('【⑥ 交互组合：全选后再点负责事项 → 仅取消甲丁，乙丙保留】', flush=True)
    r6 = await ev("""(function(){
      selectCategoryCards('owner');
      const on=[...document.querySelectorAll('.item-chk:checked')].map(x=>x.dataset.ck);
      const col=document.querySelector('.col-chk');
      return {n:on.length,on:on,colInd:col?col.indeterminate:null,colChecked:col?col.checked:null};})()""")
    print('  ', json.dumps(r6, ensure_ascii=True), flush=True)
    ok(isinstance(r6, dict) and r6.get('n') == 2
       and (P + 'b') in (r6.get('on') or []) and (P + 'c') in (r6.get('on') or []),
       '全选态下点负责事项 → 仅甲丁取消，乙丙保留')
    ok(isinstance(r6, dict) and r6.get('colChecked') is False,
       '板块不误勾（部分事项被勾时板块保持未勾，对齐既有聚合语义）')

    print('【⑦ 收尾还原】', flush=True)
    r7 = await ev("""(function(){
      toggleChkMode();   // 关闭勾选并清空记录
      const hidden=document.getElementById('chkMineOwnerBtn').style.display==='none'
        &&document.getElementById('chkMineCcBtn').style.display==='none'
        &&document.getElementById('chkAllBtn').style.display==='none';
      return {hidden:hidden,mode:CHK_MODE};})()""")
    ok(isinstance(r7, dict) and r7.get('hidden') and r7.get('mode') is False,
       '关闭勾选模式 → 三钮隐藏、勾选记录清空')

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    setup()
    asyncio.run(main())
finally:
    left = cleanup()
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
    for m in fails:
        print('  FAIL:', m)
    if fails or left:
        sys.exit(1)
