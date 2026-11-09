# -*- coding: utf-8 -*-
"""#110 单点登录实测：新登录踢旧 token、多标签共享 token 不受影响、WS 收到强制下线。"""
import asyncio, json, os, sys, urllib.request, urllib.error, sqlite3

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'

RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

def login(u='admin', pw='At159357'):
    r = urllib.request.Request(BASE + '/api/login', method='POST',
        data=json.dumps({'username': u, 'password': pw}).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())

def req(tok, path, method='GET'):
    r = urllib.request.Request(BASE + path, method=method,
        headers={'Authorization': 'Bearer ' + tok})
    try:
        return urllib.request.urlopen(r, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code

print('【A】登录两次 → 旧 token 立即失效（会话代数）')
t1 = login()['token']
ok(req(t1, '/api/me') == 200, '第一次登录的 token 有效（200）')
t2 = login()['token']
ok(req(t1, '/api/me') == 401, '第二次登录后，旧 token 立即 401（被踢）')
ok(req(t2, '/api/me') == 200, '新 token 有效（后登录者正常使用）')

print('【B】同 token 多标签复用不受影响（单点 ≠ 单标签）')
for i in range(3):
    ok(req(t2, '/api/me') == 200, '同一 token 第 %d 次请求正常（模拟多标签页）' % (i + 1))

print('【C】再登录一次 → t2 也被踢（连续单点语义）')
t3 = login()['token']
ok(req(t2, '/api/me') == 401 and req(t3, '/api/me') == 200, 't2 失效、t3 有效')

print('【D】编辑锁链路在新 token 下不受影响')
import urllib.parse
me = json.loads(urllib.request.urlopen(urllib.request.Request(
    BASE + '/api/me', headers={'Authorization': 'Bearer ' + t3}), timeout=10).read())
bid = me['boards'][0]['board_id']
cid = 'SSO_PROBE_' + str(int(__import__('time').time() * 1000))
r = urllib.request.Request(BASE + '/api/cards', method='POST',
    data=json.dumps({'board_id': bid, 'card_name': '__sso_probe', 'column_name': '测试',
                     'created_at': '2026-11-09'}).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + t3})
try:
    urllib.request.urlopen(r, timeout=10)
except urllib.error.HTTPError as e:
    # 字段名不匹配时读 detail 便于诊断
    print('  create detail:', e.read().decode()[:120])
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
cid = con.execute("SELECT card_id FROM cards WHERE card_name='__sso_probe'").fetchone()
con.close()
if cid:
    cid = cid[0]
    ok(req(t3, '/api/cards/%s/lock' % cid, 'POST') == 200, '加锁成功（编辑锁不受单点影响）')
    ok(req(t3, '/api/cards/%s/lock' % cid, 'POST') == 200, '同用户重复加锁幂等（刷新页面场景）')
    ok(req(t3, '/api/cards/%s/unlock' % cid, 'POST') == 200, '解锁成功')
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    con.execute("DELETE FROM cards WHERE card_id=?", (cid,))
    con.commit(); con.close()
    ok(True, '测试卡清理完成')
else:
    ok(False, '测试卡未创建成功（检查 create 字段名）')

print('【E】WS 强制下线消息')
async def ws_probe():
    import websockets
    # 用 t3 连 WS，然后再次登录 → 旧 WS 应收到 force_logout
    ws = await websockets.connect('ws://127.0.0.1:8100/ws?token=' + urllib.parse.quote(t3))
    await asyncio.sleep(0.5)
    t4 = login()['token']
    msg = None
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
    except asyncio.TimeoutError:
        pass
    finally:
        await ws.close()
    return t4, msg
import urllib.parse
t4, msg = asyncio.run(ws_probe())
got = bool(msg) and json.loads(msg).get('type') == 'force_logout'
ok(got, '旧设备 WS 收到 force_logout（%s）' % (str(msg)[:60]))
ok(req(t3, '/api/me') == 401 and req(t4, '/api/me') == 200, 't3 已失效、t4 有效（WS 被踢的同时 token 也被换）')

print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
