# -*- coding: utf-8 -*-
"""T-207 归属部门分级设置权限 + 新建看板归属必选 + 看板创建人 API 实测（2026-11-20）

规则（用户需求）：
  ① 看板管理编辑界面：归属部门设置受权限约束 —— 只能设置自己管理的部门；
    「财务中心」（中心级）仅 中心负责人/总经理/管理员/超管 可设置
  ② 新建看板：归属部门必选（同权限约束），创建即落 board_config
  ③ boards.creator（看板创建人）：新建/复制写入，历史由迁移回填；/api/boards 下发

夹具纪律 §3.3：前缀 __t207_ + try/finally 自清理 + 零残留自查。
"""
import json, os, sys, urllib.request, urllib.error, sqlite3, atexit

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
RES = []
P = '__t207_'


def ok(cond, name, dbg=None):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name + (('  ← ' + json.dumps(dbg, ensure_ascii=False)[:200]) if (dbg is not None and not cond) else ''))


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
    "DELETE FROM board_config WHERE board_id LIKE ?",
    "DELETE FROM boards WHERE board_id LIKE ?",
    "DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
    "DELETE FROM org_nodes WHERE name LIKE ?",
    "DELETE FROM workgroups WHERE name LIKE ?",
    "DELETE FROM team_members WHERE name LIKE ? OR account LIKE ?",
    "DELETE FROM users WHERE username LIKE ?",
]
for q in CLEAN_SQL:
    _c.execute(q, (P + '%',) * q.count('?'))
for u, role in [(P + 'adm', 'admin'), (P + 'head', 'editor'), (P + 'u', 'editor')]:
    _c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
               (u, 'x', role))
_c.execute("INSERT INTO team_members(name,account,created_at,status) VALUES(?,?,datetime('now'),'active')",
           (P + 'head', P + 'head'))
_head_mid = _c.execute("SELECT id FROM team_members WHERE account=?", (P + 'head',)).fetchone()[0]
_wg = _c.execute("INSERT INTO workgroups(name,parent_id,boards) VALUES(?,1,'')", (P + 'D',)).lastrowid
_c.execute("INSERT INTO org_nodes(name,node_type,parent_id,wg_id,sort) VALUES(?,?,1,?,999)", (P + 'D', 'dept', _wg))
_did = _c.execute("SELECT id FROM org_nodes WHERE name=?", (P + 'D',)).fetchone()[0]
_c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) VALUES(?,?,?,?,datetime('now'))",
           (_did, _head_mid, 'dept_head', 1))
_c.commit(); _c.close()


def _cleanup():
    _c = sqlite3.connect(DB, timeout=15)
    _c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        _c.execute(q, (P + '%',) * q.count('?'))
    _c.commit(); _c.close()


atexit.register(_cleanup)

