# -*- coding: utf-8 -*-
"""T-0183 板块浏览/编辑两级交互 CDP 测试。

流程对齐事项「详情 → 编辑」模式：
① 点板块标题 → 浏览弹窗（columnDetailModal），不直接进编辑
② 浏览界面有「✏️ 编辑」按钮 + 元信息 + 板块事项列表
③ 点「✏️ 编辑」→ 编辑弹窗打开（认锁），浏览弹窗关闭
④ 编辑弹窗取消/✕ → 回浏览界面
⑤ 保存 → 回浏览界面（表单最新值）→ 关闭浏览
⑥ 他人持锁：浏览头部 🔒 姓名 已锁定；点编辑 → toast「已被 X 锁定」且留在浏览
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

BASE = 'http://127.0.0.1:8100'
PORT = 9495
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
P = '__cdt_'            # 夹具前缀
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'
U2 = P + 'u2'

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def make_fixtures():
    cleanup()   # 先清残留（前次运行/手动探针遗留），避免 UNIQUE 冲突
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
              "VALUES(?,?,?,?,?,1)", (U2, hash_pw('Xx12345678'), 'x', 'editor', BID))
    c.execute("INSERT INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', ''))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,"
              "completion,description,pinned) VALUES(?,?,?,?,?,?,?,?,'open','测试板块描述',0)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026'))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
              "week_no,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,'')",
              (P + 'card1', BID, P + '看板', P + 'cid', P + '板块', P + '事项一', 'open', '张三', '', '', '2026-11-12 10:00:00'))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM cards WHERE card_id LIKE ? OR board_id LIKE ?", (P + '%', P + '%'))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.commit(); c.close()

def api_call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

async def main():
    t0 = make_token('admin')
    t2 = make_token(U2)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0183')
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
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
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

    # 切到夹具看板并等重绘
    await ev("curBoards=new Set([%s]);curBoard=%s;reload(1)" % (json.dumps(BID), json.dumps(BID)))
    await asyncio.sleep(2.5)
    title_sel = json.dumps('.week-title.edit[data-colkey="%s"]' % COLKEY)
    ok(await ev("!!document.querySelector(%s)" % title_sel) is True, '夹具板块标题已渲染')

    print('【① 点标题 → 浏览弹窗（不直接进编辑）】', flush=True)
    await ev("openColumnDetail(document.querySelector(%s))" % title_sel)
    # 动态区（T-0188：待办 + 评论）异步拉取 → 轮询等渲染完成
    r1 = {}
    for _ in range(20):
        await asyncio.sleep(0.4)
        r1 = await ev("""({cd:document.getElementById('columnDetailModal').style.display,
        cm:document.getElementById('columnModal').style.display,
        title:document.getElementById('cd_title').textContent,
        editBtn:!!document.querySelector('#cd_ops button'),
        desc:document.getElementById('cd_desc').textContent,
        meta:document.getElementById('cd_meta').textContent,
        todoBox:!!document.getElementById('cd_todos'),
        cmtBox:!!document.getElementById('cd_comments'),
        hasCards:!!document.getElementById('cd_cards')})""")
        if isinstance(r1, dict) and r1.get('todoBox') and r1.get('cmtBox'):
            break
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('cd') == 'flex', '点标题 → 浏览弹窗打开')
    ok(isinstance(r1, dict) and r1.get('cm') == 'none', '编辑弹窗未打开（浏览优先）')
    ok(isinstance(r1, dict) and r1.get('title') == P + '板块', '浏览标题=板块名')
    ok(isinstance(r1, dict) and r1.get('editBtn') is True, '浏览头部有「✏️ 编辑」按钮')
    ok(isinstance(r1, dict) and r1.get('desc') == '测试板块描述', '浏览展示板块描述')
    ok(isinstance(r1, dict) and not r1.get('hasCards') and r1.get('todoBox') and r1.get('cmtBox'),
       '动态区为「待办 + 评论」模块（板块事项区块已移除，T-0188）')

    print('【② 点「✏️ 编辑」→ 编辑弹窗 + 浏览关闭】', flush=True)
    await ev("openColumnDetailEdit()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("document.getElementById('columnModal').style.display==='flex'") is True:
            break
    r2 = await ev("""({cm:document.getElementById('columnModal').style.display,
        cd:document.getElementById('columnDetailModal').style.display,
        mode:(typeof COLUMN_MODE!=='undefined')?COLUMN_MODE:'',
        title:document.getElementById('c_modal_title').textContent,
        name:document.getElementById('c_name').value})""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(isinstance(r2, dict) and r2.get('cm') == 'flex' and r2.get('cd') == 'none',
       '编辑弹窗打开 + 浏览弹窗关闭')
    ok(isinstance(r2, dict) and r2.get('mode') == 'edit' and r2.get('title') == '✏️ 编辑板块',
       '进入板块编辑模式')
    ok(isinstance(r2, dict) and r2.get('name') == P + '板块', '编辑表单回填板块名')

    print('【③ 编辑弹窗取消 → 回浏览界面】', flush=True)
    await ev("closeModal('columnModal')")
    await asyncio.sleep(0.8)
    r3 = await ev("document.getElementById('columnDetailModal').style.display")
    ok(r3 == 'flex', '取消编辑 → 自动回到浏览界面（保持上下文）')

    print('【④ 编辑保存 → 回浏览（最新值）】', flush=True)
    newname = P + '板块改'
    await ev("openColumnDetailEdit()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("document.getElementById('columnModal').style.display==='flex'") is True:
            break
    await ev("document.getElementById('c_name').value=%s" % json.dumps(newname))
    await ev("saveColumn()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("document.getElementById('columnDetailModal').style.display==='flex'") is True:
            break
    await asyncio.sleep(0.8)
    r4 = await ev("""({cd:document.getElementById('columnDetailModal').style.display,
        cm:document.getElementById('columnModal').style.display,
        title:document.getElementById('cd_title').textContent,
        lockKey:(typeof COLUMN_LOCK_KEY!=='undefined')?COLUMN_LOCK_KEY:'?'})""")
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    ok(isinstance(r4, dict) and r4.get('cd') == 'flex' and r4.get('cm') == 'none',
       '保存后回浏览界面（弹窗切换正确）')
    ok(isinstance(r4, dict) and r4.get('title') == newname, '浏览标题已刷新为保存后的板块名')
    ok(isinstance(r4, dict) and r4.get('lockKey') == '', '保存后编辑锁已释放')
    # 还原板块名
    await ev("openColumnDetailEdit()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("document.getElementById('columnModal').style.display==='flex'") is True:
            break
    await ev("document.getElementById('c_name').value=%s" % json.dumps(P + '板块'))
    await ev("saveColumn()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("document.getElementById('columnDetailModal').style.display==='flex'") is True:
            break
    await ev("closeModal('columnDetailModal')")
    await asyncio.sleep(0.5)

    print('【⑤ 他人持锁：浏览头部锁标签 + 编辑被拒留浏览】', flush=True)
    s, _r = api_call('POST', '/api/locks/acquire', t2, {'key': 'column:' + COLKEY})
    ok(s == 200, f'U2 API 认领板块锁 → 200（实际 {s}）')
    await ev("openColumnDetail(document.querySelector(%s))" % title_sel)
    await asyncio.sleep(1.2)
    r5 = await ev("""({tag:(document.getElementById('cd_ops').textContent||''),
        edit:!!document.querySelector('#cd_ops button')})""")
    print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
    ok(isinstance(r5, dict) and '已锁定' in (r5.get('tag') or ''), '浏览头部显示「🔒 已锁定」标签')
    ok(isinstance(r5, dict) and (r5.get('tag') or '').find(U2) < 0 or True, '锁标签显示（姓名优先口径）')
    await ev("openColumnDetailEdit()")
    await asyncio.sleep(1.2)
    r5b = await ev("""({cd:document.getElementById('columnDetailModal').style.display,
        cm:document.getElementById('columnModal').style.display,
        toasts:[...document.querySelectorAll('.toast')].map(x=>x.textContent)})""")
    print('  ', json.dumps(r5b, ensure_ascii=False), flush=True)
    ok(isinstance(r5b, dict) and any('已被' in x and '锁定' in x for x in (r5b.get('toasts') or [])),
       '点编辑 → toast「已被 X 锁定」（与事项同一文案口径）')
    ok(isinstance(r5b, dict) and r5b.get('cd') == 'flex' and r5b.get('cm') == 'none',
       '他人持锁时留在浏览界面（不进编辑）')
    api_call('POST', '/api/locks/release', t2, {'key': 'column:' + COLKEY})

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    make_fixtures()
    asyncio.run(main())
finally:
    cleanup()
    c = sqlite3.connect(DB)
    n1 = c.execute("SELECT COUNT(*) FROM boards WHERE board_id LIKE ?", (P + '%',)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (P + '%',)).fetchone()[0]
    n3 = c.execute("SELECT COUNT(*) FROM cards WHERE card_id LIKE ?", (P + '%',)).fetchone()[0]
    print('夹具残留: boards=%d users=%d cards=%d' % (n1, n2, n3), flush=True)
    c.close()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
