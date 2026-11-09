# -*- coding: utf-8 -*-
"""#113 登录策略实测（干净版）：先在线者占位、后来者拒绝、kick 解封闭环。"""
import json, os, sys, urllib.request, urllib.error, urllib.parse, sqlite3, time, asyncio

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DENY_MSG = '该账号当前已在线。如非本人操作，请联系超级管理员将该用户强制下线后再试'
TEST_USER = '__t113_%d' % (int(time.time()) % 100000)   # 随机后缀，防残留冲突

RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

def login(u, pw='T113probe'):
    r = urllib.request.Request(BASE + '/api/login', method='POST',
        data=json.dumps({'username': u, 'password': pw}).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=10).read() or '{}'), 200
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or '{}'), e.code

def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=10).read() or '{}'), 200
    except urllib.error.HTTPError as e:
        return e.read().decode()[:120], e.code

async def open_ws(tok):
    import websockets
    return await websockets.connect('ws://127.0.0.1:8100/ws?token=' + urllib.parse.quote(tok))

async def main():
    sup = make_token('admin')
    r0, c0 = req(sup, '/api/admin/online')
    ok(c0 == 200, 'make_token 造的超管 token 可调管理接口')

    print('【A】无在线会话 → 登录成功')
    d, c = req(sup, '/api/admin/users', 'POST', {'username': TEST_USER, 'password': 'T113probe', 'role': 'viewer'})
    print('  创建 %s: %s' % (TEST_USER, c))
    d1, code1 = login(TEST_USER)
    ok(code1 == 200 and d1.get('token'), '新账号登录成功（无 WS 连接时不受影响）')
    tok1 = d1['token']

    print('【B】该账号 WS 在线 → 后来者登录被拒 + 文案精确')
    ws1 = await open_ws(tok1)
    await asyncio.sleep(0.6)
    d2, code2 = login(TEST_USER)
    ok(code2 == 409, '后来者登录 → 409')
    ok(d2.get('detail') == DENY_MSG, '拒绝文案精确匹配用户要求 ✓')
    r1, _ = req(tok1, '/api/me')
    ok('username' in r1, '先登录者不受影响（仍在线可用）')

    print('【C】WS 断开（关浏览器）→ 立即可再登录')
    # 模拟真实「关浏览器」：进程退出 = TCP RST/FIN（不是优雅 close frame——
    # 实测 websockets 库的优雅 close 服务端感知延迟可达 6s+，真实场景是 abort）
    ws1.transport.abort()
    _t0 = time.time()
    for _ in range(50):
        _u, _ = req(sup, '/api/admin/online')
        _cnt = [x.get('ws_count') for x in (_u.get('users') or []) if x.get('username') == TEST_USER]
        if (_cnt or [0])[0] == 0 or not _cnt:
            break
        await asyncio.sleep(0.2)
    _dt = time.time() - _t0
    print('  [debug] 服务端感知断开耗时 %.1fs，ws_count=%s' % (_dt, _cnt))
    ok(_dt < 3, '服务端 3s 内感知断开（真实关浏览器路径）')
    d3, code3 = login(TEST_USER)
    ok(code3 == 200, 'WS 断开后 → 登录放行')

    print('【D】登录成功后自己在线 → 再次登录同样被拒（自占位）')
    ws2 = await open_ws(d3['token'])  # 保持打开 → E 段 kick 应断开它
    await asyncio.sleep(0.6)
    d4, code4 = login(TEST_USER)
    ok(code4 == 409, '重复登录被拒（自己占位也算在线）')

    print('【E】超管强制下线解封闭环')
    rk, codek = req(sup, '/api/admin/online/kick', 'POST', {'username': TEST_USER})
    ok(codek == 200 and isinstance(rk, dict) and rk.get('ok') is True and rk.get('ws_kicked', 0) >= 1,
       '超管强制下线成功（断开 %s 条 WS）' % (rk.get('ws_kicked') if isinstance(rk, dict) else '?'))
    d7, code7 = login(TEST_USER)
    ok(code7 == 200, 'kick 后后来者登录放行（解封闭环）')

    print('【F】被踢者旧 token 立即失效（#111 语义未回归）')
    r4, code4f = req(d3['token'], '/api/me')
    ok(code4f == 401, '被踢会话原 token 立即 401（seq+1 生效）')

    # 清理临时账号
    req(sup, '/api/admin/users/' + TEST_USER, 'DELETE')
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    left = con.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t113%'").fetchone()[0]
    con.close()
    ok(left == 0, '临时账号清理完成（残留 %s 个）' % left)

asyncio.run(main())
print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
