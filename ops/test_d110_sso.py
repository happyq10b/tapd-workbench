# -*- coding: utf-8 -*-
"""#110 单点登录实测 v2（对齐 #113 新策略：先在线者占位，后来者拒绝）。"""
import json, os, sys, urllib.request, urllib.error, urllib.parse, sqlite3, time

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
TEST_USER = '__t110_%d' % (int(time.time()) % 100000)

RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

def login(u, pw='T110probe'):
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

sup = make_token('admin')
req(sup, '/api/admin/users', 'POST', {'username': TEST_USER, 'password': 'T110probe', 'role': 'viewer'})

print('【A】关浏览器场景：无 WS 连接 → 重复登录成功且旧 token 作废（seq+1）')
d1, c1 = login(TEST_USER)
ok(c1 == 200 and d1.get('token'), '第一次登录成功')
tok1 = d1['token']
d2, c2 = login(TEST_USER)
ok(c2 == 200 and d2.get('token'), '第二次登录成功（浏览器已关 = 无 WS = 不算在线）')
tok2 = d2['token']
ok(req(tok1, '/api/me')[1] == 401, '第一次登录的旧 token 已被 seq+1 作废（防 token 残留）')

print('【B】同 token 多标签复用不受影响（单点 ≠ 单标签）')
for i in range(3):
    ok(req(tok2, '/api/me')[1] == 200, '同一 token 第 %d 次请求正常' % (i + 1))

print('【C】超管强制下线 → 旧 token 立即失效（#111 kick 语义不变）')
rk, ck = req(sup, '/api/admin/online/kick', 'POST', {'username': TEST_USER})
ok(ck == 200 and rk.get('ok') is True, 'kick 成功')
ok(req(tok1, '/api/me')[1] == 401, '被踢后旧 token 立即 401')
d3, c3 = login(TEST_USER)
ok(c3 == 200, 'kick 解封后重新登录成功')

print('【D】make_token 兼容：运维/测试造的 token 仍有效')
tok_m = make_token(TEST_USER)
ok(req(tok_m, '/api/me')[1] == 200, 'make_token（自动活跃代数）有效')

print('【E】登录成功 seq+1（token 带当前活跃代数）')
import base64 as b
_p = json.loads(b.urlsafe_b64decode(d3['token'].split('.')[0] + '=='))
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
_db = con.execute("SELECT active_seq FROM users WHERE username=?", (TEST_USER,)).fetchone()[0]
con.close()
ok(_p.get('s') == _db, 'token.s=%s = DB active_seq=%s' % (_p.get('s'), _db))

# 清理
req(sup, '/api/admin/users/' + TEST_USER, 'DELETE')
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
n = con.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t110%'").fetchone()[0]
con.close()
ok(n == 0, '临时账号清理完成')

print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
