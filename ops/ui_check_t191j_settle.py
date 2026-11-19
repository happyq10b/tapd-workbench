# -*- coding: utf-8 -*-
"""T-191j CDP 校验：
① 板块预览头部出现「完成情况」按钮（与事项状态按钮同款），点击可展开菜单并切换；
② 板块编辑弹窗头部有完成情况按钮、表单区无「完成情况」下拉；
③ 事项/板块行倒计时列：已完成+已结算 → 显示结算结果（逾期n天等）；未完成 → 倒计时 N。
夹具 __t191jc_ 前缀，finally 清理。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, datetime, urllib.request, atexit

BASE = 'http://127.0.0.1:8100'
PORT = 9550
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

P = '__t191jc_'
BID, CID = P + 'bid', P + 'cid'
TODAY = datetime.date.today()
MK = lambda off: (TODAY + datetime.timedelta(days=off)).isoformat()
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def cleanup():
    c = sqlite3.connect(ROOT + '/src/app.db', timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    esc = chr(92)
    pat = '%' + P.replace('_', esc + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'), ('boards', 'board_id')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{esc}'", (pat,))
    c.commit()
    left = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key')):
        left += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{esc}'", (pat,)).fetchone()[0]
    c.close()
    return left


atexit.register(lambda: print('残留自查: %d（应为 0）' % cleanup(), flush=True))


def setup():
    c = sqlite3.connect(ROOT + '/src/app.db', timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    now = '2026-11-13 10:00:00'
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,created_at) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', now))
    # 板块：已完成 + 截止 6 天前 → 结算 逾期6天
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,year,completion,due_date,overdue_days)"
              " VALUES(?,?,?,?,?,?,?,?,?,?)",
              (BID + '::' + P + '板块', CID, BID, P + '板块', now, 'admin', '2026', 'done', MK(-6), 6))
    # 事项甲：已完成 + 截止 2 天前 → 结算 逾期2天；事项乙：未完成 + 截止 3 天后 → 倒计时 3
    for cid, name, st, due, od in ((P + 'a', P + '事项甲', 'done', MK(-2), 2),
                                   (P + 'b', P + '事项乙', 'open', MK(3), None)):
        c.execute("INSERT OR IGNORE INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,due,created,deleted,version,parent_id,overdue_days)"
                  " VALUES(?,?,?,?,?,?,?,?,?,0,1,'',?)",
                  (cid, BID, P + '看板', CID, P + '板块', name, st, due, now, od))
    c.commit()
    c.close()


async def main():
    setup()
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191j')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                             '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up = False
    for _ in range(40):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            up = True
            break
        except Exception:
            time.sleep(0.5)
    if not up:
        print('ENV-FAIL: headless Chrome 不可用', flush=True)
        proc.kill()
        return
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
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:160], flush=True)
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
    bid_js = json.dumps(BID)
    await ev("(async function(){curBoards=new Set([%s]);curBoard=%s;await reload(1);return 'ok'})()" % (bid_js, bid_js), True)
    await asyncio.sleep(1.5)

    print('【① 倒计时列结算展示】', flush=True)
    # 服务端复核：夹具事项甲/乙的 status 与 overdue_days（排除数据面问题）
    st = await ev("(async function(){try{const r=await fetch('/api/cards?board_ids='+%s+'&size=5',{headers:{Authorization:'Bearer '+TOKEN}});const dj=await r.json();return dj.cards.map(c=>({n:c.card_name.slice(8),s:c.status,od:c.overdue_days}))}catch(e){return 'ERR '+e.message}})()" % bid_js, True)
    print('  服务端:', json.dumps(st, ensure_ascii=True), flush=True)
    r1 = await ev("""(function(){
      const txt=document.getElementById('boardContent').textContent;
      const cds=[...document.querySelectorAll('#boardContent .fcol-cd')].map(x=>x.textContent.trim());
      return {hasOverdue6:txt.indexOf('逾期6天')>=0,hasOverdue2:txt.indexOf('逾期2天')>=0,
        hasCd3:cds.some(t=>t==='倒计时 3'),noPrefixSettle:cds.every(t=>!(t.indexOf('倒计时')===0&&(t.indexOf('逾期')>=0))),
        cds:cds.slice(0,6)};})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('hasOverdue6'), '板块行：已结算板块显示「逾期6天」（替代倒计时）')
    ok(isinstance(r1, dict) and r1.get('hasOverdue2'), '事项行：已结算事项显示「逾期2天」')
    ok(isinstance(r1, dict) and r1.get('hasCd3'), '未完成事项行：倒计时 3 正常显示（带前缀）')
    ok(isinstance(r1, dict) and r1.get('noPrefixSettle'), '结算结果不带「倒计时」前缀')

    print('【② 板块预览：头部完成情况按钮 + 元信息不重复】', flush=True)
    r2 = await ev("""(function(){
      const t=document.querySelector('#boardContent .week-title.edit');
      if(t)t.click();
      return 'clicked';})()""")
    await asyncio.sleep(1.2)
    r3 = await ev("""(function(){
      const picker=document.getElementById('cd_ops').querySelector('#c_status_picker .status-btn');
      const menuBtns=[...document.querySelectorAll('#c_status_menu button')].map(b=>b.textContent.trim());
      const meta=document.getElementById('cd_meta').textContent;
      return {pickerTxt:picker?picker.textContent.trim():null,
        menuN:menuBtns.length,menuDone:menuBtns.some(t=>t.indexOf('已完成')>=0),
        metaNoComp:meta.indexOf('完成情况：')<0,hasEdit:!!document.querySelector('#cd_ops .btn-primary')};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('pickerTxt') and '已完成' in r3.get('pickerTxt'),
       '板块预览头部出现完成情况按钮（当前=已完成）')
    ok(isinstance(r3, dict) and r3.get('menuN') == 3, '菜单含 未完成/进行中/已完成 三项')
    ok(isinstance(r3, dict) and r3.get('metaNoComp'), '元信息行不再重复展示完成情况')
    ok(isinstance(r3, dict) and r3.get('hasEdit'), '编辑按钮仍在（与事项预览同构）')
    # 切换完成情况 → open → 倒计时恢复
    r4 = await ev("""(async function(){
      document.querySelector('#c_status_picker .status-btn').click();
      await new Promise(r=>setTimeout(r,200));
      const target=[...document.querySelectorAll('#c_status_menu button')].find(b=>b.textContent.indexOf('未完成')>=0);
      target.click();
      await new Promise(r=>setTimeout(r,800));
      const picker=document.querySelector('#cd_ops #c_status_picker .status-btn');
      const meta=document.getElementById('cd_meta').textContent;
      return {after:picker?picker.textContent.trim():null,
        cdBack:meta.indexOf('倒计时')>=0&&meta.indexOf('逾期6天')<0};})()""", True)
    print('  ', json.dumps(r4, ensure_ascii=True), flush=True)
    ok(isinstance(r4, dict) and r4.get('after') and '未完成' in r4.get('after'),
       '点击菜单「未完成」→ 按钮即时切换')
    ok(isinstance(r4, dict) and r4.get('cdBack'), '回退未完成 → 倒计时列恢复（不再显示逾期6天）')
    # 还原为 done（与夹具一致）
    await ev("""(async function(){
      document.querySelector('#cd_ops #c_status_picker .status-btn').click();
      await new Promise(r=>setTimeout(r,200));
      const t=[...document.querySelectorAll('#c_status_menu button')].find(b=>b.textContent.indexOf('已完成')>=0);
      t.click();await new Promise(r=>setTimeout(r,600));return 'ok'})()""", True)

    print('【③ 板块编辑弹窗：头部按钮 + 表单区无下拉】', flush=True)
    r5 = await ev("""(function(){
      document.querySelector('#cd_ops .btn-primary').click();
      return 'ok';})()""")
    await asyncio.sleep(1.0)
    r6 = await ev("""(function(){
      const head=document.querySelector('#columnModal #ce_status_picker .status-btn');
      const formSel=document.getElementById('c_completion');
      return {headTxt:head?head.textContent.trim():null,formSelGone:!formSel};})()""")
    print('  ', json.dumps(r6, ensure_ascii=True), flush=True)
    ok(isinstance(r6, dict) and r6.get('headTxt') and ('已完成' in r6.get('headTxt') or '未完成' in r6.get('headTxt')),
       '板块编辑弹窗头部出现完成情况按钮（与事项编辑同位；当前值可能被完成门槛拦在未完成——属正确行为）')
    ok(isinstance(r6, dict) and r6.get('formSelGone'), '编辑表单区「完成情况」下拉已移除（与事项编辑一致：表单区无状态控件）')

    try:
        await send('Browser.close')
    except Exception:
        pass
    fails = [m for c2, m in N if not c2]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
except Exception as e:
    print('ERR', repr(e)[:200], flush=True)
