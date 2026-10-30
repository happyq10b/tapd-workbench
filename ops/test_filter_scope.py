#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""筛选栏端到端测试：人员 × 负责人 交集语义 + 候选接口权限过滤。

覆盖：
  1) /api/filter-options 返回权限可见范围内的候选（越权人员不出现）
  2) person 参数作用在 owner 字段（与 owner 同字段）
  3) owner 与 person 同时提交 → 取**交集**（不是覆盖、不是并集）
  4) person 单独提交 → 只保留负责人命中该人的事项
  5) person 多值 → 任一命中
  6) person 与其它筛选条件（状态/周数）可任意组合
运行：python ops/test_filter_scope.py
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

from app.app import hash_pw, make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PREFIX = '__fs_'
PASSED, FAILED = [], []


def ok(cond, msg):
    if cond:
        PASSED.append(msg); print('  ✓ ' + msg)
    else:
        FAILED.append(msg); print('  ✗ ' + msg)


def http(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except Exception:
            return e.code, {}


def db():
    c = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'app.db'))
    c.row_factory = sqlite3.Row
    return c


NOW = '2026-10-30 12:00:00'
BOARD = PREFIX + 'board'
NODE = 4           # 核算部
OWNER_A = PREFIX + '甲'
OWNER_B = PREFIX + '乙'


def setup():
    c = db()
    c.execute('DELETE FROM cards WHERE card_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM board_config WHERE board_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM boards WHERE board_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM board_columns WHERE col_key LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM users WHERE username LIKE ?', (PREFIX + '%',))
    c.execute('INSERT INTO boards (board_id, board_name, workspace_id, created_at) VALUES (?,?,?,?)',
              (BOARD, '【测试】筛选看板', 'ws_fs', NOW))
    c.execute('INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, created_at) VALUES (?,?,?,?,?,?)',
              (BOARD, '核算部', NODE, '日常', '启用', NOW))
    # 甲 / 乙 / 丙 三个人各一条事项，丙不在筛选候选里（用于验证多值任一命中）
    for owner, cid in ((OWNER_A, PREFIX + 'ca'), (OWNER_B, PREFIX + 'cb'),
                       (PREFIX + '丙', PREFIX + 'cc')):
        c.execute("""INSERT INTO cards (card_id, board_id, board_name, column_id, column_name,
                       workspace_id, card_name, status, status_name, creator, owner, cc,
                       created, modified, week_no, parent_id, version, deleted)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'',?,?,'2026年第41周','',1,0)""",
                  (cid, BOARD, '【测试】筛选看板', 'COL_FS', '【测试】筛选板块', 'ws_fs',
                   '【测试】' + owner, 'open', '未完成', 'seed', owner, NOW, NOW))
    c.execute("INSERT INTO users (username, password_hash, role, allowed_boards, allowed_columns, created_at)"
              " VALUES (?,?,'admin','*','*',?)", (PREFIX + 'admin', hash_pw('FsTest123'), NOW))
    c.commit(); c.close()


def cleanup():
    c = db()
    c.execute('DELETE FROM cards WHERE card_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM board_config WHERE board_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM boards WHERE board_id LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM board_columns WHERE col_key LIKE ?', (PREFIX + '%',))
    c.execute('DELETE FROM users WHERE username LIKE ?', (PREFIX + '%',))
    c.commit(); c.close()


def owners_of(code, r):
    return sorted((x.get('owner') or '') for x in (r.get('cards') or []))


