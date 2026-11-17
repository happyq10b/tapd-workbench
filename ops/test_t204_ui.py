# -*- coding: utf-8 -*-
"""T-204（2026-11-13）板块功能增强 —— CDP UI 实测：
  ① 目录行无「逾期」槽位，标题列吸收释放空间（宽了 ≥40px）
  ② 事项详情：全部评论按钮 / comment-list 限高 / 弹窗打开
  ③ 板块浏览：评论 @ 提及（chip + 候选下拉）/ 全部评论 / 操作记录区块
  ④ 板块操作菜单不再含折叠/展开；工具栏【操作 ▾】含全局折叠/展开子事项
  ⑤ 全局展开/折叠生效 + user_prefs.subtree_open 按用户持久化
夹具：__t204_ 前缀板块/事项（API 直造），try/finally 清理 + 零残留自查。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, cleanup as cdp_cleanup  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
PORT = 9541
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


conn = sqlite3.connect(DB)
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t204_ui',?,'admin')", (hash_pw('Xx12345678'),))
conn.commit()
conn.close()
TK = make_token('__t204_ui')   # admin 角色夹具账号 → 全量可见

COL_KEY = ''


def db_cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM column_comments WHERE col_key LIKE '%__t204%'")
    c.execute("DELETE FROM column_todos WHERE col_key LIKE '%__t204%'")
    c.execute("DELETE FROM column_actions WHERE col_key LIKE '%__t204%'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t204%'")
    c.execute("DELETE FROM actions WHERE card_id LIKE '__t204%'")
    c.execute("DELETE FROM cards WHERE card_id LIKE '__t204%' OR board_id LIKE '__t204%'")
    c.execute("DELETE FROM board_columns WHERE col_key LIKE '%__t204%' OR board_id LIKE '__t204%'")
    c.execute("DELETE FROM board_config WHERE board_id LIKE '__t204_%'")
    c.execute("DELETE FROM boards WHERE board_id LIKE '__t204_%'")
    c.execute("DELETE FROM user_prefs WHERE username LIKE '__t204_%' OR key='subtree_open' AND username='__t204_ui'")
    c.execute("DELETE FROM users WHERE username LIKE '__t204_%'")
    c.commit()
    c.close()


def residue_check():
    c = sqlite3.connect(DB)
    pairs = [
        ("users", "username LIKE '__t204_%'"),
        ("boards", "board_id LIKE '__t204_%'"),
        ("board_columns", "col_key LIKE '%__t204%' OR board_id LIKE '__t204%'"),
        ("cards", "card_id LIKE '__t204%' OR board_id LIKE '__t204%'"),
        ("column_actions", "col_key LIKE '%__t204%'"),
        ("user_prefs", "username LIKE '__t204_%'"),
    ]
    bad = []
    for t, w in pairs:
        n = c.execute(f'SELECT COUNT(*) FROM {t} WHERE {w}').fetchone()[0]
        if n:
            bad.append(f'{t}={n}')
    c.close()
    return bad


def api(path, method='GET', data=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TK)
    body = json.dumps(data).encode() if data is not None else None
    if body:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def kill_profile_chrome(profile):
    """T-204c 教训：CDP 测试结束必须杀掉自己 profile 的 Chrome ——
    残留 headless 实例的 WS 心跳一直活跃，服务端会判定该账号「真在线」，
    在线用户管理里永远显示未下线（探针以 admin 登录 → admin 无法被踢回登录态）。"""
    import re
    try:
        out = subprocess.run(
            ['wmic', 'process', 'where',
             "name='chrome.exe' and CommandLine like '%%%s%%'" % profile,
             'get', 'ProcessId', '/FORMAT:VALUE'],
            capture_output=True, text=True, timeout=20).stdout
        for pid in re.findall(r'ProcessId=(\d+)', out):
            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
    except Exception:
        pass


async def main():
    import websockets
    # ---------- 夹具：公共看板 + 板块 + 两个主事项（其一带子事项） ----------
    conn = sqlite3.connect(DB)
    conn.execute("INSERT OR REPLACE INTO boards (board_id,board_name,sort) VALUES ('__t204_B','__t204 UI看板',9201)")
    conn.commit()
    conn.close()
    st, r = api('/api/columns', 'PUT', {
        'col_key': '', 'board_id': '__t204_B', 'column_name': '__t204板块A',
        'created_at': '2026-11-13', 'year': '2026', 'nature': '日常', 'description': ''})
    ok(st == 200, '夹具板块创建')
    global COL_KEY
    COL_KEY = r['col_key']
    _c = sqlite3.connect(DB)
    _colid = _c.execute('SELECT column_id FROM board_columns WHERE col_key=?', (COL_KEY,)).fetchone()[0]
    _c.close()
    CARD_IDS = []
    for nm in ['__t204 主事项甲（这是个相当长的标题用来验证标题列加宽之后能否完整显示而不再被截断得很难看）',
               '__t204 主事项乙']:
        st, r = api('/api/cards', 'POST', {
            'board_id': '__t204_B', 'column_id': _colid, 'card_name': nm,
            'fields': {'due': '2026-11-13', 'owner': ''}})
        ok(st == 200 and r.get('card_id'), f'夹具事项创建 {nm[:12]}… → {st}')
        if r.get('card_id'):
            CARD_IDS.append(r['card_id'])
    CID_A = CARD_IDS[0] if len(CARD_IDS) > 0 else ''
    CID_B = CARD_IDS[1] if len(CARD_IDS) > 1 else ''
    # 子事项（子卡，parent_id 挂事项乙 —— 供折叠测试；注意子事项 ≠ 代办任务）
    st, r = api('/api/cards', 'POST', {
        'board_id': '__t204_B', 'column_id': _colid, 'card_name': '__t204 子事项一',
        'parent_id': CID_B, 'fields': {'due': '2026-11-13', 'owner': ''}}) if CID_B else (0, {})
    ok(st == 200, f'夹具子事项 → {st}')

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1920,1080',
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
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        res = await asyncio.wait_for(fut, timeout=30)
        return res.get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    # 1920×1080 视口（headless 窗口参数不可靠 → 用设备度量覆盖）
    await send('Emulation.setDeviceMetricsOverride',
               {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})

    cookie = 'tk=%s; path=/; Max-Age=86400' % TK
    await send('Page.navigate', {'url': BASE + '/'})
    await asyncio.sleep(1)
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    logged = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__t204_ui'")
        if r is True:
            logged = True
            break
    ok(logged, '夹具账号登录就绪')
    await asyncio.sleep(2.5)

    # 夹具建在登录之后 → 整页重载让 /api/me 重新拉取看板清单（含夹具看板），
    # 再切换到夹具看板（curBoards 是内容区权威选择，与 saveColumn 同款切换）
    await ev("location.reload()")
    await asyncio.sleep(2.5)
    await ev("curBoard='__t204_B';curBoards=new Set(['__t204_B']);reload(1)")
    await asyncio.sleep(3)

    print('【① 逾期列移除 + 标题加宽】', flush=True)
    r1 = await ev("""(function(){
      const overdue=[...document.querySelectorAll('#boardContent .slot-overdue')].length;
      const titles=[...document.querySelectorAll('#boardContent .item-title')];
      const card=titles.find(t=>t.textContent.indexOf('__t204 主事项甲')>=0);
      const r=card?card.getBoundingClientRect():null;
      return {overdue, titleW:r?Math.round(r.width):0,
              rows:document.querySelectorAll('#boardContent .item-card').length};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1.get('overdue') == 0, '① 目录无 slot-overdue 元素')
    ok((r1.get('titleW') or 0) > 400, f'① 标题列宽度 {r1.get("titleW")}px（释放空间已让给标题，1920 视口）')

    print('【② 事项详情：全部评论 + 限高】', flush=True)
    await ev("openDetail(%s)" % json.dumps(CID_A))
    await asyncio.sleep(1.5)
    r2 = await ev("""(function(){
      const btns=[...document.querySelectorAll('#detailModal .comment-form button')].map(b=>b.textContent.trim());
      const box=document.getElementById('d_comments');
      const cs=getComputedStyle(box);
      return {btns, cls:box.className, maxH:cs.maxHeight, ov:cs.overflowY};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok('全部评论' in (r2.get('btns') or []), '② 发送右侧有【全部评论】按钮')
    ok('comment-list' in (r2.get('cls') or ''), '② 预览容器为 comment-list（限高滚动）')
    ok(r2.get('ov')=='auto', '② overflow-y:auto')
    await ev("openAllComments('card')")
    await asyncio.sleep(1)
    r2b = await ev("""(function(){
      const m=document.getElementById('allCommentsModal');
      return {shown:m.style.display==='flex', title:document.getElementById('ac_title').textContent};
    })()""")
    print('  ', json.dumps(r2b, ensure_ascii=False), flush=True)
    ok(r2b.get('shown'), '② 全部评论弹窗打开')
    await ev("closeModal('allCommentsModal');closeModal('detailModal')")
    await asyncio.sleep(0.5)

    print('【③ 板块浏览：@ 提及 + 全部评论 + 操作记录】', flush=True)
    await ev("openColumnDetail(document.querySelector('.week-title.edit[data-colkey]'))")
    await asyncio.sleep(1.5)
    r3 = await ev("""(function(){
      return {hasAt:!!document.querySelector('#columnDetailModal .comment-form button[title="提及成员"]'),
              hasAll:!!document.getElementById('columnDetailModal') &&
                     [...document.querySelectorAll('#columnDetailModal .comment-form button')].some(b=>b.textContent.trim()==='全部评论'),
              hasActs:!!document.getElementById('cd_actions'),
              actsTxt:(document.getElementById('cd_actions').textContent||'').slice(0,40),
              cls:document.getElementById('cd_comments').className};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3.get('hasAt'), '③ 板块评论有 @ 按钮')
    ok(r3.get('hasAll'), '③ 板块评论有【全部评论】按钮')
    ok(r3.get('hasActs'), '③ 操作记录区块存在')
    ok('新建板块' in (r3.get('actsTxt') or ''), f"③ 操作记录含「新建板块」（实际：{r3.get('actsTxt')}）")
    ok('comment-list' in (r3.get('cls') or ''), '③ 板块评论预览同样限高')
    # @ 候选下拉：点 @ 按钮 → 候选出现 → 选第一个 → chip 出现
    await ev("toggleMentionMenu('cd')")
    await asyncio.sleep(0.5)
    r3b = await ev("""(function(){
      const drop=document.getElementById('cd_mention_drop');
      const n=drop&&!drop.hidden?drop.querySelectorAll('.mention-opt').length:0;
      if(n){drop.querySelector('.mention-opt').click();}
      return {opts:n, chip:document.querySelectorAll('#cd_mention_bar .mention-chip').length};
    })()""")
    print('  ', json.dumps(r3b, ensure_ascii=False), flush=True)
    ok((r3b.get('opts') or 0)>0, '③ @ 候选下拉展开')
    ok((r3b.get('chip') or 0)==1, '③ 选中候选 → chip 插入（cd 上下文独立）')
    # 发送带提及的板块评论
    await ev("document.getElementById('cd_new_comment').value='UI实测评论'")
    await ev("cdAddComment()")
    await asyncio.sleep(1.5)
    r3c = await ev("""(function(){
      const box=document.getElementById('cd_comments');
      return {at:box.innerHTML.indexOf('at-name')>=0, chips:document.querySelectorAll('#cd_mention_bar .mention-chip').length,
              reset:document.getElementById('cd_new_comment').value===''};
    })()""")
    print('  ', json.dumps(r3c, ensure_ascii=False), flush=True)
    ok(r3c.get('at'), '③ 板块评论发送成功且 @ 高亮渲染')
    ok((r3c.get('chips') or 0)==0 and r3c.get('reset'), '③ 发送后提及状态清空')
    await ev("closeModal('columnDetailModal')")
    await asyncio.sleep(0.5)

    print('【④ 折叠/展开入口收敛】', flush=True)
    # 板块行「操作 ▾」不再含折叠/展开
    await ev("""(function(){
      const btn=document.querySelector('#boardContent .week-header .ops-btn');
      if(btn)btn.click();
    })()""")
    await asyncio.sleep(0.5)
    r4 = await ev("""(function(){
      const items=[...document.querySelectorAll('.row-ops-menu .row-ops-item')].map(b=>b.textContent.trim());
      document.body.click();
      return {items:items};
    })()""")
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    items4 = r4.get('items') or []
    ok(len(items4) >= 3 and not any('折叠子事项' in x or '展开子事项' in x for x in items4),
       '④ 板块行菜单无折叠/展开子事项')
    # 工具栏【操作 ▾】含全局折叠/展开
    await ev("rowOpsShow({stopPropagation:function(){},clientX:600,clientY:300},'toolbarOps')")
    await asyncio.sleep(0.5)
    r4b = await ev("""(function(){
      const items=[...document.querySelectorAll('.row-ops-menu .row-ops-item')].map(b=>b.textContent.trim());
      document.body.click();
      return {items:items};
    })()""")
    print('  ', json.dumps(r4b, ensure_ascii=False), flush=True)
    items4b = r4b.get('items') or []
    ok(any('折叠子事项' in x for x in items4b) and any('展开子事项' in x for x in items4b),
       '④ 工具栏【操作 ▾】含全局折叠/展开子事项')

    print('【⑤ 全局展开/折叠 + 按用户持久化】', flush=True)
    await ev("foldAllItems(true)")
    await asyncio.sleep(2)
    r5 = await ev("""(function(){
      const open=[...document.querySelectorAll('.sub-tree')].filter(b=>b.style.display!=='none').length;
      return {open:open};
    })()""")
    ok((r5.get('open') or 0) >= 1, f"⑤ 全局展开子事项生效（{r5.get('open')} 棵展开）")
    await asyncio.sleep(1.2)   # 等防抖上传
    pref = sqlite3.connect(DB).execute(
        "SELECT value FROM user_prefs WHERE username='__t204_ui' AND key='subtree_open'").fetchone()
    ok(pref is not None, '⑤ user_prefs.subtree_open 已按用户落库')
    await ev("foldAllItems(false)")
    await asyncio.sleep(1.5)
    r5b = await ev("""(function(){
      const open=[...document.querySelectorAll('.sub-tree')].filter(b=>b.style.display!=='none').length;
      return {open};
    })()""")
    ok((r5b.get('open') or 0)==0, '⑤ 全局折叠子事项生效')

    # 控制台错误检查
    errs = await ev("window.__js_errors?window.__js_errors.length:'n/a'")
    print('  js_errors:', errs, flush=True)

    db_cleanup()
    bad = residue_check()
    ok(not bad, '零残留自查' + ('' if not bad else ' → ' + '、'.join(bad)))

    n_pass = sum(1 for x in PASSED if x)
    print(f'\n=== {n_pass}/{len(PASSED)} passed ===', flush=True)
    return 0 if n_pass == len(PASSED) else 1


if __name__ == '__main__':
    try:
        rc = asyncio.run(main())
    finally:
        cdp_cleanup("cdp_t204")
        try:
            db_cleanup()
            print('finally 清理完成（浏览器进程已回收），残留：', residue_check() or '无', flush=True)
        except Exception as e:
            print('finally 清理异常：', e, flush=True)
    sys.exit(rc if isinstance(rc, int) else 1)
