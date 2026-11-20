# -*- coding: utf-8 -*-
"""T-206 架构删除分级权限 + 【未配置架构】集中展示 API 实测（2026-11-20）

规则（用户需求）：
  ① center（财务中心等顶层架构）任何角色不可删除（前端不渲染删除键）
  ② dept（部门层大架构）仅超级管理员可删（普通管理员/部门负责人均无权）
  ③ group（小组层）超管/管理员/本部门负责人（祖先链判定）可删；组长与普通用户无权
  ④ /api/org/tree 下发 can_delete_node 能力位 + unassigned_boards（归属部门缺失看板）

夹具纪律 §3.3：前缀 __t206_ + try/finally 自清理 + 零残留自查。
"""
import json, os, sys, urllib.request, urllib.error, sqlite3, atexit

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
RES = []
P = '__t206_'


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=15).read() or '{}')
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'detail': (e.read().decode() or '')[:160]}


# ---------------- 夹具搭建 ----------------
_c = sqlite3.connect(DB, timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
CLEAN_SQL = [
    "DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
    "DELETE FROM org_nodes WHERE name LIKE ?",
    "DELETE FROM workgroups WHERE name LIKE ?",
    "DELETE FROM team_members WHERE name LIKE ? OR account LIKE ?",
    "DELETE FROM users WHERE username LIKE ?",
    "DELETE FROM boards WHERE board_id LIKE ?",
]
for q in CLEAN_SQL:
    _c.execute(q, (P + '%',) * q.count('?'))
# 账号：普通管理员 / 部门负责人 / 组长 / 普通用户
for u, role in [(P + 'adm', 'admin'), (P + 'head', 'editor'),
                (P + 'leader', 'editor'), (P + 'u', 'editor')]:
    _c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
               (u, 'x', role))
# 团队成员（架构任命载体；account 与登录账号同键）
for name, acct in [(P + 'head', P + 'head'), (P + 'leader', P + 'leader')]:
    _c.execute("INSERT INTO team_members(name,account,created_at,status) VALUES(?,?,datetime('now'),'active')",
               (name, acct))
_head_mid = _c.execute("SELECT id FROM team_members WHERE account=?", (P + 'head',)).fetchone()[0]
_leader_mid = _c.execute("SELECT id FROM team_members WHERE account=?", (P + 'leader',)).fetchone()[0]
# 架构夹具：部门（挂财务中心 id=1）+ 两个小组；workgroups.wg_id 非空 → 配套建 wg 行
_wgD = _c.execute("INSERT INTO workgroups(name,parent_id,boards) VALUES(?,1,'')", (P + 'D',)).lastrowid
_c.execute("INSERT INTO org_nodes(name,node_type,parent_id,wg_id,sort) VALUES(?,?,1,?,999)", (P + 'D', 'dept', _wgD))
_did = _c.execute("SELECT id FROM org_nodes WHERE name=?", (P + 'D',)).fetchone()[0]
for nm in (P + 'G1', P + 'G2'):
    _wg = _c.execute("INSERT INTO workgroups(name,parent_id,boards) VALUES(?,?,'')", (nm, _wgD)).lastrowid
    _c.execute("INSERT INTO org_nodes(name,node_type,parent_id,wg_id,sort) VALUES(?,?,{},?,999)".format(_did),
               (nm, 'group', _wg))
_gid1 = _c.execute("SELECT id FROM org_nodes WHERE name=?", (P + 'G1',)).fetchone()[0]
_gid2 = _c.execute("SELECT id FROM org_nodes WHERE name=?", (P + 'G2',)).fetchone()[0]
# 任命：部门长（夹具部门）+ 组长（夹具小组 G1）
_c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) VALUES(?,?,?,?,datetime('now'))",
           (_did, _head_mid, 'dept_head', 1))
_c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) VALUES(?,?,?,?,datetime('now'))",
           (_gid1, _leader_mid, 'group_leader', 1))
# 未配置归属部门的看板（不写 board_config → unassigned）
_c.execute("INSERT INTO boards(board_id,board_name,owner,participants,archived,created_at,sort) VALUES(?,?, '', '', 0, datetime('now'), 0)",
           (P + 'B', P + '看板'))
_c.commit(); _c.close()


def _cleanup():
    _c = sqlite3.connect(DB, timeout=15)
    _c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        _c.execute(q, (P + '%',) * q.count('?'))
    _c.commit(); _c.close()


atexit.register(_cleanup)

