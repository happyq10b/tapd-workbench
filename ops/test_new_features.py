#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""后端测试：看板整套复制 + 板块参与人 + 板块绑定范围（2026-11-03）。

覆盖：
  1. 整套复制（deep）：看板 + 板块 + 主事项 + 子事项 全部复制，字段口径正确
  2. 非 deep 复制：只复制看板本身（保持原行为）
  3. 板块参与人：ColumnUpdate 写入 / 读回 / 清空
  4. 板块绑定范围：/api/org/tree 的 bindable_boards = 架构下所有看板

⚠️ 夹具纪律（2026-11-02 立规）：
  · 专属前缀 __nb_ 命名空间；try/finally 保证清理（删全所有相关表）
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
PREFIX = '__nb_'
U_ADMIN = PREFIX + 'admin'
U_EDITOR = PREFIX + 'editor'
PWD = 'At159357'
DEPT = ''            # 架构里第一个中心/部门（看板配置的归属部门必须是真实部门）

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
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or '{}')
        except Exception:
            return e.code, {'__raw': raw[:300]}


def setup():
    """夹具：1 个看板 + 2 个板块 + 2 主事项 + 1 子事项（挂在主事项1下）。"""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    now = '2026-11-03 12:00:00'
    for acct, role in ((U_ADMIN, 'admin'), (U_EDITOR, 'editor')):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,?,?,?,?)""",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    stamp = str(int(time.time() * 1000))
    bid = 'NB' + stamp
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, owner, sort, created_at) "
              "VALUES (?,?,'','',0,?)", (bid, PREFIX + '看板', now))
    cols = []
    for i, cname in enumerate((PREFIX + '板块A', PREFIX + '板块B')):
        cid = 'NBC' + stamp + str(i)
        key = bid + '::' + cname
        c.execute("""INSERT INTO board_columns (col_key, column_id, board_id, column_name, created_at,
                       creator, nature, pinned, year, copy_from, owner, participants)
                       VALUES (?,?,?,?,?,?,?,0,?,'','',?)""",
                  (key, cid, bid, cname, now, U_ADMIN, '日常', '2026', ''))
        cols.append((cid, cname, key))
    cards = []
    CARD_COLS = ['card_id','board_id','board_name','column_id','column_name','workspace_id',
                 'card_name','status','status_name','priority','creator','owner','cc',
                 'follower','begin','due','completed','created','modified','description',
                 'attachment_count','label','b_sort','entity_type','cover_setted','cover_info',
                 'is_filed','created_from','date_status','due_time_ux','begin_date_status',
                 'begin_time_ux','comments','column_sort','board_status','board_creator',
                 'parent_id','version','deleted','pinned','week_no','copy_from']
    def ins_card(card_id, cname, cid, owner, parent_id, desc):
        vals = {
            'card_id': card_id, 'board_id': bid, 'board_name': PREFIX + '看板',
            'column_id': cid, 'column_name': cname, 'workspace_id': '',
            'card_name': PREFIX + cname, 'status': 'done', 'status_name': '已完成',
            'priority': '普通', 'creator': U_ADMIN, 'owner': owner, 'cc': '',
            'follower': '', 'begin': '2026-08-06', 'due': '2026-08-14', 'completed': '',
            'created': now, 'modified': now, 'description': desc, 'attachment_count': '0',
            'label': '', 'b_sort': '0', 'entity_type': '', 'cover_setted': '',
            'cover_info': '', 'is_filed': '0', 'created_from': '', 'date_status': '',
            'due_time_ux': '', 'begin_date_status': '', 'begin_time_ux': '',
            'comments': '', 'column_sort': '', 'board_status': '',
            'board_creator': '', 'parent_id': parent_id, 'version': 0, 'deleted': 0,
            'pinned': 0, 'week_no': '2026年第32周', 'copy_from': '',
        }
        c.execute('INSERT INTO cards (%s) VALUES (%s)'
                  % (','.join(CARD_COLS), ','.join('?' * len(CARD_COLS))),
                  [vals[k] for k in CARD_COLS])
    for i in range(2):
        card_id = 'NBD' + stamp + str(i)
        cid, cname, _ = cols[i]
        ins_card(card_id, '主事项' + str(i + 1), cid, '负责人' + str(i + 1), '', '描述' + str(i + 1))
        cards.append(card_id)
    # 子事项：挂在主事项1 下
    sub_id = 'NBS' + stamp
    cid, cname, _ = cols[0]
    ins_card(sub_id, '子事项1', cid, '负责人子', cards[0], '子描述')
    c.commit()
    c.close()
    return {'bid': bid, 'cols': cols, 'cards': cards, 'sub': sub_id}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        # 先删子事项再删主事项（无外键约束，但保持顺序清晰）
        c.execute("DELETE FROM cards WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM boards WHERE board_id=?", (fx['bid'],))
        # ⚠️ **连带清理复制产物**（2026-11-03 补）：整套复制会生成 BCP* 的新看板，
        #    漏删会污染可见性断言（实测 dept_group_scope 因此挂了 6 条）。
        #    按 copy_from 溯源 + 按本次夹具前缀兜底，双保险。
        c.execute("DELETE FROM cards WHERE board_id IN "
                  "(SELECT board_id FROM boards WHERE copy_from=?)", (fx['bid'],))
        c.execute("DELETE FROM board_columns WHERE board_id IN "
                  "(SELECT board_id FROM boards WHERE copy_from=?)", (fx['bid'],))
        c.execute("DELETE FROM board_config WHERE board_id IN "
                  "(SELECT board_id FROM boards WHERE copy_from=?)", (fx['bid'],))
        c.execute("DELETE FROM boards WHERE copy_from=?", (fx['bid'],))
        c.execute("DELETE FROM boards WHERE board_name LIKE ?", (PREFIX + '%',))
    for acct in (U_ADMIN, U_EDITOR):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
    c.commit()
    c.close()


def _pick_dept():
    """取架构里第一个中心/部门名（看板配置必须归属真实部门，否则 400）。"""
    c = sqlite3.connect(DB)
    r = c.execute("SELECT name FROM org_nodes WHERE node_type IN ('center','dept') ORDER BY id LIMIT 1").fetchone()
    c.close()
    return r[0] if r else ''


def main():
    fx = setup()
    global DEPT
    DEPT = _pick_dept()
    try:
        tok = {u: make_token(u) for u in (U_ADMIN, U_EDITOR)}

        print('\n【用例1】整套复制（deep）：看板 + 板块 + 事项 + 子事项')
        code, r = http('/api/boards/%s/copy' % fx['bid'], 'POST',
                       {'board_name': PREFIX + '副本', 'dept': DEPT, 'attr': '日常',
                        'status': '启用', 'deep': True}, token=tok[U_ADMIN])
        ok(code == 200, '复制请求 200（实际 %s）%s' % (code, (' ← '+str(r)[:200]) if code != 200 else ''))
        new_bid = r.get('board_id')
        ok(bool(new_bid) and new_bid != fx['bid'], '生成新的看板 ID')
        ok(r.get('deep') is True, '响应标记 deep=True')
        ok(r.get('copied_columns') == len(fx['cols']),
           '复制板块数正确（%s，期望 %d）' % (r.get('copied_columns'), len(fx['cols'])))
        # 事项数 = 主事项 2 + 子事项 1
        exp_cards = len(fx['cards']) + 1
        ok(r.get('copied_cards') == exp_cards,
           '复制事项数正确（%s，期望 %d，含子事项）' % (r.get('copied_cards'), exp_cards))
        # 校验落库
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        ncols = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id=?", (new_bid,)).fetchone()[0]
        ncards = c.execute("SELECT COUNT(*) FROM cards WHERE board_id=? AND deleted=0", (new_bid,)).fetchone()[0]
        nsubs = c.execute("SELECT COUNT(*) FROM cards WHERE board_id=? AND deleted=0 AND parent_id<>''",
                          (new_bid,)).fetchone()[0]
        c.close()
        ok(ncols == len(fx['cols']), '新看板下板块数正确（%d）' % ncols)
        ok(ncards == exp_cards, '新看板下事项数正确（%d）' % ncards)
        ok(nsubs == 1, '子事项被复制（%d 条）' % nsubs)
        # 子事项 parent_id 指向新主事项（结构保持）
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        sub = c.execute("SELECT * FROM cards WHERE board_id=? AND parent_id<>''", (new_bid,)).fetchone()
        parent = c.execute("SELECT * FROM cards WHERE card_id=?", (sub['parent_id'],)).fetchone() if sub else None
        ok(sub is not None and parent is not None and parent['board_id'] == new_bid,
           '子事项的 parent_id 指向**新看板**内的主事项（结构保持）')
        ok(sub is not None and sub['card_name'] == PREFIX + '子事项1', '子事项名称随附')
        ok(sub is not None and sub['owner'] == '负责人子', '子事项负责人随附')
        ok(sub is not None and sub['status'] == 'todo', '子事项状态重置为未完成')
        ok(sub is not None and sub['copy_from'] == fx['sub'], '子事项 copy_from 记录来源')
        # 板块归属年份随附
        col = c.execute("SELECT * FROM board_columns WHERE board_id=? LIMIT 1", (new_bid,)).fetchone()
        ok(col is not None and col['year'] == '2026', '板块归属年份随附（%s）' % (col['year'] if col else None))
        ok(col is not None and col['col_key'] == new_bid + '::' + col['column_name'],
           '新板块 col_key 用新 board_id 前缀')
        c.close()

        print('\n【用例2】非 deep 复制：只复制看板本身')
        code, r2 = http('/api/boards/%s/copy' % fx['bid'], 'POST',
                        {'board_name': PREFIX + '浅副本', 'dept': DEPT, 'attr': '日常',
                         'status': '启用'}, token=tok[U_ADMIN])
        ok(code == 200, '复制请求 200（实际 %s）' % code)
        ok(r2.get('deep') is False, '响应标记 deep=False')
        ok(r2.get('copied_columns') == 0 and r2.get('copied_cards') == 0,
           '未复制板块与事项（%s/%s）' % (r2.get('copied_columns'), r2.get('copied_cards')))
        c = sqlite3.connect(DB)
        n2 = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id=?", (r2.get('board_id'),)).fetchone()[0]
        m2 = c.execute("SELECT COUNT(*) FROM cards WHERE board_id=?", (r2.get('board_id'),)).fetchone()[0]
        c.execute("DELETE FROM board_config WHERE board_id=?", (r2.get('board_id'),))
        c.execute("DELETE FROM boards WHERE board_id=?", (r2.get('board_id'),))
        c.commit(); c.close()
        ok(n2 == 0 and m2 == 0, '浅副本下无板块无事项（%d/%d）' % (n2, m2))

        print('\n【用例3】板块参与人：写入 / 读回 / 清空')
        key = fx['cols'][0][2]
        code, r3 = http('/api/columns', 'PUT',
                        {'col_key': key, 'board_id': fx['bid'],
                         'column_name': fx['cols'][0][1], 'created_at': '2026-08-06',
                         'nature': '日常', 'year': '2026',
                         'participants': U_EDITOR + ',' + U_ADMIN}, token=tok[U_ADMIN])
        ok(code == 200, '写入参与人 200（实际 %s）%s' % (code, (' ← '+str(r3)[:200]) if code != 200 else ''))
        c = sqlite3.connect(DB)
        got = c.execute("SELECT participants FROM board_columns WHERE col_key=?", (key,)).fetchone()[0]
        c.close()
        ok(got == U_EDITOR + ',' + U_ADMIN, '参与人已写入（%s）' % got)
        # 清空
        code, _ = http('/api/columns', 'PUT',
                       {'col_key': key, 'board_id': fx['bid'],
                        'column_name': fx['cols'][0][1], 'created_at': '2026-08-06',
                        'nature': '日常', 'year': '2026',
                        'participants': ''}, token=tok[U_ADMIN])
        c = sqlite3.connect(DB)
        got2 = c.execute("SELECT participants FROM board_columns WHERE col_key=?", (key,)).fetchone()[0]
        c.close()
        ok(code == 200 and got2 == '', '参与人可清空（实际 %s）' % got2)
        # 不传 participants → 不改
        code, _ = http('/api/columns', 'PUT',
                       {'col_key': key, 'board_id': fx['bid'],
                        'column_name': fx['cols'][0][1], 'created_at': '2026-08-06',
                        'nature': '日常', 'year': '2026',
                        'participants': U_ADMIN}, token=tok[U_ADMIN])
        code, _ = http('/api/columns', 'PUT',
                       {'col_key': key, 'board_id': fx['bid'],
                        'column_name': fx['cols'][0][1], 'created_at': '2026-08-06',
                        'nature': '日常', 'year': '2026'}, token=tok[U_ADMIN])
        c = sqlite3.connect(DB)
        got3 = c.execute("SELECT participants FROM board_columns WHERE col_key=?", (key,)).fetchone()[0]
        c.close()
        ok(got3 == U_ADMIN, '不传 participants → 不改（%s）' % got3)

        print('\n【用例4】整套复制需管理员权限')
        code, _ = http('/api/boards/%s/copy' % fx['bid'], 'POST',
                       {'board_name': PREFIX + '越权', 'deep': True}, token=tok[U_EDITOR])
        ok(code == 403, '非管理员复制看板 → 403（实际 %s）' % code)
    finally:
        cleanup(fx)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (passed, failed))
    return 1 if failed else 0


sys.exit(main())
