# -*- coding: utf-8 -*-
"""T-211 综合看板 API 实测（2026-11-24）

规则（用户需求）：
  ① 默认可见 = 部门长/总经理/中心负责人/管理员/超管；综合编辑仅默认可见人员
  ② 追加人员（综合编辑配置）可见综合看板但不可编辑；候选必须在本架构子树下
    （center 型不限，跨部门不可选）
  ③ 配置持久化：syn_board_config（columns 白名单 + extra_members）
  ④ 数据端点：/api/syn-boards 数据权限仍走 user_allowed（综合模式不越权）

夹具纪律 §3.3：前缀 __t211_ + try/finally 自清理 + 零残留自查。
运行约定：从项目根运行；服务须 8100 在线。
"""
import json, os, sys, urllib.request, urllib.error, sqlite3, atexit

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
RES = []
P = '__t211_'


def ok(cond, name, dbg=None):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name + (('  ← ' + json.dumps(dbg, ensure_ascii=False)[:220]) if (dbg is not None and not cond) else ''))


def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=15).read() or '{}')
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'detail': (e.read().decode() or '')[:200]}


# ---------------- 夹具搭建 ----------------
_c = sqlite3.connect(DB, timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
CLEAN_SQL = [
    "DELETE FROM syn_board_config WHERE dept_node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
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
for u in (P + 'ch', P + 'dh', P + 'u1', P + 'u2'):
    _c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?, 'editor',1)", (u, 'x'))
for nm in (P + 'ch', P + 'dh', P + 'u1', P + 'u2'):
    _c.execute("INSERT INTO team_members(name,account,created_at,status) VALUES(?,?,datetime('now'),'active')", (nm, nm))
_mid = {nm: _c.execute("SELECT id FROM team_members WHERE account=?", (nm,)).fetchone()[0]
        for nm in (P + 'ch', P + 'dh', P + 'u1', P + 'u2')}
# 架构：夹具 center C（任命 ch=center_head）→ dept D（任命 dh=dept_head）→ 子成员 u1
_cid = _c.execute("INSERT INTO org_nodes(name,node_type,parent_id,sort) VALUES(?, 'center', 0, 990)", (P + 'C',)).lastrowid
_did = _c.execute("INSERT INTO org_nodes(name,node_type,parent_id,sort) VALUES(?, 'dept', ?, 991)", (P + 'D', _cid)).lastrowid
_d2id = _c.execute("INSERT INTO org_nodes(name,node_type,parent_id,sort) VALUES(?, 'dept', ?, 992)", (P + 'D2', _cid)).lastrowid
for nid, mid, rk in [(_cid, _mid[P + 'ch'], 'center_head'), (_did, _mid[P + 'dh'], 'dept_head'),
                     (_did, _mid[P + 'u1'], 'member'), (_d2id, _mid[P + 'u2'], 'member')]:
    _c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) "
               "VALUES(?,?,?,1,datetime('now'))", (nid, mid, rk))
# 夹具看板：B1 挂 D；B2 挂 D2（跨部门对照）
for bid, dnid in [(P + 'B1', _did), (P + 'B2', _d2id)]:
    _c.execute("INSERT INTO boards(board_id,board_name,owner,participants,creator,archived,created_at,sort) "
               "VALUES(?,'','', '', 'admin',0,datetime('now'),0)", (bid,))
    _c.execute("INSERT INTO board_config(board_id,dept,dept_node_id,attr,status) "
               "VALUES(?, '测试部门', ?, '日常','启用')", (bid, dnid))
_c.commit(); _c.close()


def _cleanup():
    _c = sqlite3.connect(DB, timeout=15)
    _c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        _c.execute(q, (P + '%',) * q.count('?'))
    _c.commit()
    n = sum(_c.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE ?", (P + '%',)).fetchone()[0]
            for _ in (0,))
    n += _c.execute("SELECT COUNT(*) FROM syn_board_config WHERE dept_node_id NOT IN (SELECT id FROM org_nodes)").fetchone()[0]
    _c.close()
    print('零残留自查: %s（孤儿配置 %d）' % ('PASS' if n == 0 else '✗ FAIL', n))


atexit.register(_cleanup)

