#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统计带权限隔离测试：/api/overview 的三个统计必须只算「权限范围内」的数据。

背景：页面上三个统计（总事项 / 已完成 / 未完成）来自 GET /api/overview。
本测试用与 test_perm_scope.py 相同的夹具模式建临时账号，验证：
  ① 不同权限账号看到的统计**互不相同**（权限外的数据不计入）
  ② 统计总数 == 该账号 /api/cards 能取到的条数（两处口径一致）
  ③ 带 board_id 参数时，统计只算该板块，且**不越权**（传无权板块 → 0）
  ④ 板块级权限（allowed_columns）生效：收窄板块后统计同步收窄
  ⑤ admin 看到全部（超级管理员不受架构过滤限制）

运行：ops/.localvenv/Scripts/python.exe ops/test_overview_perm.py
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')

PREFIX = '__ov_'
TEST_BOARD = PREFIX + 'board_a'       # 归「资金部」
TEST_BOARD2 = PREFIX + 'board_b'      # 归「管理部」
CARD_X = PREFIX + 'card_x'
CARD_Y = PREFIX + 'card_y'
USR_A = PREFIX + 'user_a'             # 任命到资金部 → 看得到 TEST_BOARD
USR_B = PREFIX + 'user_b'             # 任命到核算部 → 看得到原有看板
USR_C = PREFIX + 'user_c'             # 无架构归属 → 只看公共看板
NODE_ZICHU, NODE_GUANLI, NODE_HESUAN = 5, 2, 4

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  FAIL ' + msg)


def http(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except Exception:
            return e.code, {}


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def cleanup():
    c = db()
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('users', 'username'),
                   ('team_members', 'account'), ('board_config', 'board_id')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("""DELETE FROM org_appointments WHERE member_id IN
                 (SELECT id FROM team_members WHERE account LIKE ?)""", (PREFIX + '%',))
    c.commit()
    c.close()


def setup():
    cleanup()
    c = db()
    now = "2026-11-02 12:00:00"
    for bid, name, dept, node, part in ((TEST_BOARD, '【测试】A看板', '资金部', NODE_ZICHU, USR_A),
                                        (TEST_BOARD2, '【测试】B看板', '管理部', NODE_GUANLI, USR_B)):
        c.execute("INSERT INTO boards (board_id, board_name, workspace_id, participants, created_at)"
                  " VALUES (?,?,?,?,?)",
                  (bid, name, 'ws_ov', part, now))
        c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, created_at)
                     VALUES (?,?,?,?,?,?)""", (bid, dept, node, '日常', '启用', now))
    # 2026-11-05 新规则：部门成员不再自动继承部门看板 → A/B 以【看板参与人】身份可见各自看板
    # A 看板里 4 条事项：2 done / 1 open / 1 progressing
    stats = [('done', '已完成'), ('done', '已完成'), ('open', '未完成'), ('progressing', '进行中')]
    for i, (st, stn) in enumerate(stats):
        c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name,
                       workspace_id, card_name, status, status_name, creator, created, parent_id, version, deleted)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                  (PREFIX + 'card_%d' % i, TEST_BOARD, '【测试】A看板', 'COL_X', '测试板块',
                   'ws_ov', '【测试】事项%d' % i, st, stn, PREFIX + 'seed', now))
    # B 看板里 2 条
    for i in range(2):
        c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name,
                       workspace_id, card_name, status, status_name, creator, created, parent_id, version, deleted)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                  (PREFIX + 'bcard_%d' % i, TEST_BOARD2, '【测试】B看板', 'COL_Y', 'B板块',
                   'ws_ov', '【测试】B事项%d' % i, 'done', '已完成', PREFIX + 'seed', now))
    members = {}
    for key, name, acct in (('a', PREFIX + '成员A', USR_A), ('b', PREFIX + '成员B', USR_B),
                            ('c', PREFIX + '成员C', USR_C)):
        cur = c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                         (name, acct, now))
        members[key] = cur.lastrowid
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (?,?,'member',0,?)""", (NODE_ZICHU, members['a'], now))
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (?,?,'member',0,?)""", (NODE_HESUAN, members['b'], now))
    for acct, role in ((USR_A, 'editor'), (USR_B, 'editor'), (USR_C, 'editor')):
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,'','%s','*','*',?)""" % role, (acct, now))
    c.commit()
    c.close()


