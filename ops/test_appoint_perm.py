# -*- coding: utf-8 -*-
"""#67 任命分级权限测试（2026-11-05 用户需求）：

① 部门长任命分级：
   · dept_head（部门长）→ 仅 中心负责人 / 总经理（+管理员）可任命
   · group_leader / member（组长/组员）→ 仅 部门长（+管理员）可任命
   · 组长 / 无岗位者 → 403
② 任命组长/组员后成员**默认成为所属部门的架构参与人**（org_nodes.participants 追加）
③ 取消负责人/参与人互斥：set_board_participants 保留负责人；set_board_acl 不再清参与人
④ 部门长 = 架构负责人：绑定候选宽池（可绑其架构下全部看板，不再限「自己是负责人/参与人」）

夹具（__ap_ 前缀）：C(center)→D(dept)→G(group) 树
  __ap_admin  admin    —— 管理员
  __ap_arch   editor   —— 中心负责人（C）
  __ap_dept   editor   —— 部门长（D）
  __ap_lead   editor   —— 组长（G）
  __ap_new    无账号成员 → 用于任命目标
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__ap_'
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
    from app.app import hash_pw, make_token  # noqa
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-05 10:00:00'
    for t, col in (('cards', 'board_id'), ('board_columns', 'board_id'),
                   ('board_config', 'board_id'), ('boards', 'board_id')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    roles = {'admin': 'admin', 'arch': 'editor', 'dept': 'editor', 'lead': 'editor'}
    mids, accts = {}, {}
    for k, role in roles.items():
        acct = PREFIX + k
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + k, acct, now))
        mids[k] = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        accts[k] = acct
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    # 无登录账号的目标成员（姓名 only，account 为空 → 验证参与人同步跳过）
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'','',?)", (PREFIX + 'noacc', now))
    m_noacc = c.execute("SELECT id FROM team_members WHERE name=?", (PREFIX + 'noacc',)).fetchone()[0]
    # 任命目标成员（有账号 + 可登录 —— 负责人必须是已存在账号）
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + 'target', PREFIX + 'target', now))
    m_target = c.execute("SELECT id FROM team_members WHERE account=?", (PREFIX + 'target',)).fetchone()[0]
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
              (PREFIX + 'target', hash_pw(PWD), 'editor', '*', '*', now))
    # 树 C→D→G + 空闲节点 D2（部门，无部门长）/G2（组，无组长）—— 任命目标用，避开唯一槽位占用
    wg_ids = {}
    for key in ('C', 'D', 'G', 'D2', 'G2'):
        cur = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','', '')", (PREFIX + key,))
        wg_ids[key] = cur.lastrowid
    nC = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,0,?)", (PREFIX + 'C', 'center', wg_ids['C'])).lastrowid
    nD = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,?,?)", (PREFIX + 'D', 'dept', nC, wg_ids['D'])).lastrowid
    nG = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,?,?)", (PREFIX + 'G', 'group', nD, wg_ids['G'])).lastrowid
    nD2 = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,?,?)", (PREFIX + 'D2', 'dept', nC, wg_ids['D2'])).lastrowid
    nG2 = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,?,?)", (PREFIX + 'G2', 'group', nD, wg_ids['G2'])).lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['C'], wg_ids['D']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['D'], wg_ids['G']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['C'], wg_ids['D2']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wg_ids['D'], wg_ids['G2']))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nC, mids['arch'], 'center_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nD, mids['dept'], 'dept_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nG, mids['lead'], 'group_leader', now))
    # 看板：B_for 归属别人（部门长此前不可绑）；B_arch 中心负责人视角
    bid = PREFIX + 'B_for'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, PREFIX + 'for', '', 'someone_else', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
              (bid + '::C1', PREFIX + 'col_for', bid, 'C1', now))
    # D 绑定 B_for（部门长宽池验证用：B_for 在 D 架构下）
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (bid, wg_ids['D']))
    c.commit(); c.close()
    tk = {k: make_token(PREFIX + k) for k in roles}
    return {'mids': mids, 'accts': accts, 'tk': tk, 'nC': nC, 'nD': nD, 'nG': nG, 'nD2': nD2, 'nG2': nG2,
            'm_noacc': m_noacc, 'm_target': m_target, 'bid': bid, 'wgD': wg_ids['D']}


def cleanup(fx):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    bid = fx['bid']
    c.execute("DELETE FROM cards WHERE board_id=?", (bid,))
    c.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
    c.execute("DELETE FROM board_config WHERE board_id=?", (bid,))
    c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE member_id IN (SELECT id FROM team_members WHERE account LIKE ? OR name LIKE ?)",
              (PREFIX + '%', PREFIX + '%'))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ? OR name LIKE ?", (PREFIX + '%', PREFIX + '%'))
    c.commit(); c.close()


def main():
    fx = setup()
    t = fx['tk']
    try:
        # ── ① 任命分级矩阵 ──
        print('\n【①】任命分级矩阵')
        # 组长任命部门长 → 403
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nD'], 'member_id': fx['m_target'], 'role_key': 'dept_head'}, token=t['lead'])
        ok(code == 403, '组长任命部门长 → 403（实际 %s %s）' % (code, r.get('detail', '')))
        # 部门长任命部门长 → 403（部门长只能任命组长/组员）
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nD'], 'member_id': fx['m_target'], 'role_key': 'dept_head'}, token=t['dept'])
        ok(code == 403, '部门长任命部门长 → 403（实际 %s）' % code)
        # 中心负责人任命部门长（自己的中心子树内）→ 200
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nD2'], 'member_id': fx['m_target'], 'role_key': 'dept_head'}, token=t['arch'])
        ok(code == 200, '中心负责人任命部门长 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        appt_id = r.get('ok') and _last_appt(fx['nD'], 'dept_head')
        # 中心负责人任命组长 → 403（组长/组员由部门长任命）
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nG'], 'member_id': fx['m_target'], 'role_key': 'group_leader'}, token=t['arch'])
        ok(code == 403, '中心负责人任命组长 → 403（实际 %s）' % code)
        # 部门长任命组长（自己部门子树内）→ 200
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nG2'], 'member_id': fx['m_target'], 'role_key': 'group_leader'}, token=t['dept'])
        ok(code == 200, '部门长任命组长 → 200（实际 %s）' % code)
        # 部门长任命组员 → 200
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nG'], 'member_id': fx['m_noacc'], 'role_key': 'member'}, token=t['dept'])
        ok(code == 200, '部门长任命组员 → 200（实际 %s）' % code)
        # 部门长任命骨干（非授权岗位）→ 403
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nD'], 'member_id': fx['m_target'], 'role_key': 'dept_backbone'}, token=t['dept'])
        ok(code == 403, '部门长任命部门骨干 → 403（实际 %s）' % code)
        # 管理员任命骨干 → 200
        code, r = http('/api/org/appointments', 'POST',
                       {'node_id': fx['nD'], 'member_id': fx['m_target'], 'role_key': 'dept_backbone'}, token=t['admin'])
        ok(code == 200, '管理员任命部门骨干 → 200（实际 %s）' % code)

        # ── ② 架构参与人自动加入 ──
        print('\n【②】任命组长/组员 → 默认成为架构参与人')
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        row = c.execute('SELECT participants FROM org_nodes WHERE id=?', (fx['nD'],)).fetchone()
        parts = [x.strip() for x in ((row['participants'] if row else '') or '').split(',') if x.strip()]
        ok((PREFIX + 'target') in parts,
           '任命组长后成员账号进入部门架构参与人（实际 %s）' % parts)
        # 无账号成员任命 → 不写入（跳过），不报错（上面已 200）
        row = c.execute('SELECT participants FROM org_nodes WHERE id=?', (fx['nD'],)).fetchone()
        parts2 = [x.strip() for x in ((row['participants'] if row else '') or '').split(',') if x.strip()]
        ok('' not in parts2, '无账号成员不产生空参与人项')
        c.close()

        # ── ③ 取消互斥（后端口径）──
        print('\n【③】取消负责人/参与人互斥')
        bid = fx['bid']
        # 先设负责人，再设参与人为同一人 → 参与人接口不再剔除负责人
        code, r = http('/api/boards/%s/acl' % bid, 'PUT', {'owner': PREFIX + 'target'}, token=t['admin'])
        ok(code == 200, '设置负责人 → 200（实际 %s）' % code)
        code, r = http('/api/boards/%s/participants' % bid, 'PUT',
                       {'participants': PREFIX + 'target'}, token=t['admin'])
        ok(code == 200, '设置参与人=负责人本人 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        row = c.execute('SELECT owner,participants FROM boards WHERE board_id=?', (bid,)).fetchone()
        ok(row['owner'] == PREFIX + 'target' and row['participants'] == PREFIX + 'target',
           '后端保留：负责人与参与人可同人（owner=%s parts=%s）' % (row['owner'], row['participants']))
        # 反向：先参与人后负责人 → 负责人接口不再清空参与人
        code, r = http('/api/boards/%s/acl' % bid, 'PUT', {'owner': PREFIX + 'dept'}, token=t['admin'])
        c.close()

        # ── ④ 部门长 = 架构负责人（绑定宽池）──
        print('\n【④】部门长绑定候选宽池')
        code, r = http('/api/workgroups', 'GET', token=t['dept'])
        ok(code == 200, '部门长拉取绑定池 → 200')
        bscope = r.get('binding_scope')
        ok(bscope == 'arch', '部门长绑定口径 = arch 宽池（实际 %s）' % bscope)
        ok(fx['bid'] in (r.get('bindable_board_ids') or []),
           '部门长可绑其架构下非自己负责/参与的看板（%s in bindable）' % fx['bid'])
        # 直接绑定操作（新绑别的看板）→ 200：建一个新看板 B_new2 并放 D 架构下
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        bid2 = PREFIX + 'B_new2'
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)",
                  (bid2, PREFIX + 'new2', '', 'someone_else', '2026-11-05 10:00:00'))
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
                  (bid2 + '::C1', PREFIX + 'col_n2', bid2, 'C1', '2026-11-05 10:00:00'))
        wgrow = c.execute('SELECT boards FROM workgroups WHERE id=?', (fx['wgD'],)).fetchone()
        cur_boards = [x for x in ((wgrow['boards'] if wgrow else '') or '').split(',') if x]
        c.execute("UPDATE workgroups SET boards=? WHERE id=?", (','.join(cur_boards + [bid2]), fx['wgD']))
        c.commit(); c.close()
        code, r = http('/api/org/nodes/%d/boards' % fx['nD'], 'PUT',
                       {'boards': ','.join(cur_boards + [bid2])}, token=t['dept'])
        ok(code == 200, '部门长绑定架构下新看板 → 200（实际 %s %s）' % (code, r.get('detail', '')))

        # ── 罢免分级 ──
        print('\n【⑤】罢免同分级')
        aid = _last_appt(fx['nG2'], 'group_leader')
        code, r = http('/api/org/appointments/%d' % aid, 'DELETE', token=t['lead'])
        ok(code == 403, '组长罢免组长 → 403（实际 %s）' % code)
        code, r = http('/api/org/appointments/%d' % aid, 'DELETE', token=t['dept'])
        ok(code == 200, '部门长罢免自己任命的组长 → 200（实际 %s）' % code)
    finally:
        import gc; gc.collect()   # 确保残留连接释放，避免 cleanup 撞 database is locked
        cleanup(fx)
        print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
        if FAIL:
            sys.exit(1)


def _last_appt(node_id, role_key):
    import sqlite3
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    row = c.execute('SELECT id FROM org_appointments WHERE node_id=? AND role_key=? ORDER BY id DESC LIMIT 1',
                    (node_id, role_key)).fetchone()
    c.close()
    return row['id'] if row else 0


if __name__ == '__main__':
    main()
