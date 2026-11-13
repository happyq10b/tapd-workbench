# -*- coding: utf-8 -*-
"""T-204d（2026-11-13）评论倒序 + 操作记录实时性 —— 专项实测：
  ① 事项评论 GET 倒序（最新在前）
  ② 板块评论 GET 倒序（最新在前）
  ③ WS 广播：板块评论/待办 → column_change；事项评论 → comment（可见看板过滤）
  ④ CDP 实时刷新：u1 发评论 → admin 开着的板块预览/事项详情即时出现
     （评论列表第一条 = 新评论、操作记录新增「发表评论」）
  ⑤ 本机操作：预览里发评论 → #cd_actions 即时出现本人记录
夹具纪律：__t204d_ 前缀；try/finally 清理 + 零残留自查；结束回收浏览器进程（T-204c 教训）。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9544
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


TK_ADMIN = make_token('admin')
TK_U1 = ''   # ⚠️ u1 在 setup() 里才建号 → token 必须在 setup 之后签发（否则请求全 401/403）
BID = '__t204d_B'
COL_KEY = BID + '::__t204d板块'


def kill_profile_chrome():
    """按 CommandLine 匹配本测试 profile，强制回收（防假在线，T-204c 教训）。
    ⚠️ wmic 输出是 GBK —— 必须 rb 捕获再 errors='ignore' 解码，否则 UnicodeDecodeError。"""
    try:
        out = subprocess.run(
            ['wmic', 'process', "where", "name='chrome.exe'",
             "and CommandLine like '%%cdp_t204d%%'", 'get', 'ProcessId', '/FORMAT:VALUE'],
            capture_output=True, timeout=20).stdout.decode('gbk', errors='ignore')
        for line in out.splitlines():
            if line.startswith('ProcessId='):
                subprocess.run(['taskkill', '/PID', line.split('=')[1].strip(), '/F'],
                               capture_output=True, timeout=10)
    except Exception:
        pass


def db_cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM comments WHERE card_id LIKE '__t204d_%'")
    c.execute("DELETE FROM actions WHERE card_id LIKE '__t204d_%'")
    c.execute("DELETE FROM column_comments WHERE col_key LIKE '%__t204d板块%'")
    c.execute("DELETE FROM column_actions WHERE col_key LIKE '%__t204d板块%'")
    c.execute("DELETE FROM column_todos WHERE col_key LIKE '%__t204d板块%'")
    c.execute("DELETE FROM board_columns WHERE col_key LIKE '%__t204d板块%'")
    c.execute("DELETE FROM cards WHERE board_id LIKE '__t204d_%'")
    c.execute("DELETE FROM boards WHERE board_id LIKE '__t204d_%'")
    c.execute("DELETE FROM messages WHERE receiver LIKE '__t204d_%' OR content LIKE '%__t204d板块%'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t204d_%' OR account LIKE '__t204d_%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t204d_%'")
    c.commit()
    c.close()


def residue_check():
    c = sqlite3.connect(DB)
    pairs = [("users", "username LIKE '__t204d_%'"),
             ("boards", "board_id LIKE '__t204d_%'"),
             ("cards", "card_id LIKE '__t204d_%'"),
             ("comments", "card_id LIKE '__t204d_%'"),
             ("actions", "card_id LIKE '__t204d_%'"),
             ("board_columns", "col_key LIKE '%__t204d板块%'"),
             ("column_comments", "col_key LIKE '%__t204d板块%'"),
             ("column_actions", "col_key LIKE '%__t204d板块%'"),
             ("messages", "receiver LIKE '__t204d_%' OR content LIKE '%__t204d板块%'")]
    bad = []
    for t, w in pairs:
        n = c.execute(f'SELECT COUNT(*) FROM {t} WHERE {w}').fetchone()[0]
        if n:
            bad.append(f'{t}={n}')
    c.close()
    return bad


def setup():
    global TK_U1
    c = sqlite3.connect(DB)
    # 公共看板（不挂 board_config → 全员可见）+ u1 账号
    c.execute("INSERT INTO boards (board_id, board_name, sort) VALUES (?,'__t204d 测试看板',9300)", (BID,))
    c.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t204d_u1',?,'editor')",
              (hash_pw('Xx12345678'),))
    c.commit()
    c.close()
    TK_U1 = make_token('__t204d_u1')
    st, r = api('/api/columns', 'PUT', {
        'col_key': '', 'board_id': BID, 'column_name': '__t204d板块',
        'created_at': '2026-11-13', 'year': '2026', 'nature': '日常', 'description': ''}, TK_ADMIN)
    assert st == 200, f'夹具板块创建失败 {st}'
    # u1 设为板块参与人（公共看板对无关系账号仍不可见 —— user_allowed ⑤ 层需要关系人身份）
    st, _ = api('/api/columns', 'PUT', {
        'col_key': COL_KEY, 'board_id': BID, 'column_name': '__t204d板块',
        'created_at': '2026-11-13', 'year': '2026', 'nature': '日常', 'description': '',
        'participants': '__t204d_u1'}, TK_ADMIN)
    assert st == 200, f'夹具参与人设置失败 {st}'
    _cid = sqlite3.connect(DB).execute(
        'SELECT column_id FROM board_columns WHERE col_key=?', (COL_KEY,)).fetchone()[0]
    st, r = api('/api/cards', 'POST', {'board_id': BID, 'column_id': _cid,
                'card_name': '__t204d 事项甲', 'fields': {'owner': '__t204d_u1'}}, TK_ADMIN)
    assert st == 200, f'夹具事项创建失败 {st}'
    return r.get('card_id') or (sqlite3.connect(DB).execute(
        "SELECT card_id FROM cards WHERE card_name='__t204d 事项甲'").fetchone()[0])


async def ws_wait_event(token, pred, trigger, timeout=6.0):
    """先连 WS 再执行 trigger（同步 api 用线程跑），等待满足 pred 的广播消息。
    ⚠️ 广播是即发即失 —— 必须先挂上监听再触发，否则竞态丢失。"""
    import websockets
    ws = await websockets.connect('ws://127.0.0.1:8100/ws?token=' + token, max_size=1 << 20)
    try:
        t = asyncio.create_task(asyncio.to_thread(trigger))
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - loop.time()))
            except asyncio.TimeoutError:
                break
            m = json.loads(raw)
            if pred(m):
                return m
        await asyncio.to_thread(lambda: t.result(timeout=10) if not t.done() else None)
        return None
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def cdp_section(colkey, card_id):
    """CDP：admin 开着预览/详情，u1 远程发评论 → 即时刷新断言"""
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204d')
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
    try:
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
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
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
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        cookie = 'tk=%s; path=/; Max-Age=86400' % TK_ADMIN
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
                break
        await asyncio.sleep(2)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # 切到夹具看板 → 打开板块预览
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (BID, BID))
        await asyncio.sleep(2.5)
        r1 = await ev("""(function(){
          const t=document.querySelector('#boardContent .week-title.edit[data-colkey]');
          if(!t)return {found:false};
          openColumnDetail(t);
          return {found:true};
        })()""")
        await asyncio.sleep(1.5)
        ok(r1.get('found') is True, '⑥ CDP 打开夹具板块预览')

        # ⑥A u1 远程发板块评论 → admin 开着的预览即时刷新（评论置顶 + 操作记录）
        st, _ = api('/api/columns/comments', 'POST',
                    {'col_key': colkey, 'content': '__t204d 远程实时评论A'}, TK_U1)
        ok(st == 200, '⑥A u1 POST 板块评论 → 200')
        await asyncio.sleep(2.5)
        r2 = await ev("""(function(){
          const first=document.querySelector('#cd_comments .comment-item .who');
          const acts=document.getElementById('cd_actions');
          return {firstWho:first?first.textContent:'', hasAct:(acts?acts.textContent:'').indexOf('__t204d_u1')>=0
                  &&(acts?acts.textContent:'').indexOf('发表评论')>=0};
        })()""")
        ok(r2.get('firstWho') == '__t204d_u1', f"⑥A 预览评论第一条=u1（倒序+实时）：实际 {r2.get('firstWho')}")
        ok(r2.get('hasAct') is True, '⑥A 操作记录即时出现 u1「发表评论」')

        # ⑥B admin 本机在预览里发评论 → 操作记录即时出现本人记录（无需重开弹窗）
        await ev("document.getElementById('cd_new_comment').value='__t204d 本机评论B';cdAddComment()")
        await asyncio.sleep(2)
        r3 = await ev("""(function(){
          const first=document.querySelector('#cd_comments .comment-item');
          const acts=document.getElementById('cd_actions');
          const t=acts?acts.textContent:'';
          return {firstHasB:first?first.textContent.indexOf('本机评论B')>=0:false,
                  firstWho:first?(first.querySelector('.who')||{}).textContent:'',
                  adminAct:t.indexOf('admin')>=0&&t.indexOf('发表评论')>=0};
        })()""")
        ok(r3.get('firstWho') == 'admin' and r3.get('firstHasB') is True,
           f"⑥B 本机评论置顶显示（最新在前）：实际 {r3.get('firstWho')}")
        ok(r3.get('adminAct') is True, '⑥B 本机发评论后操作记录即时出现 admin「发表评论」')

        # ⑦ 事项详情：u1 远程发事项评论 → admin 开着的详情即时刷新
        await ev("openDetail('%s')" % card_id)
        await asyncio.sleep(2)
        st, _ = api('/api/cards/%s/comments' % card_id, 'POST',
                    {'content': '__t204d 远程实时评论C'}, TK_U1)
        ok(st == 200, '⑦ u1 POST 事项评论 → 200')
        await asyncio.sleep(2.5)
        r4 = await ev("""(function(){
          const first=document.querySelector('#d_comments .comment-item .who');
          const acts=document.getElementById('d_actions');
          return {firstWho:first?first.textContent:'', hasAct:(acts?acts.textContent:'').indexOf('__t204d_u1')>=0
                  &&(acts?acts.textContent:'').indexOf('发表评论')>=0};
        })()""")
        ok(r4.get('firstWho') == '__t204d_u1', f"⑦ 事项详情评论第一条=u1（倒序+实时）：实际 {r4.get('firstWho')}")
        ok(r4.get('hasAct') is True, '⑦ 事项操作记录即时出现 u1「发表评论」')

        r5 = await ev("window.__errs")
        ok(not r5, f'⑧ 无 JS 错误（实际：{r5}）')
    finally:
        kill_profile_chrome()
        shutil.rmtree(profile, ignore_errors=True)


async def main():
    card_id = setup()
    qk = urllib.parse.quote(COL_KEY, safe='')
    try:
        # ---------- ① 事项评论倒序 ----------
        api('/api/cards/%s/comments' % card_id, 'POST', {'content': '事项评论-第一条'}, TK_ADMIN)
        api('/api/cards/%s/comments' % card_id, 'POST', {'content': '事项评论-第二条'}, TK_U1)
        st, r = api('/api/cards/%s/comments' % card_id, token=TK_ADMIN)
        cs = (r or {}).get('comments') or []
        ok(st == 200 and len(cs) >= 2 and cs[0]['content'] == '事项评论-第二条',
           f'① 事项评论倒序（最新在前）→ {st}，{len(cs)} 条，首条={cs[0]["content"] if cs else "?"}')

        # ---------- ② 板块评论倒序 ----------
        api('/api/columns/comments', 'POST', {'col_key': COL_KEY, 'content': '板块评论-第一条'}, TK_ADMIN)
        api('/api/columns/comments', 'POST', {'col_key': COL_KEY, 'content': '板块评论-第二条'}, TK_U1)
        st, r = api('/api/columns/comments?col_key=' + qk, token=TK_ADMIN)
        cs = (r or {}).get('comments') or []
        ok(st == 200 and len(cs) >= 2 and cs[0]['content'] == '板块评论-第二条',
           f'② 板块评论倒序（最新在前）→ {st}，{len(cs)} 条，首条={cs[0]["content"] if cs else "?"}')

        # ---------- ③ WS 广播（先挂监听再触发，广播即发即失） ----------
        m = await ws_wait_event(TK_ADMIN, lambda m: m.get('type') == 'column_change'
                                and m.get('col_key') == COL_KEY,
                                lambda: api('/api/columns/comments', 'POST',
                                            {'col_key': COL_KEY, 'content': '触发广播-板块评论'}, TK_U1))
        ok(m is not None, '③ 板块评论 → WS column_change 广播（col_key 匹配，可见看板过滤）')
        m = await ws_wait_event(TK_ADMIN, lambda m: m.get('type') == 'comment'
                                and m.get('card_id') == card_id,
                                lambda: api('/api/cards/%s/comments' % card_id, 'POST',
                                            {'content': '触发广播-事项评论'}, TK_U1))
        ok(m is not None, '③ 事项评论 → WS comment 广播（card_id 匹配）')

        # ---------- ⑥⑦⑧ CDP 实时刷新 ----------
        await cdp_section(COL_KEY, card_id)
    finally:
        db_cleanup()
        print('finally 清理完成，残留：', residue_check() or '无', flush=True)
    n = sum(PASSED)
    print(f'\n=== {n}/{len(PASSED)} passed ===', flush=True)
    return 0 if n == len(PASSED) else 1


if __name__ == '__main__':
    try:
        rc = asyncio.run(main())
    finally:
        kill_profile_chrome()
    sys.exit(rc if isinstance(rc, int) else 1)