def main():
    setup()
    try:
        tok_a = make_token(USR_A)
        tok_b = make_token(USR_B)
        tok_c = make_token(USR_C)
        tok_admin = make_token('admin')

        print('\n【用例1】不同权限账号的统计必须不同')
        _, ov_a = http('/api/overview', token=tok_a)
        _, ov_b = http('/api/overview', token=tok_b)
        _, ov_c = http('/api/overview', token=tok_c)
        _, ov_admin = http('/api/overview', token=tok_admin)
        ok(ov_a.get('total') != ov_b.get('total'),
           'A（资金部）与 B（核算部）统计不同：A=%s B=%s' % (ov_a.get('total'), ov_b.get('total')))
        ok(ov_a.get('total') - ov_c.get('total') == 4 and ov_b.get('total') - ov_c.get('total') == 2,
           'C（无架构归属）只统计公共看板，A/B 各多出自己参与人看板的 4/2 条：C=%s A=%s B=%s'
           % (ov_c.get('total'), ov_a.get('total'), ov_b.get('total')))
        ok(ov_admin.get('total') > ov_a.get('total'),
           'admin 统计大于受限账号：admin=%s A=%s' % (ov_admin.get('total'), ov_a.get('total')))

        print('\n【用例2】统计口径 == /api/cards 取到的条数')
        for name, tok in (('A', tok_a), ('B', tok_b), ('C', tok_c), ('admin', tok_admin)):
            _, ov = http('/api/overview', token=tok)
            _, cd = http('/api/cards?size=9999', token=tok)
            ok(ov.get('total') == cd.get('total'),
               '%s：overview.total=%s == cards.total=%s' % (name, ov.get('total'), cd.get('total')))

        print('\n【用例3】带 board_id：只算该板块，且不越权')
        _, ov_a1 = http('/api/overview?board_id=' + TEST_BOARD, token=tok_a)
        ok(ov_a1.get('total') == 4, 'A 在自己的看板上统计 = 4：%s' % ov_a1.get('total'))
        ok(ov_a1.get('done') == 2, 'A 在自己的看板上已完成 = 2：%s' % ov_a1.get('done'))
        ok(ov_a1.get('open') == 1, 'A 在自己的看板上未完成 = 1：%s' % ov_a1.get('open'))
        # 越权：B 看板对 A 不可见 → 统计必须为 0
        _, ov_cross = http('/api/overview?board_id=' + TEST_BOARD2, token=tok_a)
        ok(ov_cross.get('total') == 0,
           'A 传无权限的 B 看板 → 统计为 0（不越权）：%s' % ov_cross.get('total'))
        # C 无任何架构归属 → 传任何测试看板都是 0
        _, ov_c1 = http('/api/overview?board_id=' + TEST_BOARD, token=tok_c)
        ok(ov_c1.get('total') == 0, 'C 传 A 看板 → 统计为 0：%s' % ov_c1.get('total'))

        print('\n【用例4】板块级权限（allowed_columns）生效')
        # 把 A 的板块白名单收窄成空 JSON → 该看板可见但板块不可见 → 统计归零
        c = db()
        c.execute("UPDATE users SET allowed_columns=? WHERE username=?",
                  (json.dumps({TEST_BOARD: ['__none__']}), USR_A))
        c.commit()
        c.close()
        tok_a2 = make_token(USR_A)
        _, ov_a2 = http('/api/overview', token=tok_a2)
        _, ov_a2_b = http('/api/overview?board_id=' + TEST_BOARD, token=tok_a2)
        ok(ov_a2.get('total') == ov_c.get('total'),
           '板块权限收窄后 A 只剩公共看板统计（=%s）' % ov_a2.get('total'))
        ok(ov_a2_b.get('total') == 0, '板块权限收窄后带 board_id 也为 0：%s' % ov_a2_b.get('total'))
        # 恢复
        c = db()
        c.execute("UPDATE users SET allowed_columns='*' WHERE username=?", (USR_A,))
        c.commit()
        c.close()

        print('\n【用例5】admin 不受架构过滤限制')
        _, ov_admin1 = http('/api/overview?board_id=' + TEST_BOARD2, token=tok_admin)
        ok(ov_admin1.get('total') == 2, 'admin 可见 B 看板统计 = 2：%s' % ov_admin1.get('total'))

        print('\n【用例6】空串 board_id = 不过滤（保持既有语义）')
        _, ov_empty = http('/api/overview?board_id=', token=tok_a)
        _, ov_none = http('/api/overview', token=tok_a)
        ok(ov_empty.get('total') == ov_none.get('total'),
           'board_id 为空串与不传等价：%s vs %s' % (ov_empty.get('total'), ov_none.get('total')))

        print('\n【用例7】/api/me 的部门清单必须按权限过滤')
        # A 任命到资金部 → 只见资金部（TEST_BOARD 归属）；B 任命到核算部 → 只见核算部
        _, me_a = http('/api/me', token=tok_a)
        _, me_b = http('/api/me', token=tok_b)
        _, me_admin = http('/api/me', token=tok_admin)
        ok(me_a.get('depts') == ['财务中心', '资金部'],
           'A 只看到资金部 + 财务中心（公共看板归属，2026-11-05）：%s' % (me_a.get('depts') or []))
        ok('管理部' not in (me_a.get('depts') or []),
           'A 看不到「管理部」（该部门无其可见看板）')
        ok('核算部' not in (me_a.get('depts') or []),
           'A 看不到「核算部」')
        ok('管理部' in (me_b.get('depts') or []) and '核算部' not in (me_b.get('depts') or []),
           'B 能看到「管理部」（参与人看板归属），看不到「核算部」（新规则，成员身份不授予可见性）：%s'
           % (me_b.get('depts') or []))
        ok(len(me_admin.get('depts') or []) > len(me_a.get('depts') or []),
           'admin 看到的部门多于受限账号：admin=%s A=%s'
           % (me_admin.get('depts'), me_a.get('depts')))
        # C 无任何架构归属 → 只看到公共看板归属的「财务中心」
        _, me_c = http('/api/me', token=tok_c)
        ok(me_c.get('depts') == ['财务中心'],
           'C 只见公共看板归属「财务中心」（2026-11-05 综合全员可见）：%s' % (me_c.get('depts') or []))
        # 部门清单 = 可见看板的归属部门 ∪ 中心（2026-11-05：财务中心恒显示）
        a_depts_from_boards = {b.get('dept') for b in (me_a.get('boards') or []) if b.get('dept')}
        ok(set(me_a.get('depts') or []) == a_depts_from_boards | {'财务中心'},
           '部门清单 == 可见看板归属部门 + 财务中心（恒显示）：%s vs %s'
           % (me_a.get('depts'), sorted(a_depts_from_boards)))
    finally:
        cleanup()

    print('\n结果：%d 通过 / %d 失败' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
