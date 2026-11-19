# -*- coding: utf-8 -*-
"""T-013e 离岗角色化 API 测试：role=departed 落库 / 名单剔除 / 登录拦截与文案 / 恢复"""
import json, os, sqlite3, sys, urllib.parse, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
RES = []


def ok(cond, msg):
    RES.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    path = urllib.parse.quote(path, safe='/?&=')
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk,
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def login(username, password):
    req = urllib.request.Request(BASE + '/api/login',
                                 data=json.dumps({'username': username, 'password': password}).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


MID, ACC, MNAME, PWD = 990415, '__t_lg3_u', '__t_离岗角色成员__', 'Xx12345678'
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA busy_timeout=5000')
node = c.execute("SELECT id,name FROM org_nodes WHERE node_type='dept' AND name NOT LIKE '__t_%' ORDER BY id LIMIT 1").fetchone()
NID = node['id']
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (ACC, hash_pw(PWD)))
c.execute("INSERT OR IGNORE INTO team_members (id,name,account,status) VALUES (?,?,?,'')", (MID, MNAME, ACC))
c.execute("INSERT OR IGNORE INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?, 'backbone',1)", (NID, MID))
c.commit(); c.close()

try:
    tk = make_token('admin')

    print('【① role=departed 保存 → users.role 与成员状态双落库 + 名单剔除】', flush=True)
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'role': 'departed'})
    ok(st == 200, '保存成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    ok(c.execute("SELECT role FROM users WHERE username=?", (ACC,)).fetchone()[0] == 'departed', 'users.role=departed')
    ok(c.execute("SELECT status FROM team_members WHERE id=?", (MID,)).fetchone()[0] == 'departed', '成员状态=离岗')
    ok(c.execute("SELECT COUNT(*) FROM org_appointments WHERE member_id=?", (MID,)).fetchone()[0] == 0, '任命已剔除')
    c.close()

    print('【② 登录拦截：正确密码也被拒，文案精确匹配】', flush=True)
    st, d = login(ACC, PWD)
    ok(st == 403, 'HTTP 403（实际 %s）' % st)
    ok((d.get('detail') or '') == '已不在本岗位，如需登入请联系管理员',
       '文案精确匹配：%r' % d.get('detail'))

    print('【③ role 切回 viewer → 恢复在岗，登录放行】', flush=True)
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'role': 'viewer'})
    ok(st == 200, '保存成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    ok(c.execute("SELECT status FROM team_members WHERE id=?", (MID,)).fetchone()[0] == '', '状态复位在岗')
    ok(c.execute("SELECT role FROM users WHERE username=?", (ACC,)).fetchone()[0] == 'viewer', 'users.role=viewer')
    ok(c.execute("SELECT COUNT(*) FROM org_appointments WHERE member_id=?", (MID,)).fetchone()[0] == 0, '名单不回填')
    c.close()
    st, d = login(ACC, PWD)
    ok(st == 200 and d.get('token'), '登录成功放行')

    print('【④ role=无权限（空串）也可解除离岗】', flush=True)
    api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'role': 'departed'})
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'role': ''})
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    ok(c.execute("SELECT status FROM team_members WHERE id=?", (MID,)).fetchone()[0] == '', '空角色 → 在岗')
    c.close()
    st, d = login(ACC, PWD)
    ok(st == 200, '登录放行')

finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE member_id=?", (MID,))
    c.execute("DELETE FROM team_members WHERE id=?", (MID,))
    c.execute("DELETE FROM users WHERE username=?", (ACC,))
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM team_members WHERE id=?", (MID,)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (ACC,)).fetchone()[0]
    print('夹具残留检查: members=%d users=%d' % (n1, n2), flush=True)
    c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
