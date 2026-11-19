# -*- coding: utf-8 -*-
"""T-198 删除与导出权限测试（用户口径）：

删除（单个 + 批量勾选）：
  · 仅能删除**自己可见**的事项（T-197 列表过滤同口径——事项身份不豁免板块过滤）；
  · 身份门槛（perm 内核 OP_DELETE ≥ LV_CARD_OWNER）：事项负责人 /
    上级板块负责人 / 上级看板负责人 / 架构负责人；事项参与人不可删。
导出勾选：
  · 只要事项对用户**可见**即可导出（无身份门槛）；导出内容 = 筛选后内容
    （card_ids 与可见集合取交集，不可见 id 静默剔除）。
批量部分无权限：deleted / failed 分列表返回，互不影响。

夹具（__t198_ 前缀，结构同 T-197：看板 B 归属部门 D7 + 工作组 G1 绑定 B）：
  C1 owner=u_cown      ：c1a owner=u_own1（板块对 u_own1 隐藏）/ c1b owner=张三
  C2 participants=u_cpart,u_own1：
       c2a owner=u_own1（u_own1 可见可删）/ c2b owner=张三 cc=u_cpart（u_cpart 可见）
       c2c owner=张三 / c2d owner=u_cpart
  C3 无身份            ：c3a owner=u_own1（板块隐藏）
  C4 owner=u_cown      ：c4a owner=张三
"""
import io
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'src', 'app.db')
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
P = '__t198_'
BID = P + 'bid'
C1 = BID + '::' + P + '板块一'
C2 = BID + '::' + P + '板块二'
C3 = BID + '::' + P + '板块三'
C4 = BID + '::' + P + '板块四'
NOW = '2026-11-13 11:00:00'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def cleanup():
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    c = None
    import time as _t
    for _ in range(6):
        try:
            c = sqlite3.connect(DB, timeout=20)
            c.execute('PRAGMA busy_timeout=20000')
            break
        except sqlite3.OperationalError:
            _t.sleep(2)
    c.execute("DELETE FROM org_appointments WHERE node_id IN (970001, 970002)")
    c.execute("DELETE FROM org_nodes WHERE id IN (970001, 970002)")
    c.execute("DELETE FROM workgroups WHERE id = 970101")
    c.execute("DELETE FROM team_members WHERE account LIKE ? ESCAPE '{}'".format(e), (P + '%',))
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('users', 'username'), ('board_config', 'board_id'),
                   ('audit_logs', 'target')):
        if col:
            c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
        else:
            c.execute(f"DELETE FROM {t} WHERE target LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('board_config', 'board_id')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'",
                       (pat,)).fetchone()[0]
    n += c.execute("SELECT COUNT(*) FROM org_nodes WHERE id IN (970001,970002)").fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def setup():
    c = None
    try:
        cleanup()
        c = sqlite3.connect(DB, timeout=20)
        c.execute('PRAGMA busy_timeout=20000')
        for a in ('u_bown', 'u_cown', 'u_cpart', 'u_own1', 'u_arch'):
            c.execute("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq,"
                      "allowed_boards,allowed_columns) VALUES(?,?,?,?,?,?)",
                      (P + a, hash_pw('At159357'), 'editor', 1, '*', '*'))
        for a, nm in (('u_bown', '王板长'), ('u_cown', '刘块长'),
                      ('u_cpart', '陈块参'), ('u_own1', '赵事项'), ('u_arch', '孙架构')):
            c.execute("INSERT OR REPLACE INTO team_members(name,account,departments,created_at) "
                      "VALUES(?,?,?,?)", (P + nm, P + a, P + '部门D8', NOW))
        c.execute("INSERT OR REPLACE INTO boards(board_id,board_name,owner,created_at) VALUES(?,?,?,?)",
                  (BID, P + '看板', P + 'u_bown', NOW))
        for ck, cid, nm, owner, parts in (
                (C1, P + 'cid1', P + '板块一', P + 'u_cown', ''),
                (C2, P + 'cid2', P + '板块二', '', P + 'u_cpart,' + P + 'u_own1'),
                (C3, P + 'cid3', P + '板块三', '', ''),
                (C4, P + 'cid4', P + '板块四', P + 'u_cown', '')):
            c.execute("INSERT OR REPLACE INTO board_columns(col_key,column_id,board_id,column_name,"
                      "created_at,creator,nature,year,completion,owner,participants) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (ck, cid, BID, nm, NOW, 'admin', '日常', '2026', 'open', owner, parts))
        # (card_id, column_id, 板块名, 事项名, owner, cc)
        cards = [
            (P + 'c1a', P + 'cid1', P + '板块一', P + '事项甲', P + 'u_own1', ''),
            (P + 'c1b', P + 'cid1', P + '板块一', P + '事项乙', '张三', ''),
            (P + 'c2a', P + 'cid2', P + '板块二', P + '事项丙', P + 'u_own1', ''),
            (P + 'c2b', P + 'cid2', P + '板块二', P + '事项丁', '张三', P + 'u_cpart'),
            (P + 'c2c', P + 'cid2', P + '板块二', P + '事项戊', '张三', ''),
            (P + 'c2d', P + 'cid2', P + '板块二', P + '事项己', P + 'u_cpart', ''),
            (P + 'c3a', P + 'cid3', P + '板块三', P + '事项庚', P + 'u_own1', ''),
            (P + 'c4a', P + 'cid4', P + '板块四', P + '事项辛', '张三', ''),
        ]
        for cid, colid, cnm, name, owner, cc in cards:
            c.execute("INSERT OR REPLACE INTO cards(card_id,board_id,board_name,column_id,"
                      "column_name,card_name,status,owner,cc,created,deleted,parent_id) "
                      "VALUES(?,?,?,?,?,?,'open',?,?,?,0,'')",
                      (cid, BID, P + '看板', colid, cnm, name, owner, cc, NOW))
        c.execute("INSERT OR REPLACE INTO org_nodes(id,name,node_type,parent_id,created_at) "
                  "VALUES(970001,?,'dept',0,?)", (P + '部门D8', NOW))
        c.execute("INSERT OR REPLACE INTO workgroups(id,name,parent_id,leader,boards,created_at) "
                  "VALUES(970101,?,970001,'',?,?)", (P + '组G1', BID, NOW))
        c.execute("INSERT OR REPLACE INTO org_nodes(id,name,node_type,parent_id,wg_id,created_at) "
                  "VALUES(970002,?,'group',970001,970101,?)", (P + '组G1', NOW))
        c.execute("INSERT OR REPLACE INTO board_config(board_id,dept,dept_node_id,attr,status,"
                  "created_at) VALUES(?,?,?,?,?,?)",
                  (BID, P + '部门D8', 970001, '日常', '启用', NOW))
        mid_arch = c.execute("SELECT id FROM team_members WHERE account=?",
                             (P + 'u_arch',)).fetchone()[0]
        c.execute("INSERT OR REPLACE INTO org_appointments(node_id,member_id,role_key,is_primary,"
                  "created_at) VALUES(970001,?,'dept_head',0,?)", (mid_arch, NOW))
        for a in ('u_own1', 'u_cown', 'u_cpart', 'u_bown'):
            mid = c.execute("SELECT id FROM team_members WHERE account=?", (P + a,)).fetchone()[0]
            c.execute("INSERT OR REPLACE INTO org_appointments(node_id,member_id,role_key,"
                      "is_primary,created_at) VALUES(970002,?,'member',0,?)", (mid, NOW))
        c.commit()
    finally:
        if c is not None:
            c.close()


def call(method, path, token, body=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            if raw:
                return r.status, data
            return r.status, json.loads(data)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def tok(u):
    return make_token(P + u)


def xlsx_card_names(data):
    """从导出 xlsx 中提取全部单元格文本集合 + 数据行数。"""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    texts = set()
    for r in rows[1:]:
        for v in r:
            if v:
                texts.add(str(v))
    return texts, max(0, len(rows) - 1)


def main():
    print('== ⑨ 先验导出口径（删除动作执行前，保持计数稳定）==', flush=True)
    s, d = call('GET', '/api/export/xlsx?board_ids=' + BID, tok('u_cpart'), raw=True)
    texts, nrows = xlsx_card_names(d)
    ok(s == 200 and nrows == 2, '板块参与人导出 → 仅 2 行（c2b 参与人 / c2c 负责人；c2a 无身份不可见）')
    ok((P + '事项丁') in texts and (P + '事项己') in texts and (P + '事项丙') not in texts,
       '导出内容 = 可见集合（不含无身份事项丙）')
    s, d = call('GET', '/api/export/xlsx?board_ids=' + BID, tok('u_own1'), raw=True)
    texts, nrows = xlsx_card_names(d)
    ok(s == 200 and nrows == 1 and (P + '事项丙') in texts,
       'u_own1 导出 → 仅 1 行（c2a：板块参与人 + 事项负责人；隐藏板块下事项不出现）')
    s, d = call('GET', '/api/export/xlsx?board_ids=' + BID + '&card_ids='
                + ','.join([P + 'c1b', P + 'c2b', P + 'c2c', P + 'c2d']), tok('u_cpart'), raw=True)
    texts, nrows = xlsx_card_names(d)
    ok(s == 200 and nrows == 2 and (P + '事项己') in texts,
       '导出勾选 card_ids 含不可见项 → 交集剔除（c1b/c2c 不可见静默丢弃，仅 c2b/c2d 2 行）')
    s, d = call('GET', '/api/export/xlsx?board_ids=' + BID, tok('u_bown'), raw=True)
    texts, nrows = xlsx_card_names(d)
    ok(s == 200 and nrows == 8, '看板负责人导出 → 全部 8 行（与列表同口径）')

    print('== ① 末级用户=事项负责人，删除**可见**事项 → 200 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c2a', tok('u_own1'))
    ok(s == 200, 'u_own1 删 c2a（板块参与人 + 事项负责人，事项可见）→ 200（实际 %s）' % s)

    print('== ② 事项负责人但板块对其隐藏 → 403（可见性约束）==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c1a', tok('u_own1'))
    ok(s == 403, 'u_own1 删 c1a（负责人身份，但板块一对其隐藏）→ 403（实际 %s %s）' % (s, d))
    s, d = call('DELETE', '/api/cards/' + P + 'c3a', tok('u_own1'))
    ok(s == 403, 'u_own1 删 c3a（板块三无任何身份）→ 403')

    print('== ③ 事项参与人（非负责人）删可见事项 → 403 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c2b', tok('u_cpart'))
    ok(s == 403, 'u_cpart 删 c2b（仅参与人身份）→ 403（实际 %s）' % s)

    print('== ④ 板块负责人删板内事项 → 200 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c1b', tok('u_cown'))
    ok(s == 200, 'u_cown 删 c1b（上级板块负责人）→ 200（实际 %s）' % s)

    print('== ⑤ 上级看板负责人删任意事项 → 200 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c4a', tok('u_bown'))
    ok(s == 200, 'u_bown 删 c4a → 200（实际 %s）' % s)

    print('== ⑥ 架构负责人删事项 → 200 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c2c', tok('u_arch'))
    ok(s == 200, 'u_arch 删 c2c → 200（实际 %s）' % s)

    print('== ⑦ 批量删除：部分无权限 → deleted/failed 分列 ==', flush=True)
    s, d = call('POST', '/api/cards/batch-delete', tok('u_cpart'),
                {'card_ids': [P + 'c2b', P + 'c2d']})
    ok(s == 200, '批量接口 200')
    ok([x['card_id'] for x in d.get('deleted', [])] == [P + 'c2d'],
       '有权项 c2d 删除成功（实际 %s）' % d.get('deleted'))
    fl = d.get('failed', [])
    ok([x['card_id'] for x in fl] == [P + 'c2b'] and fl and fl[0].get('reason'),
       '无权项 c2b 记入 failed 且带原因（实际 %s）' % fl)

    print('== ⑧ 管理员删除不受限 ==', flush=True)
    s, d = call('DELETE', '/api/cards/' + P + 'c1a', make_token('admin'))
    ok(s == 200, '管理员删 c1a → 200')


if __name__ == '__main__':
    try:
        setup()
        main()
    finally:
        left = cleanup()
        fails = [m for c, m in N if not c]
        print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
        for m in fails:
            print('  FAIL:', m)
        if fails or left:
            sys.exit(1)
