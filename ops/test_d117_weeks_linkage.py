#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""专项测试：工具栏周数筛选候选**与其他筛选项联动**（2026-11-09 需求3）

口径变更：_filter_cards_for_user 里 week_options 的统计点移到
  全部其他筛选项（看板/年份/状态/负责人/参与人/创建日期/搜索）**之后**、
  周数筛选**之前** —— 只有「当前筛选结果下存在事项」的周数才进入候选。

断言全部基于专属夹具看板（__wk_b1），不依赖全局基线数字（§3.3 纪律）。
夹具：专属前缀 __wk_ + try/finally 全量清理（boards/board_columns/cards 三表）。
"""
import os
import sqlite3
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

DB = os.path.join(ROOT, 'src', 'app.db')
BASE = 'http://127.0.0.1:8100'
PREFIX = '__wk_'
BID = PREFIX + 'b1'
PASS = 0
FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS', msg)
    else:
        FAIL += 1
        print('  FAIL', msg)


def cleanup():
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM cards WHERE board_id=? OR card_name LIKE ?', (BID, PREFIX + '%'))
    c.execute('DELETE FROM board_columns WHERE board_id=?', (BID,))
    c.execute('DELETE FROM boards WHERE board_id=?', (BID,))
    c.commit()
    c.close()


def make_fixtures():
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO boards(board_id,board_name,workspace_id,owner,sort,created_at) "
              "VALUES(?,?,?,?,0,datetime('now'))", (BID, PREFIX + '联动测试看板', '', 'admin'))
    c.execute("INSERT INTO board_columns(col_key,board_id,column_name,nature,year) VALUES(?,?,?,?,?)",
              (BID + '::' + PREFIX + '板块甲', BID, PREFIX + '板块甲', '日常', '2026'))
    c.execute("INSERT INTO board_columns(col_key,board_id,column_name,nature,year) VALUES(?,?,?,?,?)",
              (BID + '::' + PREFIX + '板块乙', BID, PREFIX + '板块乙', '日常', '2026'))
    rows = [
        # (card_id, column, card_name, status, owner, week_no)
        (PREFIX + 'c1', PREFIX + '板块甲', PREFIX + '甲事项', 'done', PREFIX + '张三', '2026年第3周'),
        (PREFIX + 'c2', PREFIX + '板块乙', PREFIX + '乙事项', 'open', PREFIX + '李四', '2026年第8周'),
        (PREFIX + 'c3', PREFIX + '板块乙', PREFIX + '丙事项', 'open', PREFIX + '李四', '2026年第11周'),
    ]
    for cid, col, name, st, ow, wk in rows:
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_name,card_name,status,owner,"
                  "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,datetime('now'),0)",
                  (cid, BID, PREFIX + '联动测试看板', col, name, st, ow, wk))
    c.commit()
    c.close()


def make_token():
    from app.app import make_token as mt
    return mt('admin')


def api(path, token):
    from urllib.parse import quote
    # 查询参数里的中文（夹具名/搜索词）做百分号编码，safe 保留 URL 结构符
    safe = path.split('?')[0]
    query = quote(path.split('?', 1)[1], safe='=&,') if '?' in path else ''
    path = safe + ('?' + query if query else '')
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=10) as r:
        import json
        return json.loads(r.read().decode('utf-8'))


def main():
    cleanup()
    try:
        make_fixtures()
        tk = make_token()

        print('== 1) 无其他筛选：候选 = 夹具看板全部周数 ==')
        d = api('/api/cards?board_ids=' + BID, tk)
        ok(sorted(d['weeks']) == ['2026年第11周', '2026年第3周', '2026年第8周'],
           'weeks=%s' % d['weeks'])

        print('== 2) 人员筛选联动：张三 → 只剩甲事项的周 ==')
        d = api('/api/cards?board_ids=' + BID + '&person=' + PREFIX + '张三', tk)
        ok(d['weeks'] == ['2026年第3周'] and d['total'] == 1, 'weeks=%s total=%d' % (d['weeks'], d['total']))

        print('== 3) 人员筛选联动：李四 → 乙/丙两周 ==')
        d = api('/api/cards?board_ids=' + BID + '&person=' + PREFIX + '李四', tk)
        ok(sorted(d['weeks']) == ['2026年第11周', '2026年第8周'], 'weeks=%s' % d['weeks'])

        print('== 4) 搜索词联动：搜「乙事项」→ 只剩乙的周 ==')
        d = api('/api/cards?board_ids=' + BID + '&q=' + PREFIX + '乙事项', tk)
        ok(d['weeks'] == ['2026年第8周'], 'weeks=%s' % d['weeks'])

        print('== 5) 搜索词命中板块名：板块甲 → 该板块下全部卡片参与统计 ==')
        d = api('/api/cards?board_ids=' + BID + '&q=' + PREFIX + '板块甲', tk)
        ok(d['weeks'] == ['2026年第3周'], 'weeks=%s' % d['weeks'])

        print('== 6) 状态联动：done → 只剩甲(2026年第3周) ==')
        d = api('/api/cards?board_ids=' + BID + '&status=done', tk)
        ok(d['weeks'] == ['2026年第3周'], 'weeks=%s' % d['weeks'])

        print('== 7) 周数筛选本身不收缩候选：week=第8周 → 仍返回全部三周，但 cards 只剩乙 ==')
        d = api('/api/cards?board_ids=' + BID + '&week=2026年第8周', tk)
        ok(len(d['weeks']) == 3 and d['total'] == 1 and d['cards'][0]['card_id'] == PREFIX + 'c2',
           'weeks=%d total=%d' % (len(d['weeks']), d['total']))

        print('== 8) 搜索+周组合：搜乙事项 & week=第3周 → 空结果，候选仍=搜索结果的周 ==')
        d = api('/api/cards?board_ids=' + BID + '&q=' + PREFIX + '乙事项&week=2026年第3周', tk)
        ok(d['total'] == 0 and d['weeks'] == ['2026年第8周'], 'total=%d weeks=%s' % (d['total'], d['weeks']))

        print('== 9) 当前周标签口径自检：后端 week_label(今天) 可作为「当前周」高亮基准 ==')
        from app.app import week_label
        import datetime
        wl = week_label(datetime.date.today().isoformat())
        ok(wl.startswith('2026年第') or wl.startswith('2027年第'), 'week_label(今天)=%s' % wl)
        # 与前端 cpWeekOf 同口径：ISO 周（周四定归属年）
        iso = datetime.date.today().isocalendar()
        ok(wl == '%d年第%d周' % (iso[0], iso[1]), '与 isocalendar 一致：%s' % wl)

        print('\n结果：PASS=%d FAIL=%d' % (PASS, FAIL))
        sys.exit(1 if FAIL else 0)
    finally:
        cleanup()
        # 残留自查（§3.3）
        c = sqlite3.connect(DB)
        n = c.execute('SELECT COUNT(*) FROM cards WHERE card_name LIKE ?', (PREFIX + '%',)).fetchone()[0]
        nb = c.execute('SELECT COUNT(*) FROM boards WHERE board_id LIKE ?', (PREFIX + '%',)).fetchone()[0]
        c.close()
        print('残留自查：cards=%d boards=%d（应为 0 0）' % (n, nb))
        if n or nb:
            print('⚠️ 夹具未清干净！')


if __name__ == '__main__':
    main()
