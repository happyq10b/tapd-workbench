# -*- coding: utf-8 -*-
"""#48 测试：①架构负责人（中心负责人/总经理）可绑定管辖架构下全部看板（宽池）；
②板块负责人指派 = 架构负责人及以上（新建+编辑）；③新建板块落库 owner/participants；
④/api/me 每看板 can_edit / can_assign_owner。"""
import json, os, sqlite3, sys, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__ab_'
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
    now = '2026-11-04 12:00:00'
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    roles = {'arch': 'editor', 'dept': 'editor', 'plain': 'editor'}
    mids, toks = {}, {}
    for k, role in roles.items():
        acct = PREFIX + k
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + k, acct, now))
        mids[k] = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    # 节点 C→D、C→GN（plain 的组）
    wC = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','','*')", (PREFIX + 'C',)).lastrowid
    wD = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,?,?,'','')", (PREFIX + 'D', wC, PREFIX + 'dept')).lastrowid
    wGN = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,?,?,'','')", (PREFIX + 'GN', wC, PREFIX + 'plain')).lastrowid
    nC = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'C', 'center', 0, wC)).lastrowid
    nD = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'D', 'dept', nC, wD)).lastrowid
    nGN = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'GN', 'group', nC, wGN)).lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wC, wD))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wC, wGN))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nC, mids['arch'], 'center_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nD, mids['dept'], 'dept_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nGN, mids['plain'], 'group_leader', now))
    # 看板
    bids = {}
    for key, owner in (('arch_t', 'someone'), ('dept_own', PREFIX + 'dept'), ('foreign', 'someone'), ('pub', PREFIX + 'plain')):
        bid = PREFIX + 'B_' + key
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, PREFIX + key, '', owner, now))
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
                  (bid + '::C1', PREFIX + 'col_' + key, bid, 'C1', now))
        bids[key] = bid
    # 绑定：D 绑 3 块（arch/dept 范围），GN 绑 pub（plain 的组 → 组长可见）
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (bids['arch_t'] + ',' + bids['dept_own'] + ',' + bids['foreign'], wD))
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (bids['pub'], wGN))
    # ⚠️ 看板归属部门（board_config）：架构负责人的权限等级靠「看板→部门→任命」挂钩，
    #    没有归属配置的看板对架构负责人无权限等级（生产数据都有归属）。
    for key in ('arch_t', 'dept_own', 'foreign', 'pub'):
        c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,?,?,?,'',?)",
                  (bids[key], PREFIX + 'D', nD, '日常', '启用', now))
    c.commit(); c.close()
    tok = {k: make_token(PREFIX + k) for k in roles}
    tok['admin'] = make_token('admin')
    return {'nC': nC, 'nD': nD, 'nGN': nGN, 'wD': wD, 'bids': bids, 'tok': tok, 'mids': mids}

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
    fx = setup()
    t = fx['tok']
    B = fx['bids']
    try:
        # ── 需求1：架构负责人宽池绑定 ──
        print('\n【需求1】架构负责人绑定管辖架构下全部看板')
        code, r = http('/api/org/tree', token=t['arch'])
        tree = {}
        def walk(ns):
            for n in ns or []:
                tree[n['name']] = n; walk(n.get('children'))
        walk(r.get('tree') or [])
        ok(tree[PREFIX + 'D']['can_config_bind'] is True, '架构负责人：部门节点可绑（can_config_bind）')
        ok(tree[PREFIX + 'D']['in_my_scope'] is True, '架构负责人：部门节点在管辖范围内')
        # 绑「不是自己负责人/参与人」的看板（B_foreign）→ 宽池放行 200
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT',
                       {'boards': B['arch_t'] + ',' + B['dept_own'] + ',' + B['foreign']}, token=t['arch'])
        ok(code == 200, '架构负责人绑【非负责人/参与人】看板 → 200（宽池，实际 %s %s）' % (code, r.get('detail', '')))
        # 部门长 = 架构负责人（2026-11-05）：绑 foreign（架构下无关系看板）→ 200 宽池豁免
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT',
                       {'boards': B['arch_t'] + ',' + B['dept_own']}, token=t['dept'])
        ok(code == 200, '部门长绑【自己是负责人】看板 → 200')
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT',
                       {'boards': B['arch_t'] + ',' + B['dept_own'] + ',' + B['foreign']}, token=t['dept'])
        ok(code == 200, '部门长绑【无关系】看板 → 200（宽池，实际 %s %s）' % (code, r.get('detail', '')))
        # 无岗位 → 403
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT', {'boards': B['arch_t']}, token=t['plain'])
        ok(code == 403, '无关组长绑别的部门节点 → 403（实际 %s）' % code)
        # 候选池口径
        code, r = http('/api/workgroups', token=t['arch'])
        ids = set(r.get('bindable_board_ids') or [])
        ok(r.get('binding_scope') == 'arch', "binding_scope='arch'")
        ok(B['foreign'] in ids, '架构负责人候选池含【非负责人/参与人】的架构下看板')
        code, r = http('/api/workgroups', token=t['dept'])
        ids = set(r.get('bindable_board_ids') or [])
        ok(r.get('binding_scope') == 'arch' and B['foreign'] in ids,
           "部门长 binding_scope='arch'（2026-11-05 宽池）且含无关系看板")

        # ── 需求2/3：板块负责人/参与人 ──
        print('\n【需求2/3】板块负责人/参与人指派')
        # /api/me 能力位
        code, r = http('/api/me', token=t['arch'])
        mb = {b['board_id']: b for b in (r.get('boards') or [])}
        ok(mb.get(B['arch_t'], {}).get('can_assign_owner') is True, '/api/me：架构负责人 can_assign_owner=true')
        ok(mb.get(B['arch_t'], {}).get('can_edit') is True, '/api/me：架构负责人 can_edit=true')
        code, r = http('/api/me', token=t['plain'])
        mb2 = {b['board_id']: b for b in (r.get('boards') or [])}
        ok(mb2.get(B['pub'], {}).get('can_assign_owner') is False,
           '/api/me：看板负责人 can_assign_owner=false（上级权）：%s' % mb2.get(B['pub'], {}).get('can_assign_owner'))
        ok(mb2.get(B['pub'], {}).get('can_edit') is True, '/api/me：看板负责人 can_edit=true')
        # 新建板块带负责人（架构负责人）→ 200 且落库
        code, r = http('/api/columns', 'POST',
                       {'board_id': B['arch_t'], 'column_name': PREFIX + '新板块', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'owner': PREFIX + 'dept',
                        'participants': PREFIX + 'dept,' + PREFIX + 'plain'}, token=t['arch'])
        ok(code == 200, '架构负责人新建板块带负责人/参与人 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        new_key = r.get('col_key')
        code, r = http('/api/cards?board_id=' + B['arch_t'], token=t['admin'])
        # 直接查库确认落库
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        row = c.execute("SELECT owner, participants FROM board_columns WHERE col_key=?", (new_key,)).fetchone()
        ok(row and row['owner'] == PREFIX + 'dept', '新建板块负责人已落库：%s' % (row and row['owner']))
        ok(row and PREFIX + 'dept' in (row['participants'] or ''), '新建板块参与人已落库（修复 create 静默丢弃）')
        # 新建板块带负责人（仅看板负责人，非架构负责人）→ 403
        code, r = http('/api/columns', 'POST',
                       {'board_id': B['pub'], 'column_name': PREFIX + '越权板块', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'owner': PREFIX + 'plain'}, token=t['plain'])
        ok(code == 403, '看板负责人新建板块指定负责人 → 403（上级权，实际 %s）' % code)
        # 编辑板块负责人：架构负责人 → 200
        code, r = http('/api/columns', 'PUT',
                       {'col_key': new_key, 'board_id': B['arch_t'], 'column_name': PREFIX + '新板块',
                        'created_at': '2026-11-04', 'nature': '日常', 'year': '2026',
                        'owner': PREFIX + 'arch'}, token=t['arch'])
        ok(code == 200, '架构负责人编辑板块改负责人 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        # 编辑板块负责人：看板负责人（非架构负责人）→ 403
        c2 = sqlite3.connect(DB)
        pub_key = c2.execute("SELECT col_key FROM board_columns WHERE board_id=? LIMIT 1", (B['pub'],)).fetchone()[0]
        c2.close()
        code, r = http('/api/columns', 'PUT',
                       {'col_key': pub_key, 'board_id': B['pub'], 'column_name': PREFIX + 'B_C1',
                        'created_at': '2026-11-04', 'nature': '日常', 'year': '2026',
                        'owner': PREFIX + 'plain'}, token=t['plain'])
        ok(code == 403, '看板负责人编辑板块改负责人 → 403（实际 %s）' % code)
        # 编辑板块参与人：架构负责人 → 200
        code, r = http('/api/columns', 'PUT',
                       {'col_key': pub_key, 'board_id': B['pub'], 'column_name': PREFIX + 'B_C1',
                        'created_at': '2026-11-04', 'nature': '日常', 'year': '2026',
                        'participants': PREFIX + 'arch'}, token=t['arch'])
        ok(code == 200, '架构负责人编辑板块改参与人 → 200（实际 %s）' % code)
    finally:
        cleanup(fx)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(main())
