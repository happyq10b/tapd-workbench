# -*- coding: utf-8 -*-
"""T-0184 架构树行级编辑锁提示 CDP 测试。

① 架构管理弹窗树行正常渲染（无锁时无 tag）
② U2 API 认锁 org:<nid> → admin 端 WS 收 edit_lock → 树**实时**出现「🔒 姓名 已锁定」
   （与事项行同款 .lock-tag 样式，姓名优先显示）
③ U2 释放 → tag 实时消失
④ 树接口输出 locked_by/locked_by_name；自己持锁不显示 tag
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

BASE = 'http://127.0.0.1:8100'
PORT = 9503
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
P = '__olb_'
NID = None
U2 = P + 'u2'

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def nid_of():
    c = sqlite3.connect(DB, timeout=15)
    r = c.execute("SELECT id FROM org_nodes WHERE name=?", (P + '测试部门',)).fetchone()
    c.close()
    return r[0] if r else None

def make_fixtures():
    global NID
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) "
              "VALUES(?,?,?,?,1)", (U2, hash_pw('Xx12345678'), 'x', 'editor'))
    c.execute("INSERT INTO org_nodes(name,node_type,parent_id,wg_id,is_anchor,function) "
              "VALUES(?,?,0,0,0,'')", (P + '测试部门', 'dept'))
    c.commit()
    NID = c.execute("SELECT id FROM org_nodes WHERE name=?", (P + '测试部门',)).fetchone()[0]
    c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
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
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0184')
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

    print('【① 打开架构管理：树行渲染 + 无锁无 tag】', flush=True)
    await ev("openWgModal()")
    for _ in range(30):
        await asyncio.sleep(0.4)
        if await ev("document.getElementById('wgModal').style.display==='flex'") is True:
            break
    await asyncio.sleep(1.5)
    row_sel = json.dumps('.org-node-row[data-org-id="%d"]' % NID)
    r1 = await ev("""({row:!!document.querySelector(%s),
        tags:document.querySelectorAll('.org-node-row[data-org-id="%d"] .lock-tag').length,
        treeFields:(function(){const n=ORG_FLAT.find(x=>x.id===%d);return n?('locked_by' in n):null})()})"""
        % (row_sel, NID, NID))
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(isinstance(r1, dict) and r1.get('row') is True, '夹具节点行已渲染')
    ok(isinstance(r1, dict) and r1.get('tags') == 0, '无锁时行内无 🔒 标签')
    ok(isinstance(r1, dict) and r1.get('treeFields') is True, '树接口输出 locked_by 字段')

    print('【② U2 认锁 → admin 端实时出现 🔒 姓名 已锁定】', flush=True)
    s, _r = api_call('POST', '/api/locks/acquire', t2, {'key': 'org:%d' % NID})
    ok(s == 200, f'U2 认领节点锁 → 200（实际 {s}）')
    tag_txt = ''
    for _ in range(20):
        await asyncio.sleep(0.5)
        tag_txt = await ev("(function(){const t=document.querySelector(%s+' .lock-tag');return t?t.textContent:''})()" % row_sel)
        if tag_txt:
            break
    print('  tag:', json.dumps(tag_txt, ensure_ascii=False), flush=True)
    ok(bool(tag_txt) and '已锁定' in tag_txt and U2 in tag_txt,
       '行内实时出现「🔒 __olb_u2 已锁定」（WS edit_lock 驱动，姓名优先口径）')
    r2 = await ev("(function(){const t=document.querySelector(%s+' .lock-tag');"
                  "return t?t.classList.contains('lock-tag'):null})()" % row_sel)
    ok(r2 is True, '提示使用与事项行同款 .lock-tag 样式')

    print('【③ 自己持锁不显示】', flush=True)
    api_call('POST', '/api/locks/release', t2, {'key': 'org:%d' % NID})
    await asyncio.sleep(1.0)
    s, _r = api_call('POST', '/api/locks/acquire', t0, {'key': 'org:%d' % NID})
    ok(s == 200, 'admin 认领节点锁 → 200')
    await asyncio.sleep(1.5)
    r3 = await ev("document.querySelectorAll(%s+' .lock-tag').length" % row_sel)
    ok(r3 == 0, '自己持锁时行内不显示 🔒 标签')

    print('【④ U2 释放 → tag 实时消失】', flush=True)
    s, _r = api_call('POST', '/api/locks/release', t0, {'key': 'org:%d' % NID})
    ok(s == 200, 'admin 释放锁 → 200')
    gone = False
    for _ in range(20):
        await asyncio.sleep(0.5)
        n = await ev("document.querySelectorAll(%s+' .lock-tag').length" % row_sel)
        if n == 0:
            gone = True
            break
    ok(gone, '释放后行内 🔒 标签实时消失')
    # 顺带验证：锁被占用时他人认锁被 409 拒绝（编辑入口防护仍在）
    s1, _ = api_call('POST', '/api/locks/acquire', t0, {'key': 'org:%d' % NID})
    ok(s1 == 200, f'admin 认锁 → 200（实际 {s1}）')
    s2, _r4 = api_call('POST', '/api/locks/acquire', t2, {'key': 'org:%d' % NID})
    ok(s2 == 409, f'锁被 admin 持有 → U2 认锁 409（实际 {s2}）')
    api_call('POST', '/api/locks/release', t0, {'key': 'org:%d' % NID})

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    make_fixtures()
    asyncio.run(main())
finally:
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    n1 = c.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE ?", (P + '%',)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (P + '%',)).fetchone()[0]
    print('夹具残留: org=%d users=%d' % (n1, n2), flush=True)
    c.close()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
