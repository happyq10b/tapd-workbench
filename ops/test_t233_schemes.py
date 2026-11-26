# -*- coding: utf-8 -*-
"""T-233 综合配置多方案（纯 API 测试）。

需求（2026-11-25 用户）：
  ①【综合编辑】→【综合配置】改名（UI 文案，API 键 syn_edit_depts 保持）；
  ② 每个架构可持续配置多个方案并保存；配置人选定一个「外部显示方案」，
    点【综合看板】时生效（= 配置人自己综合视图的适用方案）；
  ③ 校验：同一配置人名下，同一追加人员只能适配一个方案（防配置冲突）。

场景：
  A. 多方案保存：2 方案各自白名单/追加人员 + display_index → 落库与回读一致；
  B. 外部显示方案生效：GET 旧版 columns 字段 = 显示方案的白名单；切换 display_index 后跟随；
  C. 追加人适配：m1 的适用配置 = 包含它的方案（月度），而非显示方案（季度）；
  D. 冲突校验：同一成员进两个方案 → 400；方案名重复 → 400；
  E. 跨配置人邀请带方案：第二配置人抢成员 → 邀请（含方案名）→ 成员确认 →
     加入邀请方案 + 原归属人全部方案移除该成员（T-228 语义）；
  F. 兼容：旧版单配置 PUT（columns/extra_members）→ 编辑显示方案，其余方案不动；
  G. 夹具清理 + 真实配置快照恢复（admin 名下 nid=4 有真实「默认方案」，不得破坏）。
"""
import json, os, sqlite3, sys, urllib.request, urllib.error, urllib.parse

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = 'src/app.db'
NID = 4            # 核算部（BCP1793717004248 挂载架构）
OWNER_A = 'admin'  # 真实配置人（快照恢复）
OWNER_B = '__t233_o2'
M1 = '__t233_m1'
M2 = '__t233_m2'

ok_n = fail_n = 0
def ok(cond, msg):
    global ok_n, fail_n
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if cond: ok_n += 1
    else: fail_n += 1

def api(tk, path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + tk)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20,
                                    data=json.dumps(body).encode() if body is not None else None) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def _snap():
    """快照 nid=4 的真实状态（T-238 修复：**忠实行级快照**，不再从 syn_board_config
    旧存档重建 —— 旧做法曾把用户 2026-11-26 08:43 保存的真实配置覆盖掉）。
    覆盖：方案行 / 成员归属行 / 邀请行 / 用户方案接收行（选择态）。"""
    def _rows(q):
        return [dict(r) for r in conn.execute(q, (NID,))]
    return {
        'scheme': _rows('SELECT id, dept_node_id, owner, name, columns, extra_members, is_display, updated_at FROM syn_scheme WHERE dept_node_id=?'),
        'member': _rows('SELECT id, dept_node_id, member, owner FROM syn_config_member WHERE dept_node_id=?'),
        'invite': _rows('SELECT id, dept_node_id, member, owner, status, created_at, decided_at, scheme_id FROM syn_config_invite WHERE dept_node_id=?'),
        'smem': _rows('SELECT dept_node_id, username, scheme_id, status, updated_at FROM syn_scheme_member WHERE dept_node_id=?'),
    }

SNAP = _snap()
SNAP_MEM = SNAP['member']

def restore_snapshot():
    """忠实恢复：四张表按快照行原样回插（先清后插，幂等）。"""
    conn2 = sqlite3.connect(DB)
    conn2.execute('DELETE FROM syn_scheme_member WHERE dept_node_id=?', (NID,))
    conn2.execute('DELETE FROM syn_config_invite WHERE dept_node_id=?', (NID,))
    conn2.execute('DELETE FROM syn_config_member WHERE dept_node_id=?', (NID,))
    conn2.execute('DELETE FROM syn_scheme WHERE dept_node_id=?', (NID,))
    for r in SNAP['scheme']:
        conn2.execute('INSERT INTO syn_scheme (id,dept_node_id,owner,name,columns,extra_members,is_display,updated_at) '
                      'VALUES (?,?,?,?,?,?,?,?)',
                      (r['id'], r['dept_node_id'], r['owner'], r['name'], r['columns'],
                       r['extra_members'], r['is_display'], r['updated_at']))
    for r in SNAP['member']:
        conn2.execute('INSERT INTO syn_config_member (id,dept_node_id,member,owner) VALUES (?,?,?,?)',
                      (r['id'], r['dept_node_id'], r['member'], r['owner']))
    for r in SNAP['invite']:
        conn2.execute('INSERT INTO syn_config_invite (id,dept_node_id,member,owner,status,created_at,decided_at,scheme_id) '
                      'VALUES (?,?,?,?,?,?,?,?)',
                      (r['id'], r['dept_node_id'], r['member'], r['owner'], r['status'],
                       r['created_at'], r['decided_at'], r['scheme_id']))
    for r in SNAP['smem']:
        conn2.execute('INSERT INTO syn_scheme_member (dept_node_id,username,scheme_id,status,updated_at) '
                      'VALUES (?,?,?,?,?)',
                      (r['dept_node_id'], r['username'], r['scheme_id'], r['status'], r['updated_at']))
    conn2.commit(); conn2.close()