try:
    tok_adm = make_token('admin')
    tok_ch = make_token(P + 'ch')
    tok_dh = make_token(P + 'dh')
    tok_u1 = make_token(P + 'u1')
    tok_u2 = make_token(P + 'u2')

    print('【A】能力位（/api/me）')
    me_adm = req(tok_adm, '/api/me')
    me_dh = req(tok_dh, '/api/me')
    me_u1 = req(tok_u1, '/api/me')
    ok(len(me_adm.get('syn_edit_depts', [])) > 0, 'A1 超管 syn_edit_depts 非空')
    ok(int(me_dh.get('syn_depts', []) and P and 0) == 0 and str(me_dh.get('syn_depts')) .find(str(_did)) >= 0,
       'A2 部门长 syn_depts 含本部门', me_dh.get('syn_depts'))
    ok(str(me_dh.get('syn_edit_depts')).find(str(_did)) >= 0, 'A3 部门长 syn_edit_depts 含本部门（可编辑）')
    ok(str(me_dh.get('syn_depts')).find(str(_d2id)) < 0, 'A4 部门长不跨部门（D2 不在集合）')
    ok(str(me_u1.get('syn_depts')).find(str(_did)) < 0, 'A5 普通成员未追加 → syn_depts 不含本部门')

    print('【B】配置读写与持久化')
    r = req(tok_adm, '/api/syn-config?dept_node_id=%d' % _did)
    ok(r.get('can_edit') is True, 'B1 超管读取 can_edit=True', r)
    ok(r.get('dept_name') == P + 'D', 'B2 返回部门名')
    r = req(tok_dh, '/api/syn-config?dept_node_id=%d' % _did)
    ok(r.get('can_edit') is True and len(r.get('candidates', [])) > 0,
       'B3 部门长读取 can_edit=True 且候选含子树成员', [c['account'] for c in r.get('candidates', [])])
    r = req(tok_u1, '/api/syn-config?dept_node_id=%d' % _did)
    ok(r.get('__http__') == 403, 'B4 未追加普通成员读取 → 403')
    r = req(tok_adm, '/api/syn-config/%d' % _did, 'PUT',
            {'columns': P + 'B1', 'extra_members': P + 'u1'})
    ok(r.get('ok') is True, 'B5 超管保存配置（白名单+追加）')
    r = req(tok_adm, '/api/syn-config?dept_node_id=%d' % _did)
    ok(r.get('columns') == [P + 'B1'] and r.get('extra_members') == [P + 'u1'],
       'B6 配置回读（持久化）', r)
    me_u1 = req(tok_u1, '/api/me')
    ok(str(me_u1.get('syn_depts')).find(str(_did)) >= 0, 'B7 追加后 u1 syn_depts 含本部门')
    ok(str(me_u1.get('syn_edit_depts')).find(str(_did)) < 0, 'B8 追加人员不在 syn_edit_depts（不可编辑）')
    r = req(tok_u1, '/api/syn-config/%d' % _did, 'PUT', {'columns': '', 'extra_members': ''})
    ok(r.get('__http__') == 403, 'B9 追加人员保存配置 → 403')
    r = req(tok_u2, '/api/syn-config?dept_node_id=%d' % _did)
    ok(r.get('__http__') == 403, 'B10 其他部门成员读取 → 403')

    print('【C】追加候选范围（跨部门约束）')
    r = req(tok_dh, '/api/syn-config?dept_node_id=%d' % _did)
    cands = {c['account'] for c in r.get('candidates', [])}
    ok(P + 'u1' in cands, 'C1 候选含本架构子树成员 u1')
    ok(P + 'u2' not in cands, 'C2 候选不含跨部门成员 u2')
    r = req(tok_dh, '/api/syn-config/%d' % _did, 'PUT', {'columns': '', 'extra_members': P + 'u2'})
    ok(r.get('__http__') == 400, 'C3 跨部门追加 → 400', r)

    print('【D】板块白名单校验')
    r = req(tok_dh, '/api/syn-config/%d' % _did, 'PUT', {'columns': P + 'B2', 'extra_members': ''})
    ok(r.get('__http__') == 400, 'D1 白名单含其他部门看板 → 400', r)
    r = req(tok_dh, '/api/syn-config/%d' % _did, 'PUT',
            {'columns': P + 'B1', 'extra_members': P + 'u1'})
    ok(r.get('ok') is True, 'D2 部门长保存本部门看板白名单 → 200')

    print('【E】综合数据端点（模式数据 + 不越权）')
    r = req(tok_adm, '/api/syn-boards?dept_node_id=%d' % _did)
    ok([b['board_id'] for b in r.get('boards', [])] == [P + 'B1'], 'E1 admin 按白名单返回子树看板', r)
    r = req(tok_u2, '/api/syn-boards?dept_node_id=%d' % _did)
    ok(r.get('__http__') == 403, 'E2 无权限成员 → 403')
    r = req(tok_u1, '/api/syn-boards?dept_node_id=%d' % _did)
    ok(r.get('boards') == [], 'E3 追加人员可进入但数据不越权（无看板可见 → 空清单）', r)
    r = req(tok_dh, '/api/syn-boards?dept_node_id=%d' % _did)
    ok([b['board_id'] for b in r.get('boards', [])] == [P + 'B1'], 'E4 部门长综合数据正常')

    print('【F】校验与提交')
    ok(all(x for x, _ in RES), 'F1 全部断言通过')

finally:
    pass

_np = sum(1 for x, _ in RES if x)
_nf = len(RES) - _np
print('结果: PASS=%d FAIL=%d' % (_np, _nf))
sys.exit(0 if _nf == 0 else 1)
