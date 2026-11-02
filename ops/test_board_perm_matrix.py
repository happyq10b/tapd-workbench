#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""看板 / 板块 / 统计 三层权限一致性测试

背景：2026-11-02 发现 —— 看板级权限（boards）已生效，但**板块级**权限
（users.allowed_columns）没有下推到所有统计点：
  · /api/boards 的 card_count 直接 GROUP BY 统计 cards 表 → 只做了看板级过滤
    → 「看板管理」显示的卡片数与用户实际能看到的条数对不上（实测 6 vs 2）
  · /api/boards 的 col_years 同样未按可见板块过滤
  · /api/boards/{id}/columns 的 counts 未过滤（越权板块的条数随响应下发）

本测试用临时夹具（4 角色 × 3 板块）验证：
  ① 看板级：不同角色可见的看板集合不同
  ② 板块级：板块白名单收窄后，可见板块同步收窄
  ③ 统计：/api/boards 的 card_count == /api/cards 的 total（口径统一）
  ④ 统计：板块级 card_count 与该板块实际事项数一致
  ⑤ 越权：传无权看板的 board_id → 403 / 0
  ⑥ 无权限用户：什么都看不到

运行：ops/.localvenv/Scripts/python.exe ops/test_board_perm_matrix.py
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw, make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')

PREFIX = '__pm_'
BID = PREFIX + 'board'
COLS = [('COL_1', '板块一'), ('COL_2', '板块二'), ('COL_3', '板块三')]
# 每板块 2 条事项（1 done / 1 open）→ 整板 6 条
U_ADMIN = PREFIX + 'admin'
U_EDITOR = PREFIX + 'editor'
U_COL1 = PREFIX + 'col1'      # 板块白名单只给 COL_1
U_VIEWER = PREFIX + 'viewer'
U_NONE = PREFIX + 'none'      # 无任何架构归属

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
    c.execute("DELETE FROM cards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("""DELETE FROM org_appointments WHERE member_id IN
                 (SELECT id FROM team_members WHERE account LIKE ?)""", (PREFIX + '%',))
    c.commit()
    c.close()


def setup():
    cleanup()
    c = db()
    now = "2026-11-02 12:00:00"
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)",
              (BID, '【PM】权限矩阵看板', 'ws_pm', now))
    c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, created_at)
                 VALUES (?,?,?,?,?,?)""", (BID, '核算部', 4, '日常', '启用', now))
    for ci, cn in COLS:
        c.execute("""INSERT INTO board_columns (col_key, column_id, board_id, column_name,
                       created_at, creator, nature, year, pinned)
                     VALUES (?,?,?,?,?,?,?,?,0)""",
                  (BID + '::' + cn, ci, BID, cn, now, 'seed', '日常', '2026'))
        for k, st in enumerate(('done', 'open')):
            c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name,
                           workspace_id, card_name, status, status_name, creator, created, parent_id, version, deleted)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                      ('%sc_%s_%d' % (PREFIX, ci, k), BID, '【PM】权限矩阵看板', ci, cn, 'ws_pm',
                       '【PM】%s事项%d' % (cn, k), st, '已完成' if st == 'done' else '未完成',
                       PREFIX + 'seed', now))
    # 账号：admin（无需任命）/ editor / col1（板块白名单）/ viewer / none（无归属）
    accounts = [
        (U_ADMIN, 'admin', None, None),
        (U_EDITOR, 'editor', '*', '*'),
        (U_COL1, 'editor', '*', json.dumps({BID: ['COL_1']})),
        (U_VIEWER, 'viewer', '*', '*'),
        (U_NONE, 'editor', '*', '*'),
    ]
    for acct, role, ab, ac in accounts:
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        if role != 'admin' and acct != U_NONE:
            # 任命到核算部（node=4）→ 可见该看板
            c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                         VALUES (?,?,'member',0,?)""", (4, mid, now))
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,?,?,?,?)""",
                  (acct, hash_pw('At159357'), role, ab or '*', ac or '*', now))
    c.commit()
    c.close()


def board_card_count(token):
    _, r = http('/api/boards', token=token)
    for b in (r.get('boards') or []):
        if b['board_id'] == BID:
            return b.get('card_count')
    return None