try:
    tok_super = make_token('admin')             # 超级管理员
    tok_adm = make_token(P + 'adm')             # 普通管理员（role=admin）
    tok_head = make_token(P + 'head')           # 部门负责人（夹具部门 dept_head）
    tok_leader = make_token(P + 'leader')       # 组长（夹具小组 G1 group_leader）
    tok_u = make_token(P + 'u')                 # 普通用户

    print('【A】tree 能力位 can_delete_node')
    t_super = req(tok_super, '/api/org/tree')
    t_head = req(tok_head, '/api/org/tree')
    t_leader = req(tok_leader, '/api/org/tree')
    t_u = req(tok_u, '/api/org/tree')

    def _flatten(tree):
        out = {}
        def walk(ns):
            for n in ns or []:
                out[n['name']] = n
                walk(n.get('children'))
        walk(tree)
        return out

    flat_s = _flatten(t_super.get('tree', []))
    flat_h = _flatten(t_head.get('tree', []))
    flat_l = _flatten(t_leader.get('tree', []))
    flat_u = _flatten(t_u.get('tree', []))
    ctr = flat_s.get('财务中心', {})
    ok(ctr.get('can_delete_node') is False, 'A1 超管视角：center（财务中心）can_delete_node=false')
    dept_n = flat_s.get(P + 'D', {})
    ok(dept_n.get('can_delete_node') is True, 'A2 超管视角：dept can_delete_node=true（仅超管可删）')
    ok(flat_s.get(P + 'G1', {}).get('can_delete_node') is True, 'A3 超管视角：group can_delete_node=true')
    ok(flat_h.get(P + 'D', {}).get('can_delete_node') is False, 'A4 部门负责人视角：dept=false（部门层仅超管）')
    ok(flat_h.get(P + 'G1', {}).get('can_delete_node') is True, 'A5 部门负责人视角：本部门小组=true')
    ok(flat_h.get('成本组', {}).get('can_delete_node') is False, 'A6 部门负责人视角：其他部门小组=false（防跨部门越权）')
    ok(flat_h.get('核算部', {}).get('can_delete_node') is False, 'A7 部门负责人视角：其他部门=false')
    ok(flat_l.get(P + 'G1', {}).get('can_delete_node') is False, 'A8 组长视角：自己的组=false（组长非架构负责人）')
    ok(flat_u.get(P + 'G1', {}).get('can_delete_node') is False, 'A9 普通用户视角：group=false')

    print('【B】unassigned_boards 下发')
    unb = {b['board_id']: b for b in t_super.get('unassigned_boards', [])}
    ok(P + 'B' in unb, 'B1 超管：未配置归属部门的夹具看板出现在【未配置架构】清单')
    ok(unb.get(P + 'B', {}).get('can_delete') is True, 'B2 夹具看板 can_delete=true（超管）')
    ok(all(not b['board_id'].startswith(P) or b['board_id'] == P + 'B'
           for b in t_super.get('unassigned_boards', [])), 'B3 无其他夹具残留')
    _hb = {b['board_id']: b for b in t_head.get('unassigned_boards', [])}
    # 未配置归属部门 = 公共看板（user_allowed 既有口径：所有人可见，侧栏「未配置」分组同源）
    # → 部门负责人可见是正确行为；关键约束是 can_delete=false（无删除权）
    ok(_hb.get(P + 'B', {}).get('can_delete') is False,
       'B4 部门负责人：未配置看板可见（公共看板口径）但 can_delete=false')

    print('【C】删除矩阵（端点强校验）')
    r = req(tok_super, '/api/org/nodes/1', 'DELETE')
    ok(r.get('__http__') == 403, 'C1 超管删 center（财务中心）→ 403（顶层架构不可删）')
    r = req(tok_leader, '/api/org/nodes/%d' % _gid1, 'DELETE')
    ok(r.get('__http__') == 403, 'C2 组长删自己的小组 → 403')
    r = req(tok_u, '/api/org/nodes/%d' % _gid1, 'DELETE')
    ok(r.get('__http__') == 403, 'C3 普通用户删小组 → 403')
    cost_gid = None
    for n in flat_s.values():
        if n['name'] == '成本组':
            cost_gid = n['id']
    r = req(tok_head, '/api/org/nodes/%d' % cost_gid, 'DELETE')
    ok(r.get('__http__') == 403, 'C4 部门负责人删其他部门小组 → 403（分级负责）')
    r = req(tok_head, '/api/org/nodes/%d' % _gid2, 'DELETE')
    ok(r.get('ok') is True, 'C5 部门负责人删本部门小组 → 成功')
    r = req(tok_adm, '/api/org/nodes/%d' % _did, 'DELETE')
    ok(r.get('__http__') == 403, 'C6 普通管理员删部门 → 403（部门层仅超管）')
    r = req(tok_adm, '/api/org/nodes/%d' % _gid1, 'DELETE')
    ok(r.get('ok') is True, 'C7 普通管理员删小组 → 成功（管理员全量权限）')
    r = req(tok_super, '/api/org/nodes/%d' % _did, 'DELETE')
    ok(r.get('ok') is True, 'C8 超管删部门 → 成功')

    print('【D】看板删除走原口径（未配置看板经架构管理入口）')
    r = req(tok_u, '/api/boards/' + P + 'B', 'DELETE')
    ok(r.get('__http__') in (403, 401), 'D1 普通用户删看板 → 拒绝（看板负责人及以上口径不变）')
finally:
    _cleanup()

print()
fails = [n for c, n in RES if not c]
print('═' * 46)
print(' T-206 架构删除分级权限 + 未配置架构：%d/%d 通过' % (len(RES) - len(fails), len(RES)))
if fails:
    for n in fails:
        print('  ✗ ' + n)
    sys.exit(1)
# 零残留自查（夹具纪律 §3.3）
_c = sqlite3.connect(DB)
for tbl, col in [('org_nodes', 'name'), ('users', 'username'),
                 ('team_members', 'name'), ('boards', 'board_id')]:
    n = _c.execute("SELECT COUNT(*) FROM %s WHERE %s LIKE ?" % (tbl, col), (P + '%',)).fetchone()[0]
    assert n == 0, '残留 %s %d 行' % (tbl, n)
_c.close()
print(' 零残留自查通过')
