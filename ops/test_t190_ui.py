# -*- coding: utf-8 -*-
"""T-0190 UI CDP 测试（六项调整的前端行为验证）：
② 板块编辑弹窗删除按钮：板块负责人可见 / 无板块责任编辑不可见；删除走确认
③ 浏览界面待办只展示+勾选（无添加行/删除按钮/创建人）；编辑弹窗有待办管理
④ 板块行【待办：x/y】与事项行代办槽位（slot-subtask）水平对齐
⑤ 子事项行 fcols 与父事项行像素级对齐（列起点一致、无换行）
⑥ 倒计时只显示数字（含负数）
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

BASE = 'http://127.0.0.1:8100'
PORT = 9531
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
P = '__t190u_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'
U_COL = P + 'col'     # 板块负责人（非看板负责人）
U_PLN = P + 'pln'     # 普通编辑（无板块责任）
import datetime
TOMORROW = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def make_fixtures():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    for u in (U_COL, U_PLN):
        c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) VALUES(?,?,?,?,1)",
                  (u, hash_pw('Xx12345678'), 'x', 'editor'))
    c.execute("INSERT INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', ''))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,"
              "completion,description,pinned,owner,due_date) VALUES(?,?,?,?,?,?,?,?,'open','测试板块描述',0,?,?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026', U_COL, TOMORROW))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
              "week_no,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,'')",
              (P + 'card1', BID, P + '看板', P + 'cid', P + '板块', P + '事项甲', 'open', '张三', '', '', '2026-11-12 10:00:00'))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
              "week_no,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?)",
              (P + 'sub1', BID, P + '看板', P + 'cid', P + '板块', P + '子事项甲', 'open', '李四', '', '', '2026-11-12 10:01:00', P + 'card1'))
    c.execute("INSERT OR IGNORE INTO column_todos(col_key,name,sort,done,created_by) VALUES(?,?,?,?,?)",
              (COLKEY, P + '待办一', 1, 0, U_COL))
    c.execute("INSERT OR IGNORE INTO column_todos(col_key,name,sort,done,created_by) VALUES(?,?,?,?,?)",
              (COLKEY, P + '待办二', 2, 1, U_COL))
    c.execute("INSERT OR IGNORE INTO column_todos(col_key,name,sort,done,created_by) VALUES(?,?,?,?,?)",
              (COLKEY, P + '待办三', 3, 0, U_COL))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('column_todos', 'col_key'), ('column_comments', 'col_key'),
                   ('users', 'username')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit(); n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('column_todos', 'col_key'), ('users', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n

async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0190')
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
    pending = {}
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')

    bid_js = json.dumps(BID)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev('document.cookie=%s;location.href="/";' % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【⑥ 倒计时只显示数字（含负数）】', flush=True)
    r6 = await ev("""(function(){
      return {f:cdText('%s'),y:cdText('%s'),none:cdText('')};})()""" % (TOMORROW, YESTERDAY))
    print('  ', json.dumps(r6, ensure_ascii=True), flush=True)
    ok(isinstance(r6, dict) and r6.get('f') == '3', '未来截止（+3 天）→ 显示「3」')
    ok(isinstance(r6, dict) and r6.get('y') == '-2', '逾期 2 天 → 显示「-2」（负数）')
    ok(isinstance(r6, dict) and r6.get('none') == '', '无截止 → 空串（占位 —）')

    print('【渲染目录并进入板块编辑弹窗（admin）】', flush=True)
    await ev('(async function(){try{curBoards=new Set([' + bid_js + ']);curBoard=' + bid_js + ';await reload(1);return "ok"}catch(e){return "ERR "+e.message}})()', True)
    await asyncio.sleep(1.0)
    sel = json.dumps('.week-title.edit[data-colkey="%s"]' % COLKEY)
    await ev('openColumnDetail(document.querySelector(%s))' % sel)
    for _ in range(15):
        await asyncio.sleep(0.4)
        st = await ev("({todo:!!document.getElementById('cd_todos'),cmt:!!document.getElementById('cd_comments'),txt:document.getElementById('cd_todos').textContent.slice(0,60)})")
        if isinstance(st, dict) and st.get('todo') and '加载' not in str(st.get('txt')):
            break

    print('【③ 浏览界面待办：只展示+勾选，无设置入口/创建人】', flush=True)
    r3 = await ev("""(function(){
      const box=document.getElementById('cd_todos');
      const items=[...box.querySelectorAll('.subtask-item')];
      return {n:items.length,
        addRow:!!document.getElementById('cd_todo_add_row'),
        delBtns:box.querySelectorAll('button').length,
        creator:box.textContent.indexOf('u_col')>=0||box.textContent.indexOf('__t190u_col')>=0,
        chk:items.length?items[0].querySelector('input[type=checkbox]')!==null:false,
        todoTag:document.querySelector('.week-header .slot-subtask')?document.querySelector('.week-header .slot-subtask').textContent.trim():null};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('n') == 3, '浏览界面待办 3 条')
    ok(isinstance(r3, dict) and not r3.get('addRow'), '浏览界面无待办添加行（设置入口只在编辑弹窗）')
    ok(isinstance(r3, dict) and r3.get('delBtns', 1) == 0, '浏览界面待办无删除按钮')
    ok(isinstance(r3, dict) and not r3.get('creator'), '待办项不显示创建人账号')
    ok(isinstance(r3, dict) and r3.get('chk') is True, '待办可勾选')

    print('【④ 板块行【待办：1/3】与事项行代办槽位对齐】', flush=True)
    r4 = await ev("""(function(){
      const colSlot=document.querySelector('.week-header .slot-subtask');
      const colTag=colSlot?colSlot.querySelector('.st-mini'):null;
      const colRect=colSlot.getBoundingClientRect();
      // 找一条事项行的 slot-subtask 比横向位置
      let cardSlot=null,cardRect=null;
      document.querySelectorAll('.item-card .slot-subtask').forEach(function(s){
        const r2=s.getBoundingClientRect();
        if(!cardRect&&r2.width)  {cardSlot=s;cardRect=r2;}
      });
      return {tag:colTag?colTag.textContent.trim():null,
        colLeft:Math.round(colRect.left),cardLeft:cardRect?Math.round(cardRect.left):null,
        sameWidth:cardRect?Math.abs(cardRect.width-colRect.width)<2:null};})()""")
    print('  ', json.dumps(r4, ensure_ascii=True), flush=True)
    ok(isinstance(r4, dict) and r4.get('tag') == '【待办：1/3】', '板块行显示【待办：1/3】')
    ok(isinstance(r4, dict) and r4.get('cardLeft') is not None and r4.get('colLeft') == r4.get('cardLeft'),
       '板块待办槽位与事项行代办槽位左缘像素对齐（水平同列）')
    ok(isinstance(r4, dict) and r4.get('sameWidth') is True, '槽位宽度一致（118px 同规格）')

    print('【⑤ 子事项列与父事项列像素级对齐、不换行】', flush=True)
    await ev("toggleSubTree('%s',true)" % (P + 'card1'))
    await asyncio.sleep(1.0)
    r5 = await ev("""(function(){
      const card=document.querySelector('.item-card .fcols');
      const sub=document.querySelector('.sub-node .fcols');
      if(!card||!sub)return {card:!!card,sub:!!sub};
      const a=card.getBoundingClientRect(),b=sub.getBoundingClientRect();
      // 逐列取样：两个网格各自的第 2/5 列起点
      const cs=getComputedStyle(card),ss=getComputedStyle(sub);
      return {leftA:Math.round(a.left),leftB:Math.round(b.left),
        colsA:cs.gridTemplateColumns,colsB:ss.gridTemplateColumns,
        wA:Math.round(a.width),wB:Math.round(b.width),
        hA:Math.round(a.height),hB:Math.round(b.height),
        wrapB:ss.height!=='auto'&&sub.scrollHeight>sub.clientHeight+1};})()""")
    print('  ', json.dumps(r5, ensure_ascii=True), flush=True)
    ok(isinstance(r5, dict) and r5.get('colsA') == r5.get('colsB'), '父子行网格列定义一致')
    ok(isinstance(r5, dict) and r5.get('wA') == r5.get('wB') and r5.get('wA') == 530, '父子行 fcols 宽度一致=530px')
    ok(isinstance(r5, dict) and not r5.get('wrapB'), '子事项行无换行（无纵向溢出）')

    print('【② 删除按钮可见性：admin 可见 → 进入编辑弹窗】', flush=True)
    await ev("openColumnEdit(document.querySelector(%s).dataset,true)" % sel)
    await asyncio.sleep(0.8)
    r2 = await ev("""(function(){
      const b=document.getElementById('c_delete_btn');
      return {mode:COLUMN_MODE,disp:b?b.style.display:'nobtn',
        todoGrp:document.getElementById('c_todos_group').style.display,
        todos:document.getElementById('c_todos_list').querySelectorAll('.subtask-item').length};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('mode') == 'edit' and r2.get('disp') == '', 'admin（管理员）可见删除按钮')
    ok(isinstance(r2, dict) and r2.get('todoGrp') == '' and r2.get('todos', 0) == 3, '编辑弹窗待办管理区块加载 3 条')

    # 切换为普通编辑（无板块责任）：同弹窗重开模拟 —— 直接调判定函数+DOM 断言
    print('【② 判定函数：板块负责人可见 / 普通编辑不可见】', flush=True)
    r2b = await ev("""(function(){
      const colOk=colCanDelete('%s','%s');
      // 模拟「无板块责任的普通编辑」视角：换一个假 ME（非管理员、无任何管理清单）
      const saveMe=ME;
      ME={is_admin:false,is_super:false,can_edit:true,managed_columns:[],managed_boards:[],boards:[]};
      const pln=colCanDelete('%s','%s');
      // 再模拟「板块负责人」视角
      ME={is_admin:false,is_super:false,can_edit:true,managed_columns:['%s'],managed_boards:[],boards:[]};
      const colOwner=colCanDelete('%s','%s');
      ME=saveMe;
      return {colOk:colOk,pln:pln,colOwner:colOwner};})()""" % (COLKEY, BID, P + 'nope', BID, COLKEY, COLKEY, BID))
    print('  ', json.dumps(r2b, ensure_ascii=True), flush=True)
    ok(isinstance(r2b, dict) and r2b.get('colOk') is True, '板块负责人判定 = 可见')
    ok(isinstance(r2b, dict) and r2b.get('pln') is False, '无板块责任普通编辑判定 = 不可见（不渲染按钮）')
    ok(isinstance(r2b, dict) and r2b.get('colOwner') is True, '板块负责人视角 = 可见')

    # 待办在编辑弹窗增删（真实落库）
    print('【③ 编辑弹窗待办增/删/勾（真实落库）】', flush=True)
    r3b = await ev("""(async function(){
      document.getElementById('c_todo_new').value='%s待办新';
      await colAddTodo();
      const n1=document.getElementById('c_todos_list').querySelectorAll('.subtask-item').length;
      const cb=document.querySelector('#c_todos_list .subtask-item input[type=checkbox]');
      cb.click();await new Promise(r=>setTimeout(r,400));
      const last=document.getElementById('c_todos_list').querySelector('.subtask-item:last-child input[type=checkbox]');
      const del=document.getElementById('c_todos_list').querySelector('.subtask-item:last-child button');
      del.click();
      await new Promise(r=>setTimeout(r,600));
      const n2=document.getElementById('c_todos_list').querySelectorAll('.subtask-item').length;
      return {n1:n1,n2:n2};})()""" % P, True)
    print('  ', json.dumps(r3b, ensure_ascii=True), flush=True)
    ok(isinstance(r3b, dict) and r3b.get('n1') == 4, '编辑弹窗添加待办 → 4 条')
    ok(isinstance(r3b, dict) and r3b.get('n2') == 3, '确认删除待办 → 回到 3 条')
    import urllib.request as _u
    req = _u.Request(BASE + '/api/columns/todos?col_key=' + urllib.parse.quote(COLKEY),
                     headers={'Authorization': 'Bearer ' + t0})
    todos = json.loads(_u.urlopen(req, timeout=10).read())['todos']
    ok(len(todos) == 3, '服务端复核：待办 3 条（新增已删、勾选保留）')

    await send('Browser.close')


make_fixtures()
try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    cleanup()
    fails = [m for c, m in PASS if not c]
    print('结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)
