#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""专项测试：小组成员**不继承父部门看板**（2026-11-02 修复）

背景（用户报告的真实缺陷）：
  苏春景（scj）的账号在【架构管理】里被任命到 管理部(dept) + 费用组(group) + 税务组(group)，
  但这三个节点**都没有绑定任何看板**（管理部不拥有看板；费用组/税务组的 workgroups.boards 为空）
  → 按语义他**不该看到任何看板**。
  但修复前他能看到**全部 7 个看板**。

根因：`_member_authority_nodes()` 把**小组节点向上提升**到最近的部门祖先
  → 费用组/税务组的父节点是核算部 → scope 含核算部(4)
  → `_dept_stage_boards()` 直接把 scope 当部门去查归属看板
  → 小组成员继承了父部门的**全部看板**。

修复：新增 `_member_appointed_nodes()`（保留**原始任命节点**，不提升），
  `_dept_stage_boards()` 改用 `_node_bound_boards()` 按节点类型派生：
    · 部门(dept)/中心(center) → 该节点自己拥有的看板
    · 小组(group)             → 该小组自己绑定的看板（没绑定 = 没有），**不继承父部门**

⚠️ 夹具纪律（§3.3）：专属前缀 `__dg_` + try/finally 全量清理。
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

PREFIX = '__dg_'
PASS = 0
FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS ' + msg)
    else:
        FAIL += 1
        print('  FAIL ' + msg)


def cleanup():
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'),
                   ('board_columns', 'board_id'), ('boards', 'board_id'),
                   ('board_config', 'board_id'), ('users', 'username'),
                   ('team_members', 'account'), ('team_members', 'name'),
                   ('org_nodes', 'name'), ('workgroups', 'name')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("""DELETE FROM org_appointments WHERE member_id IN
                 (SELECT id FROM team_members WHERE account LIKE ?)""", (PREFIX + '%',))
    c.execute("""DELETE FROM org_appointments WHERE node_id IN
                 (SELECT id FROM org_nodes WHERE name LIKE ?)""", (PREFIX + '%',))
    c.commit()
    c.close()


