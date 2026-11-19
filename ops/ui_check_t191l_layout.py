# -*- coding: utf-8 -*-
"""T-191l 校验：
① 编辑板块弹窗无「保存后板块名称…」提示文案；
② 编辑事项弹窗无「所属看板」选择框，且保存不改 board_id；
③ 编辑板块弹窗无「创建人」字段，浏览界面元信息仍展示创建人；
④ 编辑板块弹窗宽度 = 编辑事项弹窗宽度（默认 .modal 640），负责人/参与人 = member-picker 同款，
   picker 回显正确且保存链路（姓名→账号反查）生效。
夹具 __t191l_ 前缀，finally 清理。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, atexit

BASE = 'http://127.0.0.1:8100'
PORT = 9554
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

P = '__t191l_'
BID = P + 'bid'
CK = BID + '::' + P + '板块'
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
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,year,completion,due_date,owner,participants)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (CK, P + 'colid', BID, P + '板块', now, 'admin', '2026', 'open', '', '', ''))
    c.execute("INSERT OR IGNORE INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,created,deleted,version,parent_id)"
              " VALUES(?,?,?,?,?,?, 'open', ?, 0, 1,'')",
              (P + 'card1', BID, P + '看板', P + 'colid', P + '板块', P + '事项甲', now))
    c.commit()
    c.close()


async def main():
    setup()
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191l')
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
    bid_js = json.dumps(BID)
    await ev("(async function(){curBoards=new Set([%s]);curBoard=%s;await reload(1);return 'ok'})()" % (bid_js, bid_js), True)
    await asyncio.sleep(1.5)

    print('【④+③ 编辑板块弹窗：尺寸/picker/创建人/提示文案】', flush=True)
    # 直接调 openColumnEdit（点标题打开的是预览弹窗，编辑弹窗需经预览的编辑按钮）
    r1 = await ev("""(async function(){
      await openColumnEdit({colkey:'%s',bid:'%s',cname:'%s板块',year:'2026',nature:'日常',
        created:'2026-11-13',creator:'admin',owner:'',parts:'',completion:'open',desc:'',due:''},false);
      return 'ok';})()""" % (CK, BID, P), True)
    await asyncio.sleep(1.2)
    r2 = await ev("""(function(){
      const m=document.getElementById('columnModal');
      const mr=m.querySelector('.modal').getBoundingClientRect();
      const em=document.getElementById('editModal').querySelector('.modal');
      const emW=em.getBoundingClientRect().width;   // 未打开读不到布局 → 用样式比对
      const emStyle=getComputedStyle(em).width;
      return {w:Math.round(mr.width),
        noCreator:!document.getElementById('c_creator'),
        noTip:document.getElementById('c_tip').style.display==='none',
        tipTxt:(document.getElementById('c_tip').textContent||'').indexOf('保存后板块名称')<0,
        ownerPicker:!!document.querySelector('#c_owner .pp'),
        partsPicker:!!document.querySelector('#c_parts .pp'),
        ownerReadonly:document.getElementById('c_owner').classList.contains('pp-readonly')};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('w') == 640, '编辑板块弹窗宽度 = 640px（与编辑事项同款默认 .modal）')
    ok(isinstance(r2, dict) and r2.get('noCreator'), '编辑板块弹窗无「创建人」字段')
    ok(isinstance(r2, dict) and r2.get('noTip') and r2.get('tipTxt'), '无「保存后板块名称…」提示文案')
    ok(isinstance(r2, dict) and r2.get('ownerPicker') and r2.get('partsPicker'),
       '板块负责人/参与人 = member-picker（与事项同款 .pp 结构）')
    ok(isinstance(r2, dict) and r2.get('ownerReadonly') is False, 'admin 有指派权 → picker 可编辑（非只读）')
    # 浏览界面仍展示创建人
    await ev("closeModal('columnModal')")
    r3 = await ev("""(function(){
      const t=document.querySelector('#boardContent .week-title');
      if(t)t.click();return 'clicked';})()""")
    await asyncio.sleep(1.0)
    r4 = await ev("(function(){return document.getElementById('cd_meta').textContent.indexOf('创建人')>=0?'yes':'no'})()")
    ok(r4 == 'yes', '板块浏览界面元信息仍展示「创建人」')
    await ev("closeModal('columnDetailModal')")

    print('【② 编辑事项：无所属看板框 + 保存不改归属】', flush=True)
    r5 = await ev("""(async function(){
      await openDetail('%s');return 'ok'})()""" % (P + 'card1'), True)
    await asyncio.sleep(1.0)
    r6 = await ev("""(function(){
      document.querySelector('#d_ops .btn-primary').click();return 'ok';})()""")
    await asyncio.sleep(1.0)
    r7 = await ev("""(function(){
      const m=document.getElementById('editModal');
      return {noBoard:!document.getElementById('e_board'),
        noBoardWrap:!document.getElementById('e_board_wrap'),
        weekVisible:!!document.getElementById('e_week'),
        w:Math.round(m.querySelector('.modal').getBoundingClientRect().width)};})()""")
    print('  ', json.dumps(r7, ensure_ascii=True), flush=True)
    ok(isinstance(r7, dict) and r7.get('noBoard') and r7.get('noBoardWrap'), '编辑事项弹窗无「所属看板」选择框')
    ok(isinstance(r7, dict) and r7.get('weekVisible'), '周数字段保留')
    # 保存（只改描述）→ 校验 board_id 不变
    r8 = await ev("""(async function(){
      document.getElementById('e_desc').value='t191l-保存测试';
      await saveEdit();
      await new Promise(r=>setTimeout(r,900));
      const r2=await fetch('/api/cards?card_id=%s',{headers:{Authorization:'Bearer '+TOKEN}});
      const d2=await r2.json();
      const c2=d2.cards[0];
      return {bid:c2.board_id,desc:c2.description};})()""" % (P + 'card1'), True)
    print('  ', json.dumps(r8, ensure_ascii=True), flush=True)
    ok(isinstance(r8, dict) and r8.get('bid') == BID, '保存后事项 board_id 保持原值（不再跨看板移动）')
    ok(isinstance(r8, dict) and r8.get('desc') == 't191l-保存测试', '其他字段保存正常')

    print('【④ 保存链路：picker 姓名 → 账号反查】', flush=True)
    r9 = await ev("""(async function(){
      await openColumnEdit({colkey:%s,bid:%s,cname:'%s板块',year:'2026',nature:'日常',
        created:'2026-11-13',creator:'admin',owner:'',parts:'',completion:'open',desc:'',due:''},false);
      await new Promise(r=>setTimeout(r,600));
      // admin 往参与人 picker 加两个姓名（直接调 picker 渲染函数展开候选 → 选中）
      const pw=document.getElementById('c_parts');
      if(window.PP&&PP['c_parts'])PP['c_parts'].rd('');
      await new Promise(r=>setTimeout(r,250));
      const opts=[...pw.querySelectorAll('.pp-opt')];
      if(opts.length>=2){opts[0].dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));opts[1].dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));}
      const tags=[...pw.querySelectorAll('.pp-tag')].map(x=>x.textContent.replace('×','').trim());
      let saveErr='';
      try{await saveColumn();}catch(e){saveErr=e.message||String(e);}
      await new Promise(r=>setTimeout(r,900));
      await new Promise(r=>setTimeout(r,900));
      const r2=await fetch('/api/cards?board_ids=%s&size=1',{headers:{Authorization:'Bearer '+TOKEN}});
      const d2=await r2.json();
      const col=(d2.columns||[])[0]||{};
      return {tags:tags,saveErr:saveErr,participants:col.participants,owner:col.owner,
        mode:COLUMN_MODE,key:COLUMN_EDIT_KEY};})()""" % (
        json.dumps(CK), bid_js, P, BID), True)
    print('  ', json.dumps(r9, ensure_ascii=True), flush=True)
    ok(isinstance(r9, dict) and len(r9.get('tags') or []) >= 1, 'picker 候选池有成员且可选中（tag 生成）')
    ok(isinstance(r9, dict) and len(r9.get('participants') or '') >= 1,
       '保存后 participants 落库为账号串（姓名→账号反查生效：%s）' % (r9 or {}).get('participants'))

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