def pre_clean():
    """启动预清理：回收此前崩溃运行残留的夹具数据（只动夹具拥有的行，不碰真实数据）。"""
    conn2 = sqlite3.connect(DB)
    conn2.execute("DELETE FROM syn_config_invite WHERE dept_node_id=? AND owner LIKE '%t233%'", (NID,))
    conn2.execute("DELETE FROM syn_config_member WHERE dept_node_id=? AND owner LIKE '%t233%'", (NID,))
    conn2.execute("DELETE FROM syn_scheme WHERE dept_node_id=? AND owner LIKE '%t233%'", (NID,))
    conn2.execute("DELETE FROM messages WHERE receiver LIKE '%t233%'", ())
    conn2.execute("DELETE FROM users WHERE username LIKE '%t233%'", ())
    conn2.commit(); conn2.close()

def cleanup(members):
    """夹具清理（参数化成员列表——真实成员的归属行/邀请消息一并回收）。
    ⚠️ T-238：删除范围严格限定夹具成员/夹具配置人名下 —— 不得全表清 nid。"""
    conn2 = sqlite3.connect(DB)
    marks = ','.join('?' * len(members))
    # 夹具方案（两位配置人名下全部）+ 邀请 + 归属 + 消息 + 用户
    conn2.execute('DELETE FROM syn_scheme WHERE dept_node_id=? AND owner IN (?,?)', (NID, OWNER_A, OWNER_B))
    conn2.execute("DELETE FROM syn_config_invite WHERE dept_node_id=? AND (member IN (%s) OR owner IN (?,?))" % marks,
                  (NID,) + tuple(members) + (OWNER_A, OWNER_B))
    conn2.execute('DELETE FROM syn_config_member WHERE dept_node_id=? AND member IN (%s)' % marks,
                  (NID,) + tuple(members))
    conn2.execute('DELETE FROM syn_scheme_member WHERE dept_node_id=? AND username IN (%s)' % marks,
                  (NID,) + tuple(members))
    conn2.execute("DELETE FROM messages WHERE (receiver LIKE '%t233%')"
                  " OR (sender IN (SELECT username FROM users WHERE username LIKE '%t233%'))"
                  " OR (kind='system' AND (content LIKE '%已接受您发出的追加邀请%' OR content LIKE '%已拒绝您发出的追加邀请%'))")
    conn2.execute('DELETE FROM users WHERE username IN (?,?,?)', (OWNER_B, M1, M2))
    conn2.commit(); conn2.close()