def main():
    print('=== 筛选栏：人员 × 负责人 交集语义 ===')
    setup()
    try:
        tok = make_token(PREFIX + 'admin')

        # ---------------------------------------------------------
        print('\n【用例1】候选接口 /api/filter-options')
        code, r = http('/api/filter-options', token=tok)
        ok(code == 200, '接口返回 200：%s' % code)
        people = r.get('people') or []
        weeks = r.get('weeks') or []
        ok(OWNER_A in people and OWNER_B in people, '候选含可见范围内的负责人：%s' % people[:5])
        ok('2026年第41周' in weeks, '候选含可见范围内的周数：%s' % weeks[:5])

        # ---------------------------------------------------------
        print('\n【用例2】person 单独提交 → 按 owner 字段过滤')
        code, r = http('/api/cards?board_id=%s&person=%s' % (BOARD, urllib.request.quote(OWNER_A)),
                       token=tok)
        got = owners_of(code, r)
        ok(code == 200 and got == [OWNER_A], 'person=甲 → 只返回负责人为甲的事项：%s' % got)

        # ---------------------------------------------------------
        print('\n【用例3】owner 与 person 同时提交 → 取交集')
        code, r = http('/api/cards?board_id=%s&owner=%s&person=%s'
                       % (BOARD, urllib.request.quote(OWNER_A), urllib.request.quote(OWNER_B)),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [], 'owner=甲 且 person=乙 → 交集为空（不是覆盖、不是并集）：%s' % got)

        code, r = http('/api/cards?board_id=%s&owner=%s&person=%s'
                       % (BOARD, urllib.request.quote(OWNER_A), urllib.request.quote(OWNER_A)),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [OWNER_A], 'owner=甲 且 person=甲 → 交集为甲：%s' % got)

        # ---------------------------------------------------------
        print('\n【用例4】person 多值 → 任一命中')
        code, r = http('/api/cards?board_id=%s&person=%s,%s'
                       % (BOARD, urllib.request.quote(OWNER_A), urllib.request.quote(OWNER_B)),
                       token=tok)
        got = owners_of(code, r)
        ok(sorted(got) == sorted([OWNER_A, OWNER_B]), 'person=甲,乙 → 两条都命中：%s' % got)

        # ---------------------------------------------------------
        print('\n【用例5】与其它筛选条件组合')
        code, r = http('/api/cards?board_id=%s&person=%s&status=open' % (BOARD, urllib.request.quote(OWNER_A)),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [OWNER_A], 'person + status 组合：%s' % got)
        code, r = http('/api/cards?board_id=%s&person=%s&status=done' % (BOARD, urllib.request.quote(OWNER_A)),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [], 'person + 冲突的 status → 空：%s' % got)
        code, r = http('/api/cards?board_id=%s&person=%s&week=%s'
                       % (BOARD, urllib.request.quote(OWNER_A), urllib.request.quote('2026年第41周')),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [OWNER_A], 'person + week 组合：%s' % got)
        code, r = http('/api/cards?board_id=%s&person=%s&week=%s'
                       % (BOARD, urllib.request.quote(OWNER_A), urllib.request.quote('2026年第42周')),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [], 'person + 冲突的 week → 空：%s' % got)

        # ---------------------------------------------------------
        print('\n【用例6】owner 单独提交仍然生效（未被 person 改写）')
        code, r = http('/api/cards?board_id=%s&owner=%s' % (BOARD, urllib.request.quote(OWNER_B)),
                       token=tok)
        got = owners_of(code, r)
        ok(got == [OWNER_B], 'owner=乙 单独生效：%s' % got)

        # ---------------------------------------------------------
        print('\n【用例7】候选接口遵守权限过滤（普通用户看不到越权人员）')
        c = db()
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards, allowed_columns, created_at)
                     VALUES (?,?,'viewer','__none__','*',?)""",
                  (PREFIX + 'viewer', hash_pw('FsTest123'), NOW))
        c.commit(); c.close()
        tok2 = make_token(PREFIX + 'viewer')
        code, r = http('/api/filter-options', token=tok2)
        people2 = r.get('people') or []
        ok(OWNER_A not in people2, '越权用户看不到他人的负责人候选：%s' % people2[:5])
        code, r = http('/api/cards?person=%s' % urllib.request.quote(OWNER_A), token=tok2)
        got = owners_of(code, r)
        ok(got == [], '越权用户用 person 查询 → 无结果：%s' % got)

        print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASSED), len(FAILED)))
        for f in FAILED:
            print('  FAIL: ' + f)
        return 1 if FAILED else 0
    finally:
        cleanup()


if __name__ == '__main__':
    sys.exit(main())
