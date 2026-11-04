# -*- coding: utf-8 -*-
"""#47 权限测试：①新增节点仅管理员；②看板绑定 = 部门长/组长 + 负责人/参与人候选池。

角色矩阵（夹具）：
  __bp_admin  admin      —— 全部放行
  __bp_dept   editor     —— 部门长（fixture 部门 D）→ 可绑定 D 及后代（含小组 G）
  __bp_lead   editor     —— 小组组长（G）→ 只可绑定 G
  __bp_arch   editor     —— 中心负责人（C，非部门长/组长）→ 不可绑定
  __bp_none   editor     —— 无任何岗位 → 不可绑定

看板：
  __bpB_own    负责人=__bp_dept
  __bpB_part   板块参与人含 __bp_dept
  __bpB_for    归属别人（都不行）
  __bpB_bound  已被管理员绑在 G 上（__bp_lead 不是它的负责人/参与人）
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__bp_'
PWD = 'At159357'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http(path, method='GET', body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}

def setup():
    from app.app import hash_pw, make_token
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 10:30:00'
    # 清残留（前缀级，双保险）
    for t, col in (('cards', 'board_id'), ('board_columns', 'board_id'), ('board_config', 'board_id'), ('boards', 'board_id')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    # 账号
    roles = {'admin': 'admin', 'dept': 'editor', 'lead': 'editor', 'arch': 'editor', 'none': 'editor'}
    mids = {}
    for k, role in roles.items():
        acct = PREFIX + k
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + k, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        mids[k] = mid
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    # 节点树 C→D→G + workgroups 载体
    wg_ids, node_ids = {}, {}
    for key, ntype, parent in (('C', 'center', 0), ('D', 'dept', None), ('G', 'group', None)):
        cur = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','', '')", (PREFIX + key,))
        wg_ids[key] = cur.lastrowid
    for key, ntype, parent in (('C', 'center', 0), ('D', 'dept', wg_ids['C']), ('G', 'group', node_ids.get('D'))):
        pass
    # 先建 C/D/G 节点（org_nodes），parent 指向 org_nodes.id
    cC = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'C', 'center', 0, wg_ids['C']))
    nC = cC.lastrowid
    cD = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'D', 'dept', nC, wg_ids['D']))
    nD = cD.lastrowid
    cG = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'G', 'group', nD, wg_ids['G']))
    nG = cG.lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['C'], wg_ids['D']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['D'], wg_ids['G']))
    # 任命
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nC, mids['arch'], 'center_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nD, mids['dept'], 'dept_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nG, mids['lead'], 'group_leader', now))
    # 看板
    bids = {}
    for key, owner in (('own', PREFIX + 'dept'), ('part', PREFIX + 'none'), ('for', 'someone_else'), ('bound', 'someone_else')):
        bid = PREFIX + 'B_' + key
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, PREFIX + key, '', owner, now))
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'',?)",
                  (bid + '::C1', PREFIX + 'col_' + key, bid, 'C1', now, (PREFIX + 'dept' if key == 'part' else '')))
        bids[key] = bid
    # 绑定现状：D 绑全部 4 块（父级范围），G 已绑 B_bound（管理员行为模拟）
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (','.join(bids.values()), wg_ids['D']))
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (bids['bound'], wg_ids['G']))
    c.commit(); c.close()
    tok = {k: make_token(PREFIX + k) for k in roles}
    return {'nC': nC, 'nD': nD, 'nG': nG, 'wgD': wg_ids['D'], 'wgG': wg_ids['G'], 'bids': bids, 'tok': tok}

def cleanup(fx):
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.commit(); c.close()

def main():
    from app.app import make_token
    fx = setup()
    t = fx['tok']
    try:
        # ── 需求1：新增节点仅管理员 ──
        print('\n【需求1】新增节点仅管理员')
        code, r = http('/api/org/nodes', 'POST',
                       {'name': PREFIX + '新节点', 'node_type': 'group', 'parent_id': fx['nD']}, token=t['admin'])
        ok(code == 200, '管理员新增节点 → 200（实际 %s）' % code)
        new_nid = r.get('id')
        code, r = http('/api/org/nodes', 'POST',
                       {'name': PREFIX + '越权节点', 'node_type': 'group', 'parent_id': fx['nD']}, token=t['dept'])
        ok(code == 403, '部门长新增节点 → 403（实际 %s）' % code)
        code, _ = http('/api/org/nodes', 'POST',
                       {'name': PREFIX + '越权节点2', 'node_type': 'group', 'parent_id': fx['nD']}, token=t['lead'])
        ok(code == 403, '小组组长新增节点 → 403（实际 %s）' % code)
        code, _ = http('/api/org/nodes', 'POST',
                       {'name': PREFIX + '越权节点3', 'node_type': 'group', 'parent_id': fx['nD']}, token=t['arch'])
        ok(code == 403, '中心负责人新增节点 → 403（实际 %s）' % code)

        # ── 需求2：绑定权限 ──
        print('\n【需求2】看板绑定（角色 + 候选池）')
        B = fx['bids']
        # 部门长：自己是负责人的看板 → 200
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['bound'] + ',' + B['own']}, token=t['dept'])
        ok(code == 200, '部门长绑【自己是负责人】的看板 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        # 部门长：自己是板块参与人的看板 → 200
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['bound'] + ',' + B['own'] + ',' + B['part']}, token=t['dept'])
        ok(code == 200, '部门长绑【自己是板块参与人】的看板 → 200（实际 %s）' % code)
        # 部门长：无关系的看板 → 403
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['bound'] + ',' + B['own'] + ',' + B['part'] + ',' + B['for']}, token=t['dept'])
        ok(code == 403, '部门长绑【无关系】的看板 → 403（实际 %s）' % code)
        # 组长：绑自己节点（G 是自己任命节点）→ 200
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['bound']}, token=t['lead'])
        ok(code == 200, '小组组长在本组保存绑定 → 200（实际 %s）' % code)
        # 组长：新增无关系看板 → 403（B_bound 是已有绑定可保留；B_own 不是他的）
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['bound'] + ',' + B['own']}, token=t['lead'])
        ok(code == 403, '小组组长新增【非自己负责人/参与人】看板 → 403（实际 %s）' % code)
        # 组长：部门节点（祖先 D，不是自己的任命节点）→ 403
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT', {'boards': B['own']}, token=t['lead'])
        ok(code == 403, '小组组长改父部门绑定 → 403（实际 %s）' % code)
        # 部门长：改自己部门 D 的绑定 → 200（部门长管理本部门架构下）
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT', {'boards': ','.join(B.values())}, token=t['dept'])
        ok(code == 200, '部门长改本部门绑定 → 200（实际 %s）' % code)
        # 中心负责人（架构负责人但非部门长/组长）→ 403
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['own']}, token=t['arch'])
        ok(code == 403, '中心负责人（非部门长/组长）绑定 → 403（实际 %s）' % code)
        # 无岗位 → 403
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['own']}, token=t['none'])
        ok(code == 403, '无岗位账号绑定 → 403（实际 %s）' % code)
        # 管理员 → 200
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['own']}, token=t['admin'])
        ok(code == 200, '管理员绑定 → 200（实际 %s）' % code)
        # 管理员恢复 B_bound 后，组长提交不含 B_bound → 已绑定可被其解除（解除也是绑定操作）
        http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['own'] + ',' + B['bound']}, token=t['admin'])
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['own']}, token=t['lead'])
        ok(code == 200, '组长提交（去掉已绑定项）→ 200（解除绑定放行，实际 %s）' % code)
        # 父级范围约束仍在：D 不含 B_part 时，G 绑 B_part → 400
        http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT', {'boards': B['own']}, token=t['admin'])
        code, r = http('/api/org/nodes/%d/boards' % fx['nG'], 'PUT', {'boards': B['part']}, token=t['admin'])
        ok(code == 400, '子级绑定超出父级范围 → 400（实际 %s）' % code)
        http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT', {'boards': ','.join(B.values())}, token=t['admin'])
        # 中心节点锁定
        code, r = http('/api/org/nodes/%d/boards' % fx['nC'], 'PUT', {'boards': B['own']}, token=t['admin'])
        ok(code == 403, '中心节点绑定 → 403（锁定全部看板，实际 %s）' % code)

        # ── can_config_bind 能力位 ──
        print('\n【能力位】/api/org/tree can_config_bind')
        code, r = http('/api/org/tree', token=t['dept'])
        tree = {}
        def walk(ns):
            for n in ns or []:
                tree[n['name']] = n; walk(n.get('children'))
        walk(r.get('tree') or [])
        ok(tree[PREFIX + 'D']['can_config_bind'] is True, '部门长：本部门 can_config_bind=true')
        ok(tree[PREFIX + 'G']['can_config_bind'] is True, '部门长：后代小组 can_config_bind=true（管理本部门架构下）')
        ok(tree[PREFIX + 'C']['can_config_bind'] is False, '部门长：中心节点 can_config_bind=false（锁定）')
        code, r = http('/api/org/tree', token=t['arch'])
        tree = {}; walk(r.get('tree') or [])
        ok(tree[PREFIX + 'G']['can_config_bind'] is False, '中心负责人（非部门长/组长）：小组 can_config_bind=false')
        code, r = http('/api/org/tree', token=t['lead'])
        tree = {}; walk(r.get('tree') or [])
        ok(tree[PREFIX + 'G']['can_config_bind'] is True, '小组组长：本组 can_config_bind=true')
        ok(tree[PREFIX + 'D']['can_config_bind'] is False, '小组组长：父部门 can_config_bind=false')

        # ── 候选池口径（/api/workgroups bindable_board_ids）──
        print('\n【候选池】/api/workgroups bindable_board_ids')
        code, r = http('/api/workgroups', token=t['dept'])
        ids = set(r.get('bindable_board_ids') or [])
        ok(B['own'] in ids and B['part'] in ids, '候选池含【负责人/参与人】看板：%s' % sorted(ids))
        ok(B['for'] not in ids, '候选池不含无关系看板')
        code, r = http('/api/workgroups', token=t['admin'])
        ok(r.get('bindable_board_ids') is None, '管理员不受候选池限制（bindable_board_ids=null）')

        # ── 独立性：新限制只约束「谁能执行绑定」，不改变绑定本身的效果 ──
        print('\n【独立性】绑定的既有效果不变（绑定仍决定可见性）')
        from app.app import user_allowed
        vis, _ = user_allowed(PREFIX + 'lead')
        ok(vis is None or B['own'] in vis,
           'G 组绑定了 B_own → 组长可见（绑定的既有语义未被动过）：%s'
           % (sorted(vis) if vis is not None else 'None(全部)'))
    finally:
        cleanup(fx)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(main())