def main():
    tk_a = make_token(OWNER_A)
    pre_clean()
    try:
        # ── 夹具：第二配置人（role=admin → 默认可见）+ 成员账号 ──
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (OWNER_B, hash_pw('T233!x'), 'admin', '*', '*'))
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (M1, hash_pw('T233!x'), 'editor', '*', '*'))
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (M2, hash_pw('T233!x'), 'editor', '*', '*'))
        conn.commit()
        tk_b = make_token(OWNER_B)
        tk_m1 = make_token(M1)
        tk_m2 = make_token(M2)
        # 候选成员：从真实子树候选中选（兜底用夹具账号——center 型候选含全员，
        # 若 nid=4 无候选则改走 dept 绑定，直接断言失败提示）
        st, d0 = api(tk_a, '/api/syn-config?dept_node_id=%d' % NID)
        assert st == 200, 'syn-config 读取失败: %s' % d0
        # 候选成员：取真实**非管理员**成员（候选池第③段会把全部 role=admin 的
        # users 全局纳入 —— 夹具 o2 是 admin 角色，按名字排序还会排最前，必须排除）
        mapped = {r['member'] for r in SNAP_MEM}
        cands = [c['account'] for c in (d0.get('candidates') or [])
                 if c.get('account') and 't233' not in c['account']
                 and c['account'] != 'admin' and c['account'] not in mapped]
        assert len(cands) >= 2, '无归属的候选不足 2 人（%d）' % len(cands)
        cm1, cm2 = cands[0], cands[1]
        tk_cm1 = make_token(cm1)
        tk_cm2 = make_token(cm2)
        # 白名单：取该架构子树内一个真实 col_key
        wl_all = []
        for b in (d0.get('all_boards') or []):
            wl_all += [c['col_key'] for c in (b.get('columns') or [])]
        ck = wl_all[0] if wl_all else ''

        # ── A. 多方案保存 ──
        st, d1 = api(tk_a, '/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': '月度', 'columns': ck, 'extra_members': cm1},
            {'name': '季度', 'columns': '', 'extra_members': cm2},
        ], 'display_index': 1})
        ok(st == 200 and d1.get('schemes') == 2 and d1.get('display') == '季度',
           'A 多方案保存成功（display=季度）')
        st, d2 = api(tk_a, '/api/syn-config?dept_node_id=%d' % NID)
        scs = d2.get('schemes') or []
        ok(len(scs) == 2 and scs[0]['name'] == '月度' and scs[1]['name'] == '季度'
           and scs[1]['is_display'] is True and scs[0]['is_display'] is False,
           'A 回读：2 方案、is_display 唯一且指向「季度」')
        ok(scs[0]['columns'] == ([ck] if ck else []) and scs[0]['extra_members'] == [cm1]
           and scs[1]['extra_members'] == [cm2],
           'A 各方案白名单/追加人员与保存一致')

        # ── A-bis. 全量邀请制（T-235）：首次追加也发邀请，成员确认后生效 ──
        st, dI = api(tk_cm1, '/api/syn-invites')
        inv1 = [x for x in (dI.get('invites') or []) if x['owner'] == OWNER_A and x.get('scheme_name') == '月度']
        ok(len(inv1) >= 1, 'A-bis cm1 收到「月度」追加邀请（T-235）')
        st, _ = api(tk_cm1, '/api/syn-invites/%d/decide' % inv1[0]['id'], 'POST', {'accept': True})
        st, dI2 = api(tk_cm2, '/api/syn-invites')
        inv2 = [x for x in (dI2.get('invites') or []) if x['owner'] == OWNER_A and x.get('scheme_name') == '季度']
        ok(len(inv2) >= 1, 'A-bis cm2 收到「季度」追加邀请（T-235）')
        st, _ = api(tk_cm2, '/api/syn-invites/%d/decide' % inv2[0]['id'], 'POST', {'accept': True})
        # 反馈通知：发起人 admin 收到 cm1/cm2 的接受反馈
        st, dM = api(tk_a, '/api/messages')
        msgs = json.dumps(dM, ensure_ascii=False)
        ok('已接受您发出的追加邀请' in msgs, 'A-bis 发起人收到接受反馈通知（T-235）')

        # ── B. 外部显示方案生效（配置人综合视图适用方案 = 显示方案）──
        ok(d2.get('columns') == [] , 'B 旧版 columns 字段 = 显示方案（季度=空白名单）')
        st, d3 = api(tk_a, '/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': '月度', 'columns': ck, 'extra_members': cm1},
            {'name': '季度', 'columns': '', 'extra_members': cm2},
        ], 'display_index': 0})
        st, d4 = api(tk_a, '/api/syn-config?dept_node_id=%d' % NID)
        ok(st == 200 and d4.get('columns') == ([ck] if ck else []),
           'B 切换 display_index=0 → 适用方案变为「月度」（点综合看板即此方案）')

        # ── C. 追加人适配：m1 看到包含它的「月度」，而非显示方案 ──
        st, d5 = api(tk_cm1, '/api/syn-config?dept_node_id=%d' % NID)
        ok(st == 200 and d5.get('columns') == ([ck] if ck else []) and d5.get('can_edit') is False,
           'C 追加人 cm1 适用配置 = 其适配方案「月度」的白名单（非显示方案）')
        st, d5b = api(tk_cm2, '/api/syn-config?dept_node_id=%d' % NID)
        ok(st == 200 and d5b.get('columns') == [] and d5b.get('can_edit') is False,
           'C 追加人 cm2 适用配置 = 其适配方案「季度」（空白名单）')

        # ── D. 校验 ──
        st, d6 = api(tk_a, '/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': '甲', 'columns': ck, 'extra_members': cm1},
            {'name': '乙', 'columns': '', 'extra_members': cm1},
        ], 'display_index': 0})
        ok(st == 400 and '只能适配一个方案' in (d6.get('detail') or ''),
           'D 冲突校验：同一成员进两个方案 → 400（%s）' % (d6.get('detail') or '')[:40])
        st, d7 = api(tk_a, '/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': '同名', 'columns': '', 'extra_members': ''},
            {'name': '同名', 'columns': ck, 'extra_members': ''},
        ], 'display_index': 0})
        ok(st == 400 and '方案名重复' in (d7.get('detail') or ''),
           'D 方案名重复 → 400')

        # ── E. 跨配置人邀请带方案（admin 在 A 步已即时归属 cm1 → 由 o2 发起抢人邀请）──
        st, d8 = api(tk_b, '/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': 'B方案', 'columns': ck, 'extra_members': cm1},
        ], 'display_index': 0})
        ok(st == 200 and d8.get('invited') == 1, 'E o2 配置含已归属 admin 的 cm1 → 发邀请 1 份')
        st, d10 = api(tk_cm1, '/api/syn-invites')
        invs = d10.get('invites') or []
        ok(len(invs) == 1 and invs[0]['scheme_name'] == 'B方案' and invs[0]['owner'] == OWNER_B,
           'E 邀请清单含目标方案名「B方案」与发起人')
        st, d11 = api(tk_cm1, '/api/syn-invites/%d/decide' % invs[0]['id'], 'POST', {'accept': True})
        ok(st == 200, 'E 成员确认邀请')
        st, d12 = api(tk_cm1, '/api/syn-config?dept_node_id=%d' % NID)
        ok(st == 200 and d12.get('columns') == ([ck] if ck else []),
           'E 确认后 cm1 适配「B方案」白名单（与 admin 方案并集一致）')
        st, d13 = api(tk_a, '/api/syn-config?dept_node_id=%d' % NID)
        scs13 = d13.get('schemes') or []
        ok(any(cm1 in (s.get('extra_members') or []) for s in scs13),
           'E 多方案接收：cm1 确认 o2 邀请后**保留** admin 方案（T-235 不驱逐）')
        # 反馈通知：o2 收到 cm1 的接受反馈
        st, dM2 = api(tk_b, '/api/messages')
        ok('已接受您发出的追加邀请' in json.dumps(dM2, ensure_ascii=False),
           'E 发起人 o2 收到接受反馈通知（T-235）')

        # ── F. 旧版单配置兼容（编辑显示方案「月度」，季度方案不动）──
        st, d14 = api(tk_a, '/api/syn-config/%d' % NID, 'PUT',
                      {'columns': '', 'extra_members': cm2})
        ok(st == 200, 'F 旧版 PUT 兼容')
        st, d15 = api(tk_a, '/api/syn-config?dept_node_id=%d' % NID)
        scs15 = d15.get('schemes') or []
        ok(len(scs15) == 2 and scs15[0]['name'] == '月度' and scs15[0]['columns'] == []
           and scs15[0]['extra_members'] == [cm2] and scs15[1]['extra_members'] == [cm2],
           'F 显示方案（月度）被旧版保存覆盖为空白名单+cm2，季度方案不受影响')
    finally:
        cleanup([cm1, cm2])
        restore_snapshot()
    # ── G. 残留自查 + 真源恢复核对 ──
    conn2 = sqlite3.connect(DB)
    conn2.row_factory = sqlite3.Row
    scs_now = [dict(r) for r in conn2.execute(
        'SELECT id, dept_node_id, owner, name, columns, extra_members, is_display FROM syn_scheme WHERE dept_node_id=? ORDER BY owner, id', (NID,))]
    mem_now = [dict(r) for r in conn2.execute(
        'SELECT member, owner FROM syn_config_member WHERE dept_node_id=? ORDER BY id', (NID,))]
    inv_t233 = conn2.execute("SELECT COUNT(*) FROM syn_config_invite WHERE dept_node_id=? AND owner LIKE '%t233%'", (NID,)).fetchone()[0]
    usr = conn2.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t233%'").fetchone()[0]
    conn2.close()
    # T-238：与**忠实快照**逐行比对（排序键一致：owner,id —— 中文按 name 排会与 id 序错位）
    exp_scs = sorted([{'id': r['id'], 'dept_node_id': r['dept_node_id'], 'owner': r['owner'], 'name': r['name'],
                       'columns': r['columns'], 'extra_members': r['extra_members'], 'is_display': r['is_display']}
                      for r in SNAP['scheme']], key=lambda x: (x['owner'], x['id']))
    ok(scs_now == exp_scs, 'G 方案表按快照忠实恢复一致（%d 行）' % len(exp_scs))
    ok(mem_now == [{'member': r['member'], 'owner': r['owner']} for r in sorted(SNAP['member'], key=lambda x: x['id'])],
       'G 成员归属映射恢复一致（%d 行）' % len(SNAP['member']))
    ok(inv_t233 == 0 and usr == 0, 'G 夹具零残留（t233邀请=%d t233用户=%d）' % (inv_t233, usr))
    print('结果: %d PASS / %d FAIL' % (ok_n, fail_n))
    sys.exit(1 if fail_n else 0)

if __name__ == '__main__':
    try:
        main()
    finally:
        conn.close()
