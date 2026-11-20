# -*- coding: utf-8 -*-
"""归属年份下沉到【板块】层 + 周数与年份不做联动校验 的端到端回归测试。

覆盖：
  1. 板块层：每个板块绑定**唯一**归属年份（单值必填；未填回落创建年份；非法值 400）
  2. 看板层：不再有归属年份（board_config 无 year 列；接口不返回 year，
     col_years 字段已于 #207-bis 随「板块年份」展示位一并下线）
  3. **关键约束**：周数与年份**不做**强制校验或联动限制 ——
     归属 2026 年的板块下，允许存在归属 2025 年第 40 周的事项，不报错、不拦截
  4. 展示：板块列表带 year；看板列表不带 year/col_years（#207-bis）

用法：先起服务（默认 127.0.0.1:8100），再
    python ops/test_year_layer.py
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

PREFIX = '__yl_'
BOARD = PREFIX + 'board'
COL = PREFIX + 'col'   # 板 col_key 形如 board_id::板块名（与线上一致）
COL_KEY = BOARD + '::【测试】2026 板块'
USR = PREFIX + 'user'

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
    c.execute("DELETE FROM cards WHERE card_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM cards WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?||'%'", (PREFIX,))
    c.execute("DELETE FROM users WHERE username LIKE ?||'%'", (PREFIX,))
    c.commit()
    c.close()


def setup():
    cleanup()
    c = db()
    now = "2026-10-30 12:00:00"
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)",
              (BOARD, '【测试】年份层级看板', 'ws_yl', now))
    c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, created_at)
                 VALUES (?,?,?,?,?,?)""", (BOARD, '资金部', 5, '日常', '启用', now))
    col_key = COL_KEY
    c.execute("""INSERT INTO board_columns (col_key, column_id, board_id, column_name,
                   created_at, creator, nature, year, pinned) VALUES (?,?,?,?,?,?,'日常','2026',0)""",
              (col_key, 'COL_YL', BOARD, '【测试】2026 板块', now, PREFIX + 'seed'))
    c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                   allowed_columns, created_at) VALUES (?,?,'admin','*','*',?)""",
              (USR, hash_pw('Test12345'), now))
    c.commit()
    c.close()


def col_row(col_key):
    c = db()
    row = c.execute("SELECT * FROM board_columns WHERE col_key=?", (col_key,)).fetchone()
    c.close()
    return dict(row) if row else None


def card_row(card_id):
    c = db()
    row = c.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
    c.close()
    return dict(row) if row else None


print('=== 归属年份下沉到板块层 + 周数/年份不联动 ===')
setup()
try:
    tok = make_token(USR)
    tok_admin = make_token('admin')

    # ---------- 1) 板块层：唯一归属年份 ----------
    print('\n【用例1】板块绑定唯一归属年份')
    code, r = http('/api/boards/%s/columns' % BOARD, token=tok)
    cols = r.get('columns') or []
    ok(code == 200 and cols and cols[0].get('year') == '2026',
       '板块列表返回归属年份：%s' % ([c.get('year') for c in cols],))
    # 新建板块：不传年份 → 默认取创建年份
    code, r = http('/api/columns', 'POST', {
        'board_id': BOARD, 'column_name': '【测试】默认年份板块',
        'created_at': '2026-07-08', 'nature': '日常'}, token=tok)
    ok(code == 200 and r.get('year') == '2026', '未填年份 → 默认取创建年份（实际 %s）' % r.get('year'))
    default_key = r.get('col_key') or ''
    # 新建板块：显式年份
    code, r = http('/api/columns', 'POST', {
        'board_id': BOARD, 'column_name': '【测试】2025 板块',
        'created_at': '2026-07-08', 'nature': '日常', 'year': '2025'}, token=tok)
    ok(code == 200 and r.get('year') == '2025', '显式指定年份 → 存 2025（实际 %s）' % r.get('year'))
    y2025_key = r.get('col_key') or ''
    # 非法年份
    code, r = http('/api/columns', 'POST', {
        'board_id': BOARD, 'column_name': '【测试】非法年份板块',
        'created_at': '2026-07-08', 'nature': '日常', 'year': '25年'}, token=tok)
    ok(code == 400, '非法年份格式 → 400（实际 %s）' % code)
    # 编辑板块：清空年份 → 回落创建年份
    code, r = http('/api/columns', 'PUT', {
        'col_key': y2025_key, 'board_id': BOARD, 'column_name': '【测试】2025 板块',
        'created_at': '2026-07-08', 'nature': '日常', 'year': ''}, token=tok)
    ok(code == 200 and (col_row(y2025_key) or {}).get('year') == '2026',
       '编辑时清空年份 → 回落创建年份（实际 %s）' % (col_row(y2025_key) or {}).get('year'))

    # ---------- 2) 看板层：不再有年份 ----------
    print('\n【用例2】看板层不再设置归属年份')
    c = db()
    cols_bc = [r[1] for r in c.execute('PRAGMA table_info(board_config)').fetchall()]
    c.close()
    ok('year' not in cols_bc, 'board_config 表已无 year 列：%s' % cols_bc)
    code, r = http('/api/boards', token=tok_admin)
    boards = r.get('boards') or []
    mine = [b for b in boards if b['board_id'] == BOARD]
    ok(mine and 'year' not in mine[0], '看板列表不再返回 year 字段')
    # #207-bis（2026-11-20）：col_years 字段随「板块年份」展示位下线，断言其不再下发
    ok(mine and 'col_years' not in mine[0], 'col_years 字段已下线（板块年份展示位移除）')
    code, r = http('/api/board-config', token=tok_admin)
    items = r.get('items') or []
    mine_cfg = [i for i in items if i['board_id'] == BOARD]
    ok(mine_cfg and 'year' not in mine_cfg[0], '看板配置列表不再返回 year')

    # ---------- 3) 关键约束：周数与年份不做联动校验 ----------
    print('\n【用例3】周数与年份不做强制校验 / 联动限制')
    # 板块年份 2026，事项周数 2025年第40周 → 允许
    code, r = http('/api/cards', 'POST', {
        'board_id': BOARD, 'column_id': 'COL_YL', 'column_name': '【测试】2026 板块',
        'card_name': '【测试】跨年事项', 'week_no': '2025年第40周',
        'fields': {'status': 'open', 'status_name': '未完成'}}, token=tok)
    ok(code == 200, '2026 年板块下可创建 2025 年第 40 周的事项（实际 %s）' % code)
    cross = card_row(r.get('card_id') or '')
    ok(cross is not None and cross['week_no'] == '2025年第40周', '事项周数按填写值保存：%s'
       % (cross or {}).get('week_no'))
    ok(cross is not None and cross['column_name'] == '【测试】2026 板块', '事项仍在 2026 年板块下')
    # 编辑事项改成别的年份的周数 → 允许
    code, r = http('/api/cards/' + (r.get('card_id') or ''), 'PUT',
                   {'fields': {'week_no': '2024年第12周'}}, token=tok)
    ok(code == 200, '可把事项周数改成任意年份（实际 %s）' % code)
    ok((card_row(cross['card_id']) or {}).get('week_no') == '2024年第12周', '周数改动已保存')
    # 复制事项到 2026 年板块但指定 2025 年周数 → 允许
    code, r = http('/api/cards/copy', 'POST', {
        'card_id': cross['card_id'], 'board_id': BOARD, 'column_id': 'COL_YL',
        'column_name': '【测试】2026 板块', 'week_no': '2025年第40周'}, token=tok)
    ok(code == 200, '复制到 2026 年板块并指定 2025 年周数 → 放行（实际 %s）' % code)
    cp = card_row(r.get('card_id') or '')
    ok(cp is not None and cp['week_no'] == '2025年第40周', '副本周数按填写值保存：%s'
       % (cp or {}).get('week_no'))
    # 板块年份改成 2025，事项周数仍是 2024 年 → 仍不拦截
    code, r = http('/api/columns', 'PUT', {
        'col_key': COL_KEY, 'board_id': BOARD, 'column_name': '【测试】2026 板块',
        'created_at': '2026-07-08', 'nature': '日常', 'year': '2025'}, token=tok)
    ok(code == 200, '板块年份可改为 2025（实际 %s）' % code)
    ok((card_row(cross['card_id']) or {}).get('week_no') == '2024年第12周',
       '改板块年份后，事项周数不受影响（不做联动）')
    code, r = http('/api/cards/' + cross['card_id'], 'PUT',
                   {'fields': {'week_no': '2024年第12周'}}, token=tok)
    ok(code == 200, '板块年份 2025 下保存 2024 年周数 → 不拦截（实际 %s）' % code)
finally:
    cleanup()

print('\n结果：%d 通过 / %d 失败' % (passed, failed))
sys.exit(1 if failed else 0)
