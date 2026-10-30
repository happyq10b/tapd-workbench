# -*- coding: utf-8 -*-
"""基于架构（角色/权限）的看板与板块可见性 · 端到端回归测试。

覆盖（对应「普通用户登录后仍可看到全部看板和板块」的问题）：
  1. admin = 超级管理员：拥有当前及未来新增的全部权限，不受架构过滤限制
  2. 不同架构的普通用户：只看到其所属架构授权的看板（互不可见）
  3. 无架构归属的普通账号：fail-closed（看不到任何看板）
  4. 账号级白名单只能在架构授权范围内**收窄**，不能越权授予
  5. 后端接口真正拦截：越权写 403 / 越权读 403 / 列表不返回
  6. 前端口径一致：/api/me、/api/boards、/api/cards 三者看板集合一致
  7. 板块（column）级权限：不可见的板块既读不到也写不进

用法：先起服务（默认 127.0.0.1:8100），再
    python ops/test_perm_scope.py
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('TAPD_BASE', 'http://127.0.0.1:8100')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get('TAPD_DB', os.path.join(ROOT, 'src', 'app.db'))

sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token   # noqa: E402

# ---------- 测试夹具（前缀 __pt_，结束全部清理） ----------
PREFIX = '__pt_'
TEST_BOARD = PREFIX + 'board_zichu'      # 归属「资金部」的新看板
TEST_BOARD2 = PREFIX + 'board_guanli'    # 归属「管理部」的新看板
CARD_X = PREFIX + 'card_x'               # 在 TEST_BOARD 内，板块 COL_X
CARD_Y = PREFIX + 'card_y'               # 在 TEST_BOARD 内，板块 COL_Y
USR_A = PREFIX + 'user_a'                # 任命到资金部（拥有 TEST_BOARD）
USR_B = PREFIX + 'user_b'                # 任命到核算部（拥有原有看板）
USR_C = PREFIX + 'user_c'                # 无任何架构归属
USR_D = PREFIX + 'user_d'                # role=admin，且无任何架构归属
USR_E = PREFIX + 'user_e'                # 无架构归属，但账号白名单写了 TEST_BOARD
NODE_ZICHU = 5                            # 资金部
NODE_GUANLI = 2                           # 管理部
NODE_HESUAN = 4                           # 核算部

passed = 0
failed = 0


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


# ---------------- 夹具准备 / 清理 ----------------
def cleanup():
    c = db()
    c.execute("DELETE FROM comments WHERE card_id IN (?,?)", (CARD_X, CARD_Y))
    c.execute("DELETE FROM actions WHERE card_id IN (?,?)", (CARD_X, CARD_Y))
    c.execute("DELETE FROM card_subtasks WHERE card_id IN (?,?)", (CARD_X, CARD_Y))
    c.execute("DELETE FROM cards WHERE card_id IN (?,?)", (CARD_X, CARD_Y))
    # 经接口新建的卡片 id 不含前缀（NC…），按 board_id 一并清掉，避免残留
    c.execute("DELETE FROM cards WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM board_config WHERE board_id IN (?,?)", (TEST_BOARD, TEST_BOARD2))
    c.execute("DELETE FROM boards WHERE board_id IN (?,?)", (TEST_BOARD, TEST_BOARD2))
    c.execute("""DELETE FROM org_appointments WHERE member_id IN
                 (SELECT id FROM team_members WHERE name LIKE ?||'%')""", (PREFIX,))
    c.execute("DELETE FROM team_members WHERE name LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM users WHERE username LIKE ?||'%'", (PREFIX,))
    c.commit()
    c.close()


def setup():
    cleanup()
    c = db()
    now = "2026-10-30 12:00:00"
    # 两个新看板：一个归资金部、一个归管理部
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)",
              (TEST_BOARD, '【测试】资金部看板', 'ws_pt', now))
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)",
              (TEST_BOARD2, '【测试】管理部看板', 'ws_pt', now))
    c.execute("""INSERT INTO board_config (board_id, year, dept, dept_node_id, attr, status, created_at)
                 VALUES (?,?,?,?,?,?,?)""",
              (TEST_BOARD, '2026', '资金部', NODE_ZICHU, '日常', '启用', now))
    c.execute("""INSERT INTO board_config (board_id, year, dept, dept_node_id, attr, status, created_at)
                 VALUES (?,?,?,?,?,?,?)""",
              (TEST_BOARD2, '2026', '管理部', NODE_GUANLI, '日常', '启用', now))
    # 两个卡片，分处不同板块（用于板块级权限验证）
    for cid, col, name in ((CARD_X, 'COL_X', '【测试】X 板块事项'), (CARD_Y, 'COL_Y', '【测试】Y 板块事项')):
        c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name,
                       workspace_id, card_name, status, status_name, creator, created, parent_id, version, deleted)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                  (cid, TEST_BOARD, '【测试】资金部看板', col, '板块' + col, 'ws_pt', name,
                   'open', '未开始', PREFIX + 'seed', now))
    # 成员 + 任命
    members = {}
    for key, name, account in (('a', PREFIX + '成员A', USR_A),
                               ('b', PREFIX + '成员B', USR_B),
                               ('c', PREFIX + '成员C', USR_C),
                               ('d', PREFIX + '成员D', USR_D),
                               ('e', PREFIX + '成员E', USR_E)):
        cur = c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                         (name, account, now))
        members[key] = cur.lastrowid
    # A → 资金部；B → 核算部；C/D/E 不任命
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (?,?,'member',0,?)""", (NODE_ZICHU, members['a'], now))
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (?,?,'member',0,?)""", (NODE_HESUAN, members['b'], now))
    # 账号：A/B/C/E 为 editor，D 为 admin；E 的账号白名单写了新看板（但无架构归属）
    for key, acct, role, boards in (('a', USR_A, 'editor', '*'), ('b', USR_B, 'editor', '*'),
                                    ('c', USR_C, 'editor', '*'), ('d', USR_D, 'admin', '*'),
                                    ('e', USR_E, 'editor', TEST_BOARD)):
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,'','%s',?,'*',?)""" % role,
                  (acct, boards, now))
    c.commit()
    c.close()


