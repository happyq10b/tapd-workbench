# -*- coding: utf-8 -*-
"""#165 部门字段三处联动 API 测试
① 个人界面 /api/profile 保存部门（校验 + 回显）
② 账号管理 PUT /api/team/{mid} 修改部门（管理员）→ 同步覆盖个人界面数据
③ 强映射：部门选择 ↔ org_nodes.participants；财务中心参与人=全员
夹具：__t_d165_ 前缀 + finally 清理（删全相关表）；断言用相对基线。
"""
import io, json, os, sqlite3, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk,
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        raw = r.read()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def cleanup(c):
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE '__t_d165%')")
    c.execute("DELETE FROM org_nodes WHERE name LIKE '__t_d165%'")
    c.execute("DELETE FROM workgroups WHERE name LIKE '__t_d165%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_d165%'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_d165%' OR account LIKE '__t_d165%'")
    c.commit()


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cleanup(conn)

# ---------- 夹具：两个一级节点（中心+中心）+ 两个部门 + 两名成员 ----------
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165中心A','center',0,9001,'')")
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165中心B','center',0,9002,'')")
ca = conn.execute("SELECT id FROM org_nodes WHERE name='__t_d165中心A'").fetchone()[0]
cb = conn.execute("SELECT id FROM org_nodes WHERE name='__t_d165中心B'").fetchone()[0]
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165部甲','dept',?,9003,'')", (ca,))
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165部乙','dept',?,9004,'')", (cb,))
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t_d165_u1',?,'viewer')", (hash_pw('Xx12345678'),))
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t_d165_u2',?,'viewer')", (hash_pw('Xx12345678'),))
conn.execute("INSERT INTO team_members (name,account) VALUES ('__t_d165成员甲','__t_d165_u1')")
conn.execute("INSERT INTO team_members (name,account) VALUES ('__t_d165成员乙','__t_d165_u2')")
conn.commit()
mid1 = conn.execute("SELECT id FROM team_members WHERE name='__t_d165成员甲'").fetchone()[0]
mid2 = conn.execute("SELECT id FROM team_members WHERE name='__t_d165成员乙'").fetchone()[0]
conn.close()

tk_admin = make_token('admin')
tk_u1 = make_token('__t_d165_u1')
tk_u2 = make_token('__t_d165_u2')

