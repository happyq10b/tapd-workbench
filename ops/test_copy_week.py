# -*- coding: utf-8 -*-
"""复制（看板 / 板块 / 主事项 / 子事项）+ 周数字段 的端到端回归测试。

覆盖：
  1. 复制生成的记录**独立**（改副本不影响原记录），标题带「（副本）」且可编辑
  2. 复制后**归属重选**：目标看板 / 目标板块 / 所属主事项（子事项必填）
  3. **权限过滤**：越权的源记录、目标看板、目标板块、目标主事项一律 403，
     且不会出现在可选列表里（不可见即不可选）
  4. admin 复制看板；普通用户复制看板被拒
  5. 周数：默认按创建日期所在自然周；格式校验；多值筛选（任一命中）

用法：先起服务（默认 127.0.0.1:8100），再
    python ops/test_copy_week.py
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
from app.app import make_token, hash_pw   # noqa: E402

PREFIX = '__cw_'
BOARD_A = PREFIX + 'board_a'        # 归属「资金部」（用户 A 可见）
BOARD_B = PREFIX + 'board_b'        # 归属「管理部」（用户 B 可见）
COL_A = PREFIX + 'col_a'
COL_B = PREFIX + 'col_b'
CARD_A = PREFIX + 'card_a'          # 主事项（看板 A）
SUB_A = PREFIX + 'sub_a'            # 子事项（挂在 CARD_A 下）
CARD_B = PREFIX + 'card_b'          # 主事项（看板 B）
USR_A = PREFIX + 'user_a'           # 任命到资金部 → 只见看板 A
USR_B = PREFIX + 'user_b'           # 任命到管理部 → 只见看板 B

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


def cleanup():
    c = db()
    c.execute("DELETE FROM comments WHERE card_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM actions WHERE card_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM cards WHERE card_id LIKE ?||'%'", (PREFIX,))
    # 经接口新建的卡片 id 不含前缀（NC…），只能按 board_id 清 ——
    # 残留的卡片会让「按 cards 派生的看板」继续可见，污染别的用例
    c.execute("DELETE FROM cards WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?||'%'", (PREFIX,))
    # 副本的 id 是新生成的（不含前缀），只能靠 copy_from 清理 —— 否则会残留到别的测试里
    c.execute("DELETE FROM cards WHERE copy_from LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM board_columns WHERE copy_from LIKE ?||'%'", (PREFIX,))
    c.execute("""DELETE FROM board_config WHERE board_id IN
                 (SELECT board_id FROM boards WHERE copy_from LIKE ?||'%')""", (PREFIX,))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM boards WHERE copy_from LIKE ?||'%'", (PREFIX,))
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
    for bid, bname, dept, node in ((BOARD_A, '【测试】资金部看板', '资金部', 5),
                                    (BOARD_B, '【测试】管理部看板', '管理部', 2)):
        c.execute("INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)",
                  (bid, bname, 'ws_cw', now))
        c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, created_at)
                     VALUES (?,?,?,?,?,?)""", (bid, dept, node, '日常', '启用', now))
    for key, bid, cname in ((COL_A, BOARD_A, '【测试】板块A'), (COL_B, BOARD_B, '【测试】板块B')):
        c.execute("""INSERT INTO board_columns (col_key, column_id, board_id, column_name,
                       created_at, creator, nature, year, pinned) VALUES (?,?,?,?,?,?,'日常','2026',0)""",
                  (key, 'COL_' + key[-1], bid, cname, now, PREFIX + 'seed'))
    # 主事项 A（周数按创建日期 = 2026-10-30 → 第 44 周）+ 子事项 A
    c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name, workspace_id,
                   card_name, status, status_name, creator, owner, begin, due, created, parent_id,
                   version, deleted, week_no) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'',1,0,?)""",
              (CARD_A, BOARD_A, '【测试】资金部看板', 'COL_A', '【测试】板块A', 'ws_cw',
               '【测试】主事项A', 'open', '未完成', PREFIX + 'seed', '刘自琴', '2026-10-01', '2026-10-31',
               now, '2026年第44周'))
    c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name, workspace_id,
                   card_name, status, status_name, creator, owner, begin, due, created, parent_id,
                   version, deleted, week_no) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,?)""",
              (SUB_A, BOARD_A, '【测试】资金部看板', '', '', 'ws_cw',
               '【测试】子事项A', 'open', '未完成', PREFIX + 'seed', '刘自琴', '2026-10-01', '2026-10-31',
               now, CARD_A, '2026年第44周'))
    c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name, workspace_id,
                   card_name, status, status_name, creator, owner, begin, due, created, parent_id,
                   version, deleted, week_no) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'',1,0,?)""",
              (CARD_B, BOARD_B, '【测试】管理部看板', 'COL_B', '【测试】板块B', 'ws_cw',
               '【测试】主事项B', 'open', '未完成', PREFIX + 'seed', '王伟娜', '2026-10-01', '2026-10-31',
               now, '2026年第44周'))
    # 成员 + 任命：A → 资金部；B → 管理部
    mids = {}
    for key, name, acct in (('a', PREFIX + '成员A', USR_A), ('b', PREFIX + '成员B', USR_B)):
        cur = c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                         (name, acct, now))
        mids[key] = cur.lastrowid
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (5,?,'member',0,?)""", (mids['a'], now))
    c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                 VALUES (2,?,'member',0,?)""", (mids['b'], now))
    for acct in (USR_A, USR_B):
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,'editor','*','*',?)""",
                  (acct, hash_pw('Test12345'), now))
    c.commit()
    c.close()