def board_ids_of_user(token):
    code, r = http('/api/me', token=token)
    if code != 200:
        return code, None
    return code, {b['board_id'] for b in r.get('boards', [])}


def base_board_ids():
    """测试看板之外、原本就存在的看板集合（核对用）"""
    c = db()
    rows = c.execute("SELECT board_id FROM boards WHERE board_id NOT LIKE ?||'%'", (PREFIX,)).fetchall()
    c.close()
    return {r[0] for r in rows}


print('=== 基于架构的看板/板块可见性 ===')
try:
    code, _ = http('/api/login')
except Exception as e:
    print('无法连接服务 %s：%s' % (BASE, e))
    sys.exit(1)

setup()
try:
    origin_boards = base_board_ids()
    tok_a = make_token(USR_A)
    tok_b = make_token(USR_B)
    tok_c = make_token(USR_C)
    tok_d = make_token(USR_D)
    tok_e = make_token(USR_E)
    tok_admin = make_token('admin')

    # ---------- 1) admin = 超级管理员 ----------
    print('\n【用例1】admin 超级管理员不受架构过滤限制')
    code, vis = board_ids_of_user(tok_admin)
    ok(code == 200 and vis and TEST_BOARD in vis,
       '内置 admin 账号可见全部看板（含测试看板 %s）' % TEST_BOARD)
    code, vis_d = board_ids_of_user(tok_d)
    ok(code == 200 and vis_d and TEST_BOARD in vis_d and TEST_BOARD2 in vis_d,
       'role=admin 的账号（%s）同样不受架构过滤限制' % USR_D)
    code, r = http('/api/boards', token=tok_d)
    ok(code == 200 and {b['board_id'] for b in r.get('boards', [])} >= {TEST_BOARD, TEST_BOARD2},
       'admin 调用 /api/boards 返回全部看板')

    # ---------- 2) 不同架构的普通用户 ----------
    print('\n【用例2】普通用户按所属架构过滤看板')
    code, vis_a = board_ids_of_user(tok_a)
    ok(code == 200 and vis_a == {TEST_BOARD},
       '任命到资金部的 %s 只看到资金部看板：%s' % (USR_A, sorted(vis_a or [])))
    code, vis_b = board_ids_of_user(tok_b)
    ok(code == 200 and vis_b is not None and TEST_BOARD not in vis_b and TEST_BOARD2 not in vis_b,
       '任命到核算部的 %s 看不到资金部/管理部看板' % USR_B)
    ok(code == 200 and vis_b and vis_b <= origin_boards and vis_b,
       '任命到核算部的 %s 只看到核算部原有看板（%d 个）' % (USR_B, len(vis_b or [])))
    code, vis_c = board_ids_of_user(tok_c)
    ok(code == 200 and vis_c == set(),
       '无任何架构归属的 %s 看不到任何看板（fail-closed）：%s' % (USR_C, sorted(vis_c or [])))

    # ---------- 3) 账号白名单只能收窄，不能越权授予 ----------
    print('\n【用例3】账号级白名单只能在架构授权范围内收窄')
    code, vis_e = board_ids_of_user(tok_e)
    ok(code == 200 and vis_e == set(),
       '无架构归属但账号白名单含测试看板的 %s 仍看不到看板：%s' % (USR_E, sorted(vis_e or [])))

    # ---------- 4) 后端接口真正拦截 ----------
    print('\n【用例4】后端接口拦截（不可仅靠前端隐藏）')
    code, r = http('/api/cards?board_id=' + TEST_BOARD, token=tok_b)
    ok(code == 200 and r.get('total') == 0,
       '%s 拉取资金部看板的事项返回 0 条（实际 %s）' % (USR_B, r.get('total')))
    code, r = http('/api/cards?board_id=' + TEST_BOARD, token=tok_a)
    ok(code == 200 and r.get('total') == 2,
       '%s 拉取本部门看板的事项返回 2 条（实际 %s）' % (USR_A, r.get('total')))
    code, r = http('/api/cards/' + CARD_X + '/comments', token=tok_b)
    ok(code == 403, '%s 读取不可见看板的评论被拒（实际 %s）' % (USR_B, code))
    code, r = http('/api/cards/' + CARD_X + '/actions', token=tok_b)
    ok(code == 403, '%s 读取不可见看板的操作日志被拒（实际 %s）' % (USR_B, code))
    code, r = http('/api/cards/' + CARD_X + '/subtasks', token=tok_b)
    ok(code == 403, '%s 读取不可见看板的子事项被拒（实际 %s）' % (USR_B, code))
    code, r = http('/api/cards', 'POST', {
        'board_id': TEST_BOARD, 'card_name': '【测试】越权建卡', 'fields': {'status': 'open'}}, token=tok_b)
    ok(code == 403, '%s 在不可见看板建卡被拒（实际 %s：%s）'
       % (USR_B, code, str(r.get('detail', ''))[:40]))
    code, r = http('/api/cards', 'POST', {
        'board_id': TEST_BOARD, 'card_name': '【测试】越权评论', 'fields': {'status': 'open'}}, token=tok_d)
    ok(code == 200, 'admin 在任意看板建卡被允许（实际 %s）' % code)
    created = r.get('card_id')
    if created:
        http('/api/cards/' + created, 'DELETE', token=tok_d)

    # ---------- 5) 前端口径一致 ----------
    print('\n【用例5】/api/me、/api/boards、/api/cards 口径一致')
    for label, tok in (('资金部成员', tok_a), ('核算部成员', tok_b), ('admin', tok_admin)):
        code, me = http('/api/me', token=tok)
        me_set = {b['board_id'] for b in me.get('boards', [])}
        code2, bl = http('/api/boards', token=tok)
        bl_set = {b['board_id'] for b in bl.get('boards', [])}
        code3, cards = http('/api/cards?size=500', token=tok)
        card_set = {c['board_id'] for c in cards.get('cards', [])}
        ok(me_set == bl_set, '%s：/api/me 与 /api/boards 看板集合一致' % label)
        ok(card_set <= me_set, '%s：卡片所属看板 ⊆ 可见看板' % label)
        ok(code3 == 200 and card_set <= me_set, '%s：/api/cards 未泄露不可见看板' % label)

    # ---------- 6) 板块（column）级权限 ----------
    print('\n【用例6】板块级权限：不可见的板块读不到、写不进')
    c = db()
    c.execute("UPDATE users SET allowed_columns=? WHERE username=?",
              (json.dumps({TEST_BOARD: ['COL_X']}), USR_A))
    c.commit()
    c.close()
    code, r = http('/api/cards?board_id=' + TEST_BOARD, token=tok_a)
    names = {c.get('card_name') for c in r.get('cards', [])}
    cols = {c.get('column_id') for c in r.get('cards', [])}
    ok(code == 200 and 'COL_X' in cols and 'COL_Y' not in cols,
       '板块白名单生效：只看得到 COL_X（实际 %s）' % sorted(cols))
    code, r = http('/api/cards', 'POST', {
        'board_id': TEST_BOARD, 'column_id': 'COL_Y', 'column_name': '板块COL_Y',
        'card_name': '【测试】写入不可见板块', 'fields': {'status': 'open'}}, token=tok_a)
    ok(code == 403, '往不可见板块写入被拒（实际 %s）' % code)
    code, r = http('/api/cards', 'POST', {
        'board_id': TEST_BOARD, 'column_id': 'COL_X', 'column_name': '板块COL_X',
        'card_name': '【测试】写入可见板块', 'fields': {'status': 'open'}}, token=tok_a)
    ok(code == 200, '往可见板块写入被允许（实际 %s）' % code)
    if r.get('card_id'):
        http('/api/cards/' + r['card_id'], 'DELETE', token=tok_a)
    c = db()
    c.execute("UPDATE users SET allowed_columns='*' WHERE username=?", (USR_A,))
    c.commit()
    c.close()
finally:
    cleanup()

print('\n结果：%d 通过 / %d 失败' % (passed, failed))
sys.exit(1 if failed else 0)