def build():
    """造一棵独立的架构树 + 看板，验证各节点的可见性派生"""
    from app.app import hash_pw
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-02 17:10:00'
    # 部门 D1（拥有看板 B1）→ 小组 G1（绑定看板 B2）→ 小组 G2（不绑定任何看板）
    # ⚠️ wg_id 必须指向对应的 workgroups.id —— _node_bound_boards 靠它找
    #    小组的显式看板绑定（wg_id=0 → 读不到 → 小组绑定永远为空）
    c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
              " VALUES (?,?,'dept',?,9001,0,'',0,?)", (9001, PREFIX + 'D1', 0, now))
    c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
              " VALUES (?,?,'group',?,9002,0,'',0,?)", (9002, PREFIX + 'G1', 9001, now))
    c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
              " VALUES (?,?,'group',?,9003,0,'',0,?)", (9003, PREFIX + 'G2', 9001, now))
    # 看板 B1 归属 D1；看板 B2 不归属任何部门（靠小组绑定）
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,'','','',0,?)", (PREFIX + 'B1', PREFIX + '看板一', now))
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,'','','',0,?)", (PREFIX + 'B2', PREFIX + '看板二', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (PREFIX + 'B1', PREFIX + 'D1', 9001, '日常', '启用', now))
    # B2 也登记归属（挂到小组节点 G1）—— 不登记会落入
    # 「未归属部门的看板 = 公共看板 = 全员可见」规则，干扰用例判定
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (PREFIX + 'B2', PREFIX + 'G1', 9002, '日常', '启用', now))
    # 工作组：G1 绑定 B2；G2 不绑定
    c.execute("INSERT INTO workgroups (id,name,parent_id,leader,function,boards,created_at)"
              " VALUES (?,?,0,'','',?,?)", (9002, PREFIX + 'G1', PREFIX + 'B2', now))
    c.execute("INSERT INTO workgroups (id,name,parent_id,leader,function,boards,created_at)"
              " VALUES (?,?,0,'','','',?)", (9003, PREFIX + 'G2', now))
    # 三个成员：分别任命到 D1 / G1 / G2
    for acct, node in ((PREFIX + 'dept', 9001), (PREFIX + 'grp1', 9002), (PREFIX + 'grp2', 9003)):
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
                  " VALUES (?,?,'member',0,?)", (node, mid, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
    c.commit()
    c.close()


def main():
    from app.app import user_allowed, _member_appointed_nodes, _member_dept_scope
    cleanup()
    # ⚠️ 真实数据的**基线必须在造夹具之前实测**（2026-11-04 教训）：
    #    用例5 曾硬编码「== 7 个看板」→ 用户自己复制看板（合法数据）就让断言假失败。
    #    基线实测于 cleanup() 之后、build() 之前 —— 此刻库中无本测试夹具。
    _base_yh = len(user_allowed('yh')[0] or set())
    _base_wwn = len(user_allowed('wwn')[0] or set())
    build()
    try:
        print('\n【用例1】小组节点不向上提升（根因修复点）')
        nodes, _src = _member_appointed_nodes(PREFIX + 'grp2')
        ok(nodes == {9003},
           'G2 成员的原始任命节点 = G2 自身（不被提升到父部门 D1）：%s' % sorted(nodes))
        scope = _member_dept_scope(PREFIX + 'grp2')
        ok(9003 not in scope,
           '注意：展示用的 scope 仍按祖先算（%s）—— 那是展示语义，权限判定不用它' % sorted(scope))

        print('\n【用例2】各成员可见看板符合「节点自己绑定的」语义（2026-11-05 新规则）')
        # 公共看板 = 归属中心 / 未归属（生产「综合」已移入财务中心 → 全员可见）
        c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
        center_ids = {r[0] for r in c.execute("SELECT id FROM org_nodes WHERE node_type='center'")}
        all_ids = {r[0] for r in c.execute('SELECT board_id FROM boards')}
        owned_ids = {r[0] for r in c.execute(
            'SELECT board_id FROM board_config WHERE dept_node_id > 0 AND dept_node_id NOT IN (%s)'
            % ','.join('?' * len(center_ids)), tuple(center_ids))} if True else set()
        c.close()
        public = all_ids - owned_ids
        b_dept, _c = user_allowed(PREFIX + 'dept')
        ok(b_dept == public,
           '部门成员 → 不再自动继承部门看板，只见公共看板（实际 %s）' % sorted(b_dept or []))
        b_g1, _c = user_allowed(PREFIX + 'grp1')
        ok(b_g1 == public | {PREFIX + 'B2'},
           'G1 成员 → 公共 + G1 自己绑定的 B2（实际 %s）' % sorted(b_g1 or []))
        b_g2, _c = user_allowed(PREFIX + 'grp2')
        ok(b_g2 == public,
           'G2 成员（G2 未绑定任何看板）→ 只见公共看板（实际 %s）' % sorted(b_g2 or []))

        print('\n【用例3】关键回归：G2 成员不得继承父部门 D1 的看板')
        ok(PREFIX + 'B1' not in (b_g2 or set()),
           'G2 成员看不到父部门 D1 的看板 B1（修复前会看到）')

        print('\n【用例4】小组绑定的看板可见，且不越界')
        ok(PREFIX + 'B1' not in (b_g1 or set()),
           'G1 成员只看到 B2，不会顺带看到 D1 的 B1（实际 %s）' % sorted(b_g1 or []))

    finally:
        cleanup()
        print('\n=== 夹具已清理 ===')

    # ⚠️ 真实数据断言必须在**夹具清理之后**跑 ——
    #    否则夹具的看板会混进真实账号的可见集合，数字对不上。
    print('\n【用例5】真实数据回归（夹具已清理，避免干扰）')
    # 生产公共看板 = 归属中心 / 未归属（2026-11-05：「综合」已移入财务中心 → 全员可见）
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    center_ids = {r[0] for r in c.execute("SELECT id FROM org_nodes WHERE node_type='center'")}
    all_ids = {r[0] for r in c.execute('SELECT board_id FROM boards')}
    owned_ids = {r[0] for r in c.execute(
        'SELECT board_id FROM board_config WHERE dept_node_id > 0 AND dept_node_id NOT IN (%s)'
        % ','.join('?' * len(center_ids)), tuple(center_ids))}
    c.close()
    _public_real = all_ids - owned_ids
    b_scj, _c = user_allowed('scj')
    ok(b_scj == _public_real,
       '苏春景（管理部 + 费用组 + 税务组，均未绑定看板）→ 只见公共看板（%d 个）：%s'
       % (len(b_scj or []), sorted(b_scj or [])))
    b_tyl, _c = user_allowed('tyl')
    ok(b_tyl == _public_real,
       '谭亚利（总账部部长，总账部不拥有看板 + 小组未绑定）→ 只见公共看板：%s' % sorted(b_tyl or []))
    b_yh, _c = user_allowed('yh')
    ok(b_yh and len(b_yh) == _base_yh,
       '余河（财务中心）可见看板数 = 进入时基线 %d（管理层全范围不受夹具影响）：%d 个'
       % (_base_yh, len(b_yh or [])))
    b_wwn, _c = user_allowed('wwn')
    ok(b_wwn and len(b_wwn) == _base_wwn,
       '王伟娜（核算部部长）可见看板数 = 进入时基线 %d：%d 个' % (_base_wwn, len(b_wwn or [])))
    b_none, _c = user_allowed('zhangsan')
    ok(not b_none,
       '无任何架构归属的账号 → 0 个看板（fail-closed）：%s' % sorted(b_none or []))
    print('\n结果：%d 通过 / %d 失败' % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
