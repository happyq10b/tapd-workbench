# -*- coding: utf-8 -*-
"""#111 在线用户管理实测：权限门禁 / 列表内容 / 强制下线即时生效 / 禁踢自己。"""
import json, os, sys, urllib.request, urllib.error, sqlite3, time

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
from app.app import make_token

RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

def login(u='admin', pw='At159357'):
    r = urllib.request.Request(BASE + '/api/login', method='POST',
        data=json.dumps({'username': u, 'password': pw}).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())

def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=10).read() or '{}')
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'detail': e.read().decode()[:120]}

sup = make_token('admin')                                     # 内置 admin（超级管理员）
# ⚠️ 不走真实登录：admin 正被用户浏览器使用时 /api/login 会 409（单点在线冲突，
#    app.py「该账号当前已在线」）。本测试的权限门禁/kick/重登路径都不依赖 admin 的
#    真实登录态 —— 列表时间/IP 取历史 last_login_at 即可，B 组断言口径不变。
adm = make_token('dsy')                                       # role=admin 普通管理账号（make_token 缺省取活跃代数）
# T-0191 清理遗留账号：不再借用建库期遗留的 zhangsan，改用自带夹具账号（atexit 清理）
import atexit
FIX_U = '__d111_u'
from app.app import hash_pw as _hp
_c = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db', timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
_c.execute("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
           (FIX_U, _hp('x'), 'editor'))
_c.commit(); _c.close()
atexit.register(lambda: (lambda _c: (_c.execute("DELETE FROM users WHERE username=?", (FIX_U,)),
                                     _c.commit(), _c.close()))(
    sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db', timeout=15)))
usr = make_token(FIX_U)                                       # 普通用户（自带夹具）
def login_as(u, pw='At159357'):                               # 真实登录（走 active_seq+1 路径）
    return login(u, pw)['token']

print('【A】权限门禁：仅超级管理员')
r = req(sup, '/api/admin/online')
ok('users' in r, '超管查询成功（%d 条记录）' % len(r.get('users', [])))
ok(req(adm, '/api/admin/online').get('__http__') == 403, '普通管理账号（dsy）→ 403')
ok(req(usr, '/api/admin/online').get('__http__') == 403, '普通用户（%s）→ 403' % FIX_U)

print('【B】列表内容：登录时间/IP/在线状态')
rows = {u['username']: u for u in req(sup, '/api/admin/online')['users']}
me_row = rows.get('admin')
ok(bool(me_row) and bool(me_row.get('login_at')), 'admin 有登录时间（%s）' % (me_row and me_row.get('login_at')))
ok(bool(me_row) and bool(me_row.get('ip')), 'admin 有 IP（%s）' % (me_row and me_row.get('ip')))
ok(bool(me_row) and isinstance(me_row.get('online'), bool) and me_row.get('ws_count') >= 0,
   'online/ws_count 字段存在（测试环境无浏览器 → ws_count=0 离线是正确行为）')
ok(all('login_at' in u and 'ip' in u and 'online' in u for u in rows.values()),
   '所有行字段完整（%d 个账号）' % len(rows))

print('【C】强制下线：即时生效 + 反馈')
# 目标：夹具账号的当前会话（usr token）→ kick → 立即 401
ok('username' in req(usr, '/api/me'), '夹具账号当前 token 有效')
r = req(sup, '/api/admin/online/kick', 'POST', {'username': FIX_U})
ok(r.get('ok') is True, 'kick 接口成功（反馈：%s）' % json.dumps(r, ensure_ascii=False)[:80])
import base64 as _b
_p = json.loads(_b.urlsafe_b64decode(usr.split('.')[0] + '=='))
import sqlite3 as _sq
_c = _sq.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
_dbg = _c.execute("SELECT active_seq FROM users WHERE username=?", (FIX_U,)).fetchone()[0]
_c.close()
print('  [debug] usr payload:', _p, '| DB %s seq:' % FIX_U, _dbg)
ok(req(usr, '/api/me').get('__http__') == 401, '被踢账号 token 立即 401（下线即时生效）')
ok(req(usr, '/api/me').get('__http__') == 401, '持续 401（不是瞬时抖动）')
ok(req(sup, '/api/admin/online/kick', 'POST', {'username': FIX_U}).get('ok') is True,
   '重复下线幂等成功（离线账号也可踢）')

print('【D】边界：禁踢自己 / 未知账号')
r = req(sup, '/api/admin/online/kick', 'POST', {'username': 'admin'})
ok(r.get('__http__') == 400, '踢自己 → 400（%s）' % r.get('detail', '')[:40])
r = req(sup, '/api/admin/online/kick', 'POST', {'username': '__nouser__'})
ok(r.get('__http__') == 404, '未知账号 → 404')
r = req(adm, '/api/admin/online/kick', 'POST', {'username': FIX_U})
ok(r.get('__http__') == 403, '普通管理账号调用 kick → 403（仅超管可操作）')

print('【E】被踢账号重新登录即恢复（用夹具账号验证登录路径，不占用 admin 的在线会话）')
t = login_as(FIX_U, 'x')
_tp = json.loads(_b.urlsafe_b64decode(t.split('.')[0] + '=='))
_c = _sq.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
_dbg2 = _c.execute("SELECT active_seq FROM users WHERE username='admin'").fetchone()[0]
_c.close()
r2 = req(t, '/api/me')
ok('username' in r2, '重新登录后正常使用（单点语义未破坏）')

print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