try:
    print('【① /api/me 下发部门与选项】', flush=True)
    st, me = api(tk_u1, 'GET', '/api/me')
    ok(st == 200 and me.get('departments') == [], '个人界面初始部门为空')
    opts = me.get('dept_options') or []
    names = [o['name'] for o in opts]
    ok('__t_d165部甲' in names and '__t_d165中心A' in names, '选项含前两级节点（中心+部门）：%s' % names)
    ok(all(o['node_type'] in ('center', 'dept') for o in opts), '选项不含小组层')

    print('【② 个人界面保存部门 + 校验】', flush=True)
    st, d = api(tk_u1, 'POST', '/api/profile',
                {'departments': ['__t_d165部甲', '__t_d165中心A'], 'gender': ''})
    ok(st == 200 and sorted(d.get('departments') or []) == ['__t_d165中心A', '__t_d165部甲'],
       '保存成功并回显：%s' % d.get('departments'))
    st, d = api(tk_u1, 'POST', '/api/profile', {'departments': ['__t_d165不存在的部门']})
    ok(st == 400, '未知部门 → 400：%s' % d.get('detail'))
    st, me = api(tk_u1, 'GET', '/api/me')
    ok(sorted(me.get('departments') or []) == ['__t_d165中心A', '__t_d165部甲'], '非法提交不落库，/api/me 保持原值')

    print('【③ 强映射：参与人同步】', flush=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    p甲 = c.execute("SELECT participants FROM org_nodes WHERE name='__t_d165部甲'").fetchone()[0]
    p乙 = c.execute("SELECT participants FROM org_nodes WHERE name='__t_d165部乙'").fetchone()[0]
    ok('__t_d165_u1' in (p甲 or '').split(','), '选中部门甲 → 参与人含 u1')
    ok('__t_d165_u1' not in (p乙 or '').split(','), '未选部门乙 → 参与人不含 u1')
    pc = c.execute("SELECT participants FROM org_nodes WHERE id=?", (ca,)).fetchone()[0]
    # 2026-11-12 口径对齐 T-013c：中心参与人=全员指「在职全员」——离岗成员（departed）
    # 按用户确认的规则不补（丁璇 2026-11-10 确认「离岗不回流」），断言同步排除。
    all_accs = [r[0] for r in c.execute(
        "SELECT account FROM team_members WHERE account!='' AND IFNULL(status,'')!='departed'")]
    missing = [a for a in all_accs if a not in (pc or '').split(',')]
    ok(not missing, '财务中心型中心节点参与人=在职全员（缺：%s）' % missing)

    print('【④ 取消部门 → 参与人移除】', flush=True)
    api(tk_u1, 'POST', '/api/profile', {'departments': ['__t_d165部乙']})
    p甲 = c.execute("SELECT participants FROM org_nodes WHERE name='__t_d165部甲'").fetchone()[0]
    p乙 = c.execute("SELECT participants FROM org_nodes WHERE name='__t_d165部乙'").fetchone()[0]
    ok('__t_d165_u1' not in (p甲 or '').split(','), '取消甲 → 参与人移除 u1')
    ok('__t_d165_u1' in (p乙 or '').split(','), '改选乙 → 参与人加入 u1')
    c.close()

    print('【⑤ 账号管理改部门 → 个人界面同步】', flush=True)
    st, d = api(tk_admin, 'PUT', '/api/team/%d' % mid1, {'name': '__t_d165成员甲', 'departments': ['__t_d165部甲']})
    ok(st == 200, '管理员修改部门成功')
    st, me = api(tk_u1, 'GET', '/api/me')
    ok(me.get('departments') == ['__t_d165部甲'], '个人界面读回账号管理的修改：%s' % me.get('departments'))
    st, d = api(tk_u1, 'POST', '/api/profile', {'departments': ['__t_d165中心A']})
    st, team = api(tk_admin, 'GET', '/api/team')
    m1 = next(m for m in team['members'] if m['id'] == mid1)
    ok(m1.get('departments') == ['__t_d165中心A'], '账号管理读回个人界面的修改：%s' % m1.get('departments'))

    print('【⑥ 越权与非管理员防护】', flush=True)
    st, d = api(tk_u2, 'PUT', '/api/team/%d' % mid2, {'name': '__t_d165成员乙', 'departments': ['__t_d165部甲']})
    ok(st == 403, '非管理员改他人部门 → 403')
    st, d = api(tk_u2, 'POST', '/api/profile', {'departments': ['__t_d165部甲', '__t_d165部乙']})
    ok(st == 200, '本人仍可改自己的部门（个人界面权限不变）')

    print('【⑦ 无账号成员保存部门被拒（无处映射）】', flush=True)
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO team_members (name,account) VALUES ('__t_d165成员丙','')")
    c.commit()
    c.close()
    # 无账号成员没有登录态 —— 用 admin 直接写该行验证接口侧拒绝路径不可行（profile 是本人接口），
    # 账号管理接口对无账号成员仍可设置部门（列在成员上），验证写入成功即可：
    c = sqlite3.connect(DB)
    mid3 = c.execute("SELECT id FROM team_members WHERE name='__t_d165成员丙'").fetchone()[0]
    c.close()
    st, d = api(tk_admin, 'PUT', '/api/team/%d' % mid3, {'name': '__t_d165成员丙', 'departments': ['__t_d165部甲']})
    ok(st == 200, '无账号成员也可在账号管理设置部门（列在成员维度）')
finally:
    conn = sqlite3.connect(DB)
    cleanup(conn)
    conn.close()
    print('cleanup done（残留自查：见下方）', flush=True)
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE '__t_d165%'").fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM team_members WHERE name LIKE '__t_d165%'").fetchone()[0]
    n3 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t_d165%'").fetchone()[0]
    print('残留: nodes=%d members=%d users=%d' % (n, n2, n3), flush=True)
    c.close()

total = len(PASSED)
good = sum(PASSED)
print('结果: %d/%d' % (good, total), flush=True)
sys.exit(0 if good == total else 1)
