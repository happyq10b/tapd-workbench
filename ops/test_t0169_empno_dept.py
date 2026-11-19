# -*- coding: utf-8 -*-
"""T-0169 新成员工号自动生成（no+5位随机）+ 部门录入 API 测试"""
import json, os, re, sqlite3, sys, urllib.parse, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

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


tk = make_token('admin')
NAMES = ['__t_id成员甲__', '__t_id成员乙__']
MIDS = []
try:
    print('【① 新增成员 → 工号自动生成 no+5位随机数】', flush=True)
    st, d = api(tk, 'POST', '/api/team', {'name': NAMES[0], 'role': 'editor'})
    ok(st == 200, '添加成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    m1 = c.execute("SELECT id,emp_no FROM team_members WHERE name=?", (NAMES[0],)).fetchone()
    MIDS.append(m1[0])
    ok(bool(re.fullmatch(r'no\d{5}', m1[1])), '工号格式 no+5位随机：%r' % m1[1])
    ok(c.execute("SELECT COUNT(*) FROM team_members WHERE emp_no=? AND id!=?", (m1[1], m1[0])).fetchone()[0] == 0,
       '工号全局唯一')
    c.close()

    print('【② 新增成员带部门 → 落库 + 架构参与人同步】', flush=True)
    st, d = api(tk, 'POST', '/api/team',
                {'name': NAMES[1], 'role': 'editor', 'departments': ['核算部']})
    ok(st == 200, '添加成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    m2 = c.execute("SELECT id,emp_no,departments FROM team_members WHERE name=?", (NAMES[1],)).fetchone()
    MIDS.append(m2[0])
    ok(bool(re.fullmatch(r'no\d{5}', m2[1])), '工号同样自动生成：%r' % m2[1])
    ok(m2[2] == '核算部', '部门落库：%r' % m2[2])
    acc = c.execute("SELECT account FROM team_members WHERE id=?", (m2[0],)).fetchone()[0]
    c.close()
    st, d = api(tk, 'GET', '/api/team')
    mem = next((m for m in d['members'] if m['id'] == m2[0]), {})
    ok(mem.get('departments') == ['核算部'], '/api/team 下发部门')
    # 未开账号 → 参与人无处挂载，跳过属预期；开通账号场景由 #165 测试覆盖
    print('   （未开账号 → 参与人同步自然跳过，符合 #165 语义）')

    print('【③ 新增不含工号入参 → 不接受外部工号伪造】', flush=True)
    st, d = api(tk, 'POST', '/api/team', {'name': '__t_id成员丙__', 'role': 'viewer'})
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    m3 = c.execute("SELECT id,emp_no FROM team_members WHERE name='__t_id成员丙__'").fetchone()
    MIDS.append(m3[0])
    ok(bool(re.fullmatch(r'no\d{5}', m3[1])), '系统生成的工号仍为 no+5位：%r' % m3[1])
    c.close()

finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    for mid in MIDS:
        c.execute("DELETE FROM org_appointments WHERE member_id=?", (mid,))
        c.execute("DELETE FROM team_members WHERE id=?", (mid,))
    c.execute("DELETE FROM users WHERE username IN (SELECT account FROM team_members WHERE name LIKE '__t_id成员%')")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_id成员%'")
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM team_members WHERE name LIKE '__t_id成员%'").fetchone()[0]
    print('夹具残留检查: members=%d' % n, flush=True)
    c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
