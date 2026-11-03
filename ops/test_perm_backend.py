#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""后端测试：权限过滤能力位（2026-11-03）。

覆盖：
  1. /api/me 暴露权限画像（arch_scope / arch_leader_nodes / editable_boards）
  2. /api/boards 逐看板给出 can_edit / can_assign_owner / can_delete / perm_role
  3. /api/org/tree 逐节点给出 can_config_bind / can_manage_node
  4. 角色差异：
     · 管理员 → 全部可配置
     · 架构负责人 → 只可配置自己管辖范围内的
     · 看板负责人 → 只可配置自己负责的看板
     · 只读 → 全部不可配置
  5. 越权拦截：只读账号调写接口 → 403 + 统一错误体

⚠️ 夹具纪律（2026-11-02 立规）：
  · 专属前缀 __pbm_ 命名空间；try/finally 保证清理（删全所有相关表）
  · **断言不硬编码全局基线数字** —— 用夹具自己造的数据比对
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw, make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PREFIX = '__pbm_'
U_ADMIN = PREFIX + 'admin'
U_ARCH = PREFIX + 'arch'
U_BOARD = PREFIX + 'board'
U_VIEWER = PREFIX + 'viewer'
PWD = 'At159357'

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  ✗ ' + msg)


def http(path, method='GET', body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or '{}')
        except Exception:
            return e.code, {'__raw': raw[:300]}


def setup():
    """造夹具：
      架构：__pbm_center（中心）→ __pbm_dept_a（U_ARCH 负责）/ __pbm_dept_b（范围外）
      看板：__pbm_b1 归属 dept_a（U_ARCH 可配置）、__pbm_b2 归属 dept_b（U_ARCH 不可配置）
      U_BOARD 是 __pbm_b2 的负责人（看板负责人可配置自己的看板）
    """
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    now = '2026-11-03 12:00:00'
    for acct, role in ((U_ADMIN, 'admin'), (U_ARCH, 'editor'),
                       (U_BOARD, 'editor'), (U_VIEWER, 'viewer')):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,?,?,?,?)""",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
              (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    ids = {}
    for name, ntype in ((PREFIX + 'center', 'center'), (PREFIX + 'dept_a', 'dept'),
                        (PREFIX + 'dept_b', 'dept')):
        cur = c.execute("INSERT INTO org_nodes (name, node_type, parent_id, function) VALUES (?,?,0,'')",
                         (name, ntype))
        ids[name] = cur.lastrowid
    for key in ('dept_a', 'dept_b'):
        c.execute("UPDATE org_nodes SET parent_id=? WHERE id=?",
                  (ids[PREFIX + 'center'], ids[PREFIX + 'dept_a' if key == 'dept_a' else PREFIX + 'dept_b']))
    # U_ARCH → dept_a 部门长
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (U_ARCH,)).fetchone()[0]
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (?,?,?,1,?)""", (ids[PREFIX + 'dept_a'], mid, 'dept_head', now))
    # 看板
    b1 = 'PB' + str(int(time.time() * 1000))[-11:]
    b2 = 'PC' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, owner, sort, created_at) "
              "VALUES (?,?,'',?,0,?)", (b1, PREFIX + 'b1', U_BOARD, now))
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, owner, sort, created_at) "
              "VALUES (?,?,'',?,0,?)", (b2, PREFIX + 'b2', U_BOARD, now))
    c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, remark, created_at)
                 VALUES (?,?,?,?,?,'',?)""",
              (b1, PREFIX + 'dept_a', ids[PREFIX + 'dept_a'], '日常', '启用', now))
    cfg_b1 = c.execute("SELECT id FROM board_config WHERE board_id=?", (b1,)).fetchone()[0]
    c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, remark, created_at)
                 VALUES (?,?,?,?,?,'',?)""",
              (b2, PREFIX + 'dept_b', ids[PREFIX + 'dept_b'], '日常', '启用', now))
    c.commit()
    c.close()
    return {'node_a': ids[PREFIX + 'dept_a'], 'node_b': ids[PREFIX + 'dept_b'],
            'node_c': ids[PREFIX + 'center'], 'b1': b1, 'b2': b2, 'cfg_b1': cfg_b1}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        for bid in (fx['b1'], fx['b2']):
            c.execute("DELETE FROM board_config WHERE board_id=?", (bid,))
            c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
        c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
                  (PREFIX + '%',))
        c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    for acct in (U_ADMIN, U_ARCH, U_BOARD, U_VIEWER):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
    c.commit()
    c.close()


def board_by_id(res, bid):
    for b in res.get('boards', []):
        if b['board_id'] == bid:
            return b
    return None


