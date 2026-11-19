# -*- coding: utf-8 -*-
"""T-0189 筛选工具栏 UI 重构 CDP 测试。

① 大标题：架构部门→架构、可选看板→看板
② 板块筛选标题行：标题【板块】（看板带同款）+ 筛选明细右侧 + 三按钮行尾
③ 筛选框行：创建日期区间已删、人员→负责人、新增参与人框、操作按钮行尾
④ 参与人筛选真实过滤（cc 参数，落库口径）
⑤ 全选当前 / 取消全选 切换
⑥ 清空筛选后按钮布局稳定（#84 bug 回归）
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9529
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
P = '__tb9_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def make_fixtures():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', ''))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,"
              "completion,description,pinned) VALUES(?,?,?,?,?,?,?,?,'open','',0)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026'))
    # card1：负责人 张三、参与人 李四；card2：负责人 王五、参与人 李四；card3：参与人 王五
    rows = [
        (P + 'c1', '事项甲', '张三', '李四'),
        (P + 'c2', '事项乙', '王五', '李四'),
        (P + 'c3', '事项丙', '张三', '王五'),
    ]
    for cid, nm, ow, cc in rows:
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
                  "week_no,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,'')",
                  (cid, BID, P + '看板', P + 'cid', P + '板块', nm, 'open', ow, cc, '2026-46', '2026-11-12 10:00:00'))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM cards WHERE card_id LIKE ? OR board_id LIKE ?", (P + '%', P + '%'))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.commit(); c.close()

async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0189')
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
    asyncio.get_event_loop().create_task(reader())

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【① 大标题更名】', flush=True)
    r0 = await ev("[...document.querySelectorAll('.tb-navgroup .tb-band-title')].map(x=>x.textContent.trim())")
    print('  ', json.dumps(r0, ensure_ascii=True), flush=True)
    ok(isinstance(r0, list) and r0[:2] == ['架构', '看板'], '大标题为「架构」「看板」')

    # 切到夹具看板并等重绘
    bid_js = json.dumps(BID)
    await ev('curBoards=new Set([' + bid_js + ']);curBoard=' + bid_js + ';reload(1)')
    await asyncio.sleep(3.0)

    print('【② 板块筛选标题行】', flush=True)
    r1 = await ev("""(function(){
      const tb=document.querySelector('.toolbar');
      const row=document.querySelector('.toolbar-title-row');
      if(!tb||!row)return {err:'missing'};
      const rowR=row.getBoundingClientRect(), tbR=tb.getBoundingClientRect();
      const btns=row.querySelector('.toolbar-title-btns');
      const bR=btns?btns.getBoundingClientRect():null;
      const hint=document.getElementById('filterHint');
      return {title:row.querySelector('.tb-band-title').textContent.trim(),
        hintInRow:!!(hint&&row.contains(hint)),
        btnsInRow:['chkAllBtn','chkModeBtn'].every(function(id){const b=document.getElementById(id);return b&&row.contains(b);})
          &&!!(row.querySelector('.btn-clear')&&row.textContent.indexOf('清空筛选')>=0),
        btnsRight:Math.round(bR.right),tbRight:Math.round(tbR.right-16),
        rowTop:Math.round(rowR.top),
        leftTop:Math.round(document.querySelector('.toolbar-left').getBoundingClientRect().top)};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('title') == '板块', '筛选栏标题【板块】（看板带同款 .tb-band-title）')
    ok(isinstance(r1, dict) and r1.get('hintInRow'), '筛选明细在标题右侧（同一行）')
    ok(isinstance(r1, dict) and r1.get('btnsInRow'), '三个勾选类按钮都在标题行')
    ok(isinstance(r1, dict) and abs(r1.get('btnsRight', 0) - r1.get('tbRight', -1)) <= 3,
       '按钮组贴标题行右端（与工具栏右缘对齐）')
    ok(isinstance(r1, dict) and r1.get('rowTop', 99) < r1.get('leftTop', 0), '标题行在筛选框行上方')

    print('【③ 筛选框行：删日期 / 更名负责人 / 新增参与人 / 操作行尾】', flush=True)
    r2 = await ev("""(function(){
      const left=document.querySelector('.toolbar-left');
      const sg=left.querySelector('.search-group').getBoundingClientRect();
      const ops=document.getElementById('toolbarOpsBtn').getBoundingClientRect();
      const labelOf=function(w){const l=document.getElementById(w);return l?l.querySelector('.cf-label').textContent.trim():null;};
      return {dateGone:!document.getElementById('createdStart')&&!document.getElementById('dateFilterBox'),
        owner:labelOf('personFilterWrap'),cc:labelOf('ccFilterWrap'),
        ccSameRow:Math.abs(document.getElementById('ccFilterWrap').getBoundingClientRect().top-sg.top)<3,
        opsSameRow:Math.abs(ops.top-sg.top)<3,
        opsRight:Math.round(ops.right),
        leftRight:Math.round(left.getBoundingClientRect().right-16),
        sgW:Math.round(sg.width)};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('dateGone'), '创建日期区间筛选项已删除')
    ok(isinstance(r2, dict) and r2.get('owner') == '👤 负责人', '【人员】已更名为【负责人】')
    ok(isinstance(r2, dict) and r2.get('cc') == '👥 参与人', '新增【参与人】筛选框（同款样式）')
    ok(isinstance(r2, dict) and r2.get('ccSameRow') and r2.get('opsSameRow'),
       '参与人框与搜索框同行、操作按钮在筛选框行末尾')
    ok(isinstance(r2, dict) and abs(r2.get('opsRight', 0) - r2.get('leftRight', -1)) <= 3,
       '操作按钮贴筛选框行右缘（无溢出/空余）') if False else None
    # left.getBoundingClientRect().right 已是工具栏内容右缘（子元素不含容器 padding）
    r2b = await ev("""(function(){
      const ops=document.getElementById('toolbarOpsBtn').getBoundingClientRect();
      const left=document.querySelector('.toolbar-left').getBoundingClientRect();
      return {opsRight:Math.round(ops.right),leftRight:Math.round(left.right)};})()""")
    ok(isinstance(r2b, dict) and abs(r2b.get('opsRight', 0) - r2b.get('leftRight', -1)) <= 3,
       '操作按钮贴筛选框行右缘（无溢出/空余）')

    print('【④ 参与人筛选真实过滤】', flush=True)
    r3 = await ev("""(function(){
      CC_SEL=new Set(['李四']);window._ccFilter='李四';
      paintFilterCombos();return reload(1).then(function(){
        const names=[...document.querySelectorAll('.item-title')].map(x=>x.textContent.trim());
        const wrap=document.getElementById('ccFilterWrap');
        return {names:names,chips:wrap.querySelectorAll('.cf-chip').length,
          active:wrap.classList.contains('active'),
          count:document.getElementById('ccFilterCount').textContent,
          hint:document.getElementById('filterHint').textContent};});
    })()""", True)
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    names = (r3 or {}).get('names', []) if isinstance(r3, dict) else []
    joined = ''.join(names)
    ok('甲' in joined and '丙' not in joined and '乙' in joined,
       '参与人=李四 → 只显示参与人含李四的事项（丙被过滤）')
    ok(isinstance(r3, dict) and r3.get('chips', 0) >= 1 and '已选 1' in (r3.get('count') or ''),
       '参与人框：计数徽标与 active 高亮')
    ok(isinstance(r3, dict) and '参与人：李四' in (r3.get('hint') or ''), '筛选明细汇总含「参与人：李四」')

    print('【⑤ 全选当前 / 取消全选 切换】', flush=True)
    # 先清掉参与人筛选，恢复 3 条
    await ev("CC_SEL=new Set();window._ccFilter='';paintFilterCombos();reload(1)")
    await asyncio.sleep(2.5)
    await ev("document.getElementById('chkModeBtn').click()")
    await asyncio.sleep(2.0)
    r4a = await ev("(function(){const b=document.getElementById('chkAllBtn');return {vis:b.style.display!=='none',txt:b.textContent.trim()};})()")
    ok(isinstance(r4a, dict) and r4a.get('vis') and r4a.get('txt') == '全选当前', '启用勾选后「全选当前」出现')
    await ev("document.getElementById('chkAllBtn').click()")
    await asyncio.sleep(0.8)
    r4b = await ev("""(function(){
      const items=[...document.querySelectorAll('.item-chk')];
      const subs=[...document.querySelectorAll('.sub-chk')];
      return {txt:document.getElementById('chkAllBtn').textContent.trim(),
        n:items.length,on:items.filter(x=>x.checked).length,subOn:subs.filter(x=>x.checked).length};})()""")
    print('  ', json.dumps(r4b, ensure_ascii=True), flush=True)
    ok(isinstance(r4b, dict) and r4b.get('txt') == '取消全选' and r4b.get('n') > 0 and r4b.get('on') == r4b.get('n'),
       '点击全选 → 全部事项勾选，按钮变「取消全选」')
    await ev("document.getElementById('chkAllBtn').click()")
    await asyncio.sleep(0.8)
    r4c = await ev("""(function(){
      const items=[...document.querySelectorAll('.item-chk')];
      return {txt:document.getElementById('chkAllBtn').textContent.trim(),
        on:items.filter(x=>x.checked).length};})()""")
    ok(isinstance(r4c, dict) and r4c.get('txt') == '全选当前' and r4c.get('on') == 0,
       '再次点击 → 取消全选（按钮切回「全选当前」）')

    print('【⑥ 清空筛选后按钮布局稳定（#84 bug 回归）】', flush=True)
    # 记录标题行按钮组位置 → 设置筛选 → 点清空筛选 → 比对
    await ev("document.getElementById('searchInput').value='事项'")
    before = await ev("""(function(){
      const b=document.querySelector('.toolbar-title-btns').getBoundingClientRect();
      return {left:Math.round(b.left),right:Math.round(b.right),top:Math.round(b.top)};})()""")
    await ev("clearAllRowFilters()")
    for _ in range(20):
        await asyncio.sleep(0.4)
        st = await ev("({q:document.getElementById('searchInput').value,hint:document.getElementById('filterHint').textContent})")
        if isinstance(st, dict) and not st.get('q'):
            break
    await asyncio.sleep(1.0)
    after = await ev("""(function(){
      const row=document.querySelector('.toolbar-title-row');
      const b=document.querySelector('.toolbar-title-btns').getBoundingClientRect();
      const cb=row.querySelector('.btn-clear');
      return {left:Math.round(b.left),right:Math.round(b.right),top:Math.round(b.top),
        inRow:row.contains(cb),hint:document.getElementById('filterHint').textContent};})()""")
    print('  before:', json.dumps(before, ensure_ascii=True), ' after:', json.dumps(after, ensure_ascii=True), flush=True)
    ok(isinstance(after, dict) and after.get('inRow'), '清空筛选后三个按钮仍在标题行')
    ok(isinstance(before, dict) and isinstance(after, dict)
       and abs(before.get('left', 0) - after.get('left', -9)) <= 2
       and abs(before.get('right', 0) - after.get('right', -9)) <= 2
       and before.get('top') == after.get('top'),
       '清空筛选前后按钮位置完全不变（#84 错位修复）')
    ok(isinstance(after, dict) and after.get('hint') == '', '清空后筛选明细为空')
    # 再带明细（非空 hint）场景：设置参与人筛选 → 按钮仍贴右
    await ev("CC_SEL=new Set(['李四']);window._ccFilter='李四';paintFilterCombos();reload(1)")
    await asyncio.sleep(2.0)
    after2 = await ev("""(function(){
      const b=document.querySelector('.toolbar-title-btns').getBoundingClientRect();
      const tb=document.querySelector('.toolbar').getBoundingClientRect();
      return {right:Math.round(b.right),tbRight:Math.round(tb.right-16)};})()""")
    ok(isinstance(after2, dict) and abs(after2.get('right', 0) - after2.get('tbRight', -1)) <= 3,
       '明细非空时按钮组仍贴行尾')
    # 复原
    await ev("CC_SEL=new Set();window._ccFilter='';paintFilterCombos();reload(1)")

    await send('Browser.close')


make_fixtures()
try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    cleanup()
    print('夹具残留自查（清理后）', flush=True)
    c = sqlite3.connect(DB)
    n_res = 0
    for tb, col in (('boards', 'board_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                    ('users', 'username')):
        n_res += c.execute("SELECT COUNT(*) FROM %s WHERE %s LIKE ? ESCAPE '\\'" % (tb, col),
                           ('%' + P.replace('_', '\\_') + '%',)).fetchone()[0]
    c.close()
    ok(n_res == 0, '夹具零残留（实际 %d）' % n_res)

fails = [m for cnd, m in PASS if not cnd]
print('结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
for m in fails:
    print('  FAILED:', m, flush=True)
sys.exit(1 if fails else 0)