def card_row(card_id):
    c = db()
    row = c.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
    c.close()
    return dict(row) if row else None


print('=== 复制 + 周数 ===')
setup()
try:
    tok_a = make_token(USR_A)
    tok_b = make_token(USR_B)
    tok_admin = make_token('admin')

    # ---------- 1) 复制主事项 ----------
    print('\n【用例1】复制主事项：独立副本 + 归属重选')
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': CARD_A, 'board_id': BOARD_A, 'column_id': 'COL_A',
        'column_name': '【测试】板块A', 'card_name': '【测试】副本标题'}, token=tok_a)
    ok(code == 200, '复制主事项成功（实际 %s）' % code)
    new_id = r.get('card_id') or ''
    ok(bool(new_id) and new_id != CARD_A, '副本是新记录（card_id=%s）' % new_id)
    row = card_row(new_id)
    ok(row is not None and row['card_name'] == '【测试】副本标题', '标题可编辑并已保存')
    ok(row is not None and row['copy_from'] == CARD_A, '副本记录了复制来源（copy_from）')
    ok(row is not None and row['creator'] == USR_A, '副本创建人 = 当前账号')
    ok(row is not None and row['status'] == 'open', '副本状态重置为未完成')
    ok(row is not None and row['parent_id'] == '', '主事项副本仍是主事项')
    ok(row is not None and row['week_no'] == '2026年第44周', '副本周数默认按创建日期：%s'
       % (row or {}).get('week_no'))
    # 改副本不影响原记录
    http('/api/cards/' + new_id, 'PUT', {'fields': {'card_name': '改过的副本'}}, token=tok_a)
    src = card_row(CARD_A)
    ok(src and src['card_name'] == '【测试】主事项A', '修改副本不影响原记录（数据不共享）')

    # ---------- 2) 复制子事项 ----------
    print('\n【用例2】复制子事项：必须重新选择所属主事项')
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': SUB_A, 'board_id': BOARD_A, 'column_id': 'COL_A',
        'column_name': '【测试】板块A'}, token=tok_a)
    ok(code == 400, '未选所属主事项 → 400（实际 %s）' % code)
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': SUB_A, 'board_id': BOARD_A, 'column_id': 'COL_A',
        'column_name': '【测试】板块A', 'parent_id': CARD_A}, token=tok_a)
    ok(code == 200, '选择所属主事项后复制成功（实际 %s）' % code)
    sub_copy = card_row(r.get('card_id') or '')
    ok(sub_copy is not None and sub_copy['parent_id'] == CARD_A, '子事项副本挂在所选主事项下')
    ok(sub_copy is not None and (sub_copy['card_name'] or '').endswith('（副本）'),
       '子事项副本标题带「（副本）」：%s' % (sub_copy or {}).get('card_name'))

    # ---------- 3) 复制板块 ----------
    print('\n【用例3】复制板块：归属重选到目标看板')
    code, r = http('/api/columns/copy', 'POST', {
        'col_key': COL_A, 'board_id': BOARD_A}, token=tok_a)
    ok(code == 200, '复制板块成功（实际 %s）' % code)
    col_key = r.get('col_key') or ''
    ok(col_key.startswith(BOARD_A + '::'), '副本板块在目标看板下：%s' % col_key)
    c = db()
    row = c.execute("SELECT copy_from FROM board_columns WHERE col_key=?", (col_key,)).fetchone()
    c.close()
    ok(row is not None and row['copy_from'] == COL_A, '板块副本记录了来源')

    # ---------- 4) 复制看板 ----------
    print('\n【用例4】复制看板（管理员级）')
    code, r = http('/api/boards/%s/copy' % BOARD_A, 'POST',
                   {'board_name': '【测试】看板副本'}, token=tok_a)
    ok(code == 403, '普通用户复制看板被拒（实际 %s）' % code)
    code, r = http('/api/boards/%s/copy' % BOARD_A, 'POST',
                   {'board_name': '【测试】看板副本', 'year': '2026', 'attr': '日常',
                    'status': '启用', 'dept': '资金部', 'dept_node_id': 5}, token=tok_admin)
    ok(code == 200, '管理员复制看板成功（实际 %s）' % code)
    new_bid = r.get('board_id') or ''
    c = db()
    row = c.execute("SELECT copy_from FROM boards WHERE board_id=?", (new_bid,)).fetchone()
    cfg = c.execute("SELECT dept, dept_node_id FROM board_config WHERE board_id=?", (new_bid,)).fetchone()
    c.close()
    ok(row is not None and row['copy_from'] == BOARD_A, '看板副本记录了来源')
    ok(cfg is not None and cfg['dept'] == '资金部' and cfg['dept_node_id'] == 5,
       '看板副本的归属配置随附且可改')

    # ---------- 5) 权限过滤：越权不可见、不可选、不可复制 ----------
    print('\n【用例5】权限过滤：越权数据不可见也不可选')
    code, r = http('/api/me', token=tok_a)
    vis_a = {b['board_id'] for b in r.get('boards', [])}
    code, r = http('/api/me', token=tok_b)
    vis_b = {b['board_id'] for b in r.get('boards', [])}
    ok(BOARD_A in vis_a and BOARD_B not in vis_a, '用户 A 只看到资金部看板')
    ok(BOARD_B in vis_b and BOARD_A not in vis_b, '用户 B 只看到管理部看板')
    code, r = http('/api/boards/%s/columns' % BOARD_B, token=tok_a)
    ok(code == 403, '用户 A 取管理部看板的板块被拒（实际 %s）' % code)
    code, r = http('/api/boards/%s/columns' % BOARD_A, token=tok_a)
    ok(code == 200 and any(c['column_id'] == 'COL_A' for c in r.get('columns', [])),
       '用户 A 能拿到本部门可见板块（作为目标板块选项）')
    # 复制越权源
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': CARD_B, 'board_id': BOARD_B, 'column_id': 'COL_B',
        'column_name': '【测试】板块B'}, token=tok_a)
    ok(code == 403, '复制不可见看板的事项 → 403（实际 %s）' % code)
    # 复制到越权目标看板
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': CARD_A, 'board_id': BOARD_B, 'column_id': 'COL_B',
        'column_name': '【测试】板块B'}, token=tok_a)
    ok(code == 403, '复制到不可见看板 → 403（实际 %s）' % code)
    # 复制板块到越权看板
    code, r = http('/api/columns/copy', 'POST', {'col_key': COL_A, 'board_id': BOARD_B}, token=tok_a)
    ok(code == 403, '复制板块到不可见看板 → 403（实际 %s）' % code)
    # 子事项副本的父事项不可见
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': SUB_A, 'board_id': BOARD_A, 'column_id': 'COL_A',
        'column_name': '【测试】板块A', 'parent_id': CARD_B}, token=tok_a)
    ok(code == 403, '把子事项副本挂到不可见主事项下 → 403（实际 %s）' % code)
    # 目标板块越权（账号板块白名单）
    c = db()
    c.execute("UPDATE users SET allowed_columns=? WHERE username=?",
              (json.dumps({BOARD_A: ['COL_A']}), USR_A))
    c.commit()
    c.close()
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': CARD_A, 'board_id': BOARD_A, 'column_id': 'COL_OTHER',
        'column_name': '【测试】越权板块'}, token=tok_a)
    ok(code == 403, '复制到越权板块 → 403（实际 %s）' % code)
    c = db()
    c.execute("UPDATE users SET allowed_columns='*' WHERE username=?", (USR_A,))
    c.commit()
    c.close()

    # ---------- 6) 周数 ----------
    print('\n【用例6】周数：默认计算 / 格式校验 / 多值筛选')
    code, r = http('/api/cards?card_id=' + CARD_A, token=tok_a)
    w = (r.get('cards') or [{}])[0].get('week_no')
    ok(w == '2026年第44周', '周数按创建日期所在自然周：%s' % w)
    code, r = http('/api/cards', 'POST', {
        'board_id': BOARD_A, 'card_name': '【测试】周数事项', 'week_no': '2026-41'}, token=tok_a)
    ok(code == 200 and (r.get('card_id') or ''), '建卡可指定周数（2026-41 → 标准标签）')
    made = card_row(r.get('card_id') or '')
    ok(made is not None and made['week_no'] == '2026年第41周', '周数已归一化：%s'
       % (made or {}).get('week_no'))
    code, r = http('/api/cards', 'POST', {
        'board_id': BOARD_A, 'card_name': '【测试】非法周数', 'week_no': '第41周'}, token=tok_a)
    ok(code == 400, '非法周数格式 → 400（实际 %s）' % code)
    code, r = http('/api/cards?week=2026%E5%B9%B4%E7%AC%AC44%E5%91%A8', token=tok_a)
    ok(code == 200 and r.get('total', 0) >= 1, '周数筛选命中：%s 条' % r.get('total'))
    code, r = http('/api/cards?week=2026%E5%B9%B4%E7%AC%AC44%E5%91%A8,2026%E5%B9%B4%E7%AC%AC41%E5%91%A8', token=tok_a)
    ok(code == 200 and r.get('total', 0) >= 2, '周数多选（任一命中）：%s 条' % r.get('total'))
    code, r = http('/api/cards?board_id=%s' % BOARD_A, token=tok_a)
    ok(code == 200 and '2026年第44周' in (r.get('weeks') or []), '接口返回可选周数列表供筛选栏使用')
finally:
    cleanup()

print('\n结果：%d 通过 / %d 失败' % (passed, failed))
sys.exit(1 if failed else 0)