def main():
    fx = setup()
    try:
        tok = {u: make_token(u) for u in (U_ADMIN, U_ARCH, U_BOARD, U_VIEWER)}

        print('\n【用例1】/api/me 暴露权限画像')
        code, me = http('/api/me', token=tok[U_ARCH])
        ok(code == 200, '/api/me 200（实际 %s）' % code)
        ok(fx['node_a'] in (me.get('arch_leader_nodes') or []),
           'arch_leader_nodes 含我担任负责人的节点')
        ok(fx['node_a'] in (me.get('arch_scope') or []), 'arch_scope 含我管辖的节点')
        ok(fx['node_b'] not in (me.get('arch_scope') or []), 'arch_scope 不含范围外的节点')
        ok(me.get('is_arch_owner') is True, 'is_arch_owner 为真')
        ok(fx['b1'] in (me.get('editable_boards') or []), 'editable_boards 含我管辖的看板')
        ok(fx['b2'] not in (me.get('editable_boards') or []), 'editable_boards 不含范围外的看板')
        code, me_v = http('/api/me', token=tok[U_VIEWER])
        ok(me_v.get('is_arch_owner') is False, '只读：is_arch_owner 为假')
        ok((me_v.get('editable_boards') or []) == [], '只读：editable_boards 为空')
        ok((me_v.get('arch_scope') or []) == [], '只读：arch_scope 为空')

        print('\n【用例2】/api/boards 逐看板给出能力位')
        code, res = http('/api/boards', token=tok[U_ARCH])
        b1 = board_by_id(res, fx['b1'])
        b2 = board_by_id(res, fx['b2'])
        ok(code == 200, '/api/boards 200（实际 %s）' % code)
        ok(b1 is not None, '返回管辖范围内的看板')
        ok(b1.get('can_edit') is True, '架构负责人：范围内看板 can_edit=True')
        ok(b1.get('can_assign_owner') is True, '架构负责人：范围内看板 can_assign_owner=True')
        ok(b1.get('perm_role') == '架构负责人', 'perm_role 正确：%s' % b1.get('perm_role'))
        if b2 is not None:
            ok(b2.get('can_edit') is False, '架构负责人：范围外看板 can_edit=False')
        code, res_b = http('/api/boards', token=tok[U_BOARD])
        ob2 = board_by_id(res_b, fx['b2'])
        ok(ob2 is not None, '看板负责人：能看到自己负责的看板')
        if ob2 is not None:
            ok(ob2.get('can_edit') is True, '看板负责人：自己的看板 can_edit=True')
            ok(ob2.get('can_assign_owner') is False,
               '看板负责人：不能指派看板负责人（属上级权）')
            ok(ob2.get('perm_role') == '看板负责人', 'perm_role 正确：%s' % ob2.get('perm_role'))
        code, res_v = http('/api/boards', token=tok[U_VIEWER])
        ok(all(not b.get('can_edit') for b in res_v.get('boards', [])),
           '只读：所有看板 can_edit=False')

        print('\n【用例3】/api/org/tree 逐节点给出能力位')
        code, tree = http('/api/org/tree', token=tok[U_ARCH])

        def find_node(nodes, nid):
            for n in nodes or []:
                if n['id'] == nid:
                    return n
                r = find_node(n.get('children'), nid)
                if r:
                    return r
            return None

        na = find_node(tree.get('tree'), fx['node_a'])
        nb = find_node(tree.get('tree'), fx['node_b'])
        ok(code == 200, '/api/org/tree 200（实际 %s）' % code)
        ok(na is not None and na.get('can_config_bind') is True,
           '架构负责人：范围内节点 can_config_bind=True')
        ok(nb is not None and nb.get('can_config_bind') is False,
           '架构负责人：范围外节点 can_config_bind=False')
        ok(na is not None and na.get('can_manage_node') is False,
           '架构负责人：节点结构增删改仍限管理员（can_manage_node=False）')
        code, tree_v = http('/api/org/tree', token=tok[U_VIEWER])
        nv = find_node(tree_v.get('tree'), fx['node_a'])
        ok(nv is not None and nv.get('can_config_bind') is False,
           '只读：节点 can_config_bind=False')
        code, tree_a = http('/api/org/tree', token=tok[U_ADMIN])
        naa = find_node(tree_a.get('tree'), fx['node_a'])
        ok(naa is not None and naa.get('can_config_bind') is True and
           naa.get('can_manage_node') is True, '管理员：节点能力位全开')

        print('\n【用例4】越权拦截 → 403 + 统一错误体')
        code, r = http('/api/boards/%s/acl' % fx['b1'], 'PUT',
                       {'owner': U_VIEWER}, token=tok[U_VIEWER])
        ok(code == 403, '只读指派看板负责人 → 403（实际 %s）' % code)
        ok(r.get('error') == 'PERMISSION_DENIED', '返回统一错误码：%s' % r.get('error'))
        ok('need_role' in r and 'have_role' in r, '错误体含角色信息')
        code, r = http('/api/boards/%s/acl' % fx['b2'], 'PUT',
                       {'owner': U_VIEWER}, token=tok[U_ARCH])
        ok(code == 403, '架构负责人指派范围外看板的负责人 → 403（实际 %s）' % code)
        code, r = http('/api/board-config/%s' % fx['cfg_b1'], 'PUT',
                       {'board_id': fx['b1'], 'dept': PREFIX + 'dept_a',
                        'attr': '日常', 'status': '启用'},
                       token=tok[U_VIEWER])
        ok(code == 403, '只读改看板配置 → 403（实际 %s）' % code)
    finally:
        cleanup(fx)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (passed, failed))
    return 1 if failed else 0


sys.exit(main())