def main():
    setup()
    try:
        T = {u: make_token(u) for u in (U_ADMIN, U_EDITOR, U_COL1, U_VIEWER, U_NONE)}

        print('\n【用例1】看板级：各角色可见板块集合')
        _, me_admin = http('/api/me', token=T[U_ADMIN])
        _, me_editor = http('/api/me', token=T[U_EDITOR])
        _, me_none = http('/api/me', token=T[U_NONE])
        ok(len(me_admin.get('boards') or []) > 0, '管理员可见看板：%d 个' % len(me_admin.get('boards') or []))
        ok(len(me_editor.get('boards') or []) > 0, '可编辑可见看板：%d 个' % len(me_editor.get('boards') or []))
        ok(len(me_none.get('boards') or []) == 0, '无归属用户可见看板：0 个')
        ok(not (me_none.get('depts') or []), '无归属用户部门清单为空：%s' % (me_none.get('depts') or []))

        print('\n【用例2】板块级：白名单收窄后可见板块同步收窄')
        _, cols_all = http('/api/boards/%s/columns' % BID, token=T[U_EDITOR])
        _, cols_one = http('/api/boards/%s/columns' % BID, token=T[U_COL1])
        names_all = [c['column_name'] for c in (cols_all.get('columns') or [])]
        names_one = [c['column_name'] for c in (cols_one.get('columns') or [])]
        ok(len(names_all) == 3, '可编辑看到 3 个板块：%s' % names_all)
        ok(names_one == ['板块一'], '板块白名单用户只看到「板块一」：%s' % names_one)

        print('\n【用例3】统计口径统一：/api/boards 的 card_count == /api/cards 的 total')
        for name, u in (('管理员', U_ADMIN), ('可编辑', U_EDITOR),
                        ('板块白名单', U_COL1), ('只读', U_VIEWER)):
            _, cd = http('/api/cards?board_id=%s&size=999' % BID, token=T[u])
            bc = board_card_count(T[u])
            ok(bc == cd.get('total'),
               '%s：boards.card_count=%s == cards.total=%s' % (name, bc, cd.get('total')))
        # 无权限用户：看板本身就不在列表里（看板级已过滤）→ card_count 取不到（None）
        _, cd_none = http('/api/cards?board_id=%s&size=999' % BID, token=T[U_NONE])
        ok(board_card_count(T[U_NONE]) in (None, 0),
           '无权限：看板不可见，card_count 取不到=None，与 cards.total=0 一致：%s vs %s'
           % (board_card_count(T[U_NONE]), cd_none.get('total')))
        ok(board_card_count(T[U_COL1]) == 2,
           '板块白名单用户的看板卡片数 = 2（只算授权板块）：%s' % board_card_count(T[U_COL1]))
        # 无权限用户：看板本身就不出现在列表里（看板级已过滤）→ card_count 取不到（None）
        ok(board_card_count(T[U_NONE]) in (None, 0),
           '无权限用户的看板卡片数不可见（看板已被过滤，取不到=None）：%s'
           % board_card_count(T[U_NONE]))

        print('\n【用例4】板块级计数与该板块实际事项数一致')
        _, cols_one = http('/api/boards/%s/columns' % BID, token=T[U_COL1])
        c1 = (cols_one.get('columns') or [])
        ok(len(c1) == 1 and c1[0].get('card_count') == 2,
           '「板块一」card_count=2：%s' % [(c['column_name'], c['card_count']) for c in c1])
        _, cols_all = http('/api/boards/%s/columns' % BID, token=T[U_EDITOR])
        ok(all(c.get('card_count') == 2 for c in (cols_all.get('columns') or [])),
           '各板块 card_count 均为 2：%s' % [(c['column_name'], c['card_count'])
                                       for c in (cols_all.get('columns') or [])])

        print('\n【用例5】越权访问被拒')
        code, _ = http('/api/boards/%s/columns' % BID, token=T[U_NONE])
        ok(code == 403, '无权限用户取板块列表 → 403：%s' % code)
        _, cd_none = http('/api/cards?board_id=%s&size=999' % BID, token=T[U_NONE])
        ok(cd_none.get('total') == 0, '无权限用户取事项 → 0 条：%s' % cd_none.get('total'))

        print('\n【用例6】统计带按板块取数时同样遵守板块权限')
        _, ov_admin = http('/api/overview?board_id=%s' % BID, token=T[U_ADMIN])
        _, ov_col1 = http('/api/overview?board_id=%s' % BID, token=T[U_COL1])
        ok(ov_admin.get('total') == 6, '管理员统计 6 条：%s' % ov_admin.get('total'))
        ok(ov_col1.get('total') == 2, '板块白名单用户统计 2 条：%s' % ov_col1.get('total'))
    finally:
        cleanup()

    print('\n结果：%d 通过 / %d 失败' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