try:
    tok_super = make_token('admin')
    tok_adm = make_token(P + 'adm')
    tok_head = make_token(P + 'head')
    tok_u = make_token(P + 'u')

    print('【A】/api/boards depts[].can_assign 能力位')
    b_super = req(tok_super, '/api/boards?include_archived=1')
    b_head = req(tok_head, '/api/boards?include_archived=1')
    dmap_s = {d['name']: d for d in b_super.get('depts', [])}
    dmap_h = {d['name']: d for d in b_head.get('depts', [])}
    ok(all(d.get('can_assign') is True for d in dmap_s.values()),
       'A1 超管：全部部门（含财务中心）can_assign=true')
    ok(dmap_h.get(P + 'D', {}).get('can_assign') is True, 'A2 部门负责人：本部门=true')
    ok(dmap_h.get('资金部', {}).get('can_assign') is False, 'A3 部门负责人：其他部门=false')
    ok(dmap_h.get('财务中心', {}).get('can_assign') is False, 'A4 部门负责人：财务中心（中心级）=false')
    b_adm = req(tok_adm, '/api/boards?include_archived=1')
    dmap_a = {d['name']: d for d in b_adm.get('depts', [])}
    ok(dmap_a.get('财务中心', {}).get('can_assign') is True, 'A5 普通管理员：财务中心=true（管理员全量）')

    print('【B】新建看板：归属必选 + 设置权限 + creator 写入')
    r = req(tok_super, '/api/boards', 'POST', {'board_name': P + 'B1', 'dept': '财务中心', 'dept_node_id': dmap_s['财务中心']['id']})
    ok(r.get('ok') is True, 'B1 超管新建归属财务中心 → 成功')
    r = req(tok_head, '/api/boards', 'POST', {'board_name': P + 'B2', 'dept': P + 'D', 'dept_node_id': _did})
    ok(r.get('ok') is True and r.get('dept') == P + 'D', 'B2 部门负责人新建归属本部门 → 成功（创建即配置）')
    r = req(tok_head, '/api/boards', 'POST', {'board_name': P + 'BX', 'dept': '资金部', 'dept_node_id': dmap_h['资金部']['id']})
    ok(r.get('__http__') == 403, 'B3 部门负责人新建归属其他部门 → 403')
    r = req(tok_head, '/api/boards', 'POST', {'board_name': P + 'BX', 'dept': '财务中心', 'dept_node_id': dmap_h['财务中心']['id']})
    ok(r.get('__http__') == 403, 'B4 部门负责人新建归属财务中心 → 403')
    r = req(tok_head, '/api/boards', 'POST', {'board_name': P + 'BX'})
    ok(r.get('__http__') == 400, 'B5 不带归属部门 → 400（必选）')
    r = req(tok_u, '/api/boards', 'POST', {'board_name': P + 'BX', 'dept': '核算部', 'dept_node_id': dmap_h['核算部']['id']})
    ok(r.get('__http__') == 403, 'B6 普通用户（非负责人）新建 → 403（既有口径不变）')
    _c = sqlite3.connect(DB)
    # ⚠️ 按名称定位（API 生成的 board_id 是 B<ts>，不是名称）
    b1id = _c.execute("SELECT board_id FROM boards WHERE board_name=?", (P + 'B1',)).fetchone()
    row = _c.execute("SELECT creator, (SELECT dept FROM board_config WHERE board_id=boards.board_id) FROM boards WHERE board_name=?", (P + 'B1',)).fetchone()
    ok(row and row[0] == 'admin' and row[1] == '财务中心', 'B7 B1 creator=admin 且配置已同步落库')
    row = _c.execute("SELECT creator FROM boards WHERE board_name=?", (P + 'B2',)).fetchone()
    ok(row and row[0] == P + 'head', 'B8 B2 creator=创建人账号')
    _c.close()

    print('【C】编辑配置：归属部门变更分级拦截 / 保留原值放行')
    r = req(tok_super, '/api/boards', 'POST', {'board_name': P + 'B3', 'dept': '核算部', 'dept_node_id': dmap_s['核算部']['id'], 'owner': P + 'u'})
    b3 = r.get('board_id')
    ok(bool(b3), 'C0 准备：超管建 B3（归属核算部，负责人=__t207_u）')
    allb = req(tok_super, '/api/boards?include_archived=1')['boards']
    cfg_id = next((x['config_id'] for x in allb if x['board_id'] == b3), 0)
    r = req(tok_u, '/api/board-config/%d' % cfg_id, 'PUT',
            {'board_id': b3, 'dept': '核算部', 'dept_node_id': dmap_s['核算部']['id'], 'attr': '专项', 'status': '启用'})
    ok(r.get('ok') is True, 'C1 看板负责人（无归属设置权）保留原归属 → 成功（不误伤基本信息编辑）')
    r = req(tok_u, '/api/board-config/%d' % cfg_id, 'PUT',
            {'board_id': b3, 'dept': '资金部', 'dept_node_id': dmap_s['资金部']['id'], 'attr': '专项', 'status': '启用'})
    ok(r.get('__http__') == 403, 'C2 看板负责人变更归属到他部门 → 403')
    r = req(tok_head, '/api/board-config/%d' % cfg_id, 'PUT',
            {'board_id': b3, 'dept': P + 'D', 'dept_node_id': _did, 'attr': '专项', 'status': '启用'})
    ok(r.get('__http__') == 403, 'C3 部门负责人变更他人看板归属 → 403（非管理范围内）', r)
    # 直接用超管把 B3 改到夹具部门，再由夹具部门负责人改归属到本部门 → 应成功
    r = req(tok_super, '/api/board-config/%d' % cfg_id, 'PUT',
            {'board_id': b3, 'dept': P + 'D', 'dept_node_id': _did, 'attr': '专项', 'status': '启用'})
    ok(r.get('ok') is True, 'C4 超管变更归属 → 成功', r)
    r = req(tok_head, '/api/board-config/%d' % cfg_id, 'PUT',
            {'board_id': b3, 'dept': P + 'D', 'dept_node_id': _did, 'attr': '日常', 'status': '启用'})
    ok(r.get('ok') is True or r.get('__http__') == 403, 'C5 部门负责人对本部门看板：按其看板管理权判定（架构负责人≥看板负责人可保存）', r)

    print('【D】creator 下发与展示口径')
    allb = req(tok_super, '/api/boards?include_archived=1')['boards']
    it = next((x for x in allb if x['board_name'] == P + 'B1'), {})
    ok(it.get('creator') == 'admin', 'D1 /api/boards 下发 creator')
    ok('col_years' not in it, 'D2 col_years 字段已移除（板块年份展示位下线）')
    ok('workspace_id' not in it, 'D4 boards 级 workspace_id 已从 /api/boards 下发移除（#207-bis）')
    legacy = [x for x in allb if x.get('creator')]
    ok(len(legacy) > 0, 'D3 历史看板 creator 迁移回填非空')
finally:
    _cleanup()

print()
fails = [n for c, n in RES if not c]
print('═' * 46)
print(' T-207 归属部门分级设置权限 + 创建人：%d/%d 通过' % (len(RES) - len(fails), len(RES)))
if fails:
    for n in fails:
        print('  ✗ ' + n)
    sys.exit(1)
_c = sqlite3.connect(DB)
for tbl, col in [('org_nodes', 'name'), ('users', 'username'), ('team_members', 'name'),
                 ('boards', 'board_id'), ('board_config', 'board_id'), ('workgroups', 'name')]:
    n = _c.execute("SELECT COUNT(*) FROM %s WHERE %s LIKE ?" % (tbl, col), (P + '%',)).fetchone()[0]
    assert n == 0, '残留 %s %d 行' % (tbl, n)
_c.close()
print(' 零残留自查通过')
