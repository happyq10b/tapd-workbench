#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据清理：删除空板块（无任何事项）与空看板（无任何板块 / 板块全被清理为空）

规则（用户 2026-11-02 要求）：
  ① 每个板块至少保留一个事项 —— 没有任何事项的板块**直接删除**；
  ② 看板本身若无任何板块，或其所有板块均被清理为空 → **一并删除该看板**。

删除顺序（有关联，顺序不能颠倒）：
  1. 删空板块（board_columns 里没有未删事项的行）；
  2. 删空看板（boards 里既无剩余板块、也无未删事项的行），
     并连带清理它的 board_config / board_columns / 事项 / 子事项。

⚠️ 判定口径：事项按 **column_id** 匹配板块（column_id 是板块的权威标识）；
   column_id 为空的历史脏数据（无板块归属）**不计入**任何板块 ——
   它们本身就不是"某板块的事项"，不应导致空板块被误判为非空。

用法：
    ops/.localvenv/Scripts/python.exe ops/cleanup_empty.py --dry-run   # 只报告不删
    ops/.localvenv/Scripts/python.exe ops/cleanup_empty.py             # 实际删除
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'src', 'app.db')


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def find_empty_columns(conn):
    """找出没有任何未删事项的板块"""
    return [dict(r) for r in conn.execute("""
        SELECT bc.col_key, bc.board_id, bc.column_id, bc.column_name
        FROM board_columns bc
        WHERE NOT EXISTS (
            SELECT 1 FROM cards cd
            WHERE cd.deleted = 0
              AND cd.column_id = bc.column_id
              AND bc.column_id <> ''
        )
        ORDER BY bc.board_id, bc.column_name
    """)]


def find_empty_boards(conn, dead_col_keys):
    """找出应当删除的看板：
       · 该看板下**所有板块**都在待删列表里（板块全被清理为空），或
       · 该看板**既无剩余板块、也无未删事项**（本来就是空看板）。
    ⚠️ 必须先算「板块全被清理为空」，再算「本来就没板块」——
       否则会把"板块被删光但还有事项"的看板误删（那些事项将无处安放）。
    """
    dead_by_board = {}
    for c in dead_col_keys:
        dead_by_board.setdefault(c['board_id'], set()).add(c['column_id'])

    out = []
    for r in conn.execute('SELECT board_id, board_name FROM boards'):
        bid = r['board_id']
        total = conn.execute(
            'SELECT COUNT(*) FROM board_columns WHERE board_id=?', (bid,)).fetchone()[0]
        dead = dead_by_board.get(bid, set())
        alive = total - len(dead)
        if total > 0 and alive == 0:
            out.append({'board_id': bid, 'board_name': r['board_name'],
                        'reason': '所有板块均被清理为空', 'total_cols': total})
            continue
        if total == 0:
            cards = conn.execute(
                'SELECT COUNT(*) FROM cards WHERE deleted=0 AND board_id=?', (bid,)).fetchone()[0]
            if cards == 0:
                out.append({'board_id': bid, 'board_name': r['board_name'],
                            'reason': '无任何板块且无任何事项', 'total_cols': 0})
    return out


def do_cleanup(conn, dry_run=False):
    empty_cols = find_empty_columns(conn)
    empty_boards = find_empty_boards(conn, empty_cols)

    print('=== 空板块（无任何未删事项）===')
    if not empty_cols:
        print('  （无）')
    for c in empty_cols:
        print('  %-14s %-16s | %s' % (c['col_key'][:14], c['board_id'][-6:], c['column_name']))
    print('  合计：%d 个' % len(empty_cols))

    print()
    print('=== 空看板（板块全空 / 无板块且无事项）===')
    if not empty_boards:
        print('  （无）')
    for b in empty_boards:
        print('  %-14s %-20s | %s' % (b['board_id'][-6:], b['board_name'], b['reason']))
    print('  合计：%d 个' % len(empty_boards))

    if dry_run:
        print()
        print('[dry-run] 未执行任何删除')
        return 0

    if not empty_cols and not empty_boards:
        print()
        print('无需清理')
        return 0

    conn.execute('BEGIN')
    try:
        # ① 删空板块
        for c in empty_cols:
            conn.execute('DELETE FROM board_columns WHERE col_key=?', (c['col_key'],))
        # ② 删空看板（连带其配置 / 板块 / 事项 / 子事项）
        for b in empty_boards:
            bid = b['board_id']
            # 子事项随主事项删除（先删子事项，避免留下孤儿）
            conn.execute("""DELETE FROM card_subtasks WHERE card_id IN
                            (SELECT card_id FROM cards WHERE board_id=?)""", (bid,))
            conn.execute('DELETE FROM cards WHERE board_id=?', (bid,))
            conn.execute('DELETE FROM board_columns WHERE board_id=?', (bid,))
            conn.execute('DELETE FROM board_config WHERE board_id=?', (bid,))
            conn.execute('DELETE FROM boards WHERE board_id=?', (bid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print()
    print('已删除：%d 个空板块，%d 个空看板' % (len(empty_cols), len(empty_boards)))
    return 0


def main():
    ap = argparse.ArgumentParser(description='清理空板块与空看板')
    ap.add_argument('--dry-run', action='store_true', help='只报告不删除')
    args = ap.parse_args()
    if not os.path.exists(DB):
        print('找不到数据库：%s' % DB)
        return 1
    conn = connect()
    try:
        return do_cleanup(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
