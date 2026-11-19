#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-0176 API 测试：编辑锁通用化 + 锁提示姓名显示
  ① 锁提示统一显示**姓名**（locked_by_name），姓名为空回退账号
  ② 通用锁端点 /api/locks/acquire|heartbeat|release|holder（key 走请求体/查询串）
  ③ 板块锁：编辑 / 删除（含板块下事项被编辑时拒绝删板块）
  ④ 看板锁：改名 / 批量删除跳过被编辑看板
  ⑤ 事项锁缺陷修复：写路径 check→acquire（持锁他人 409；无锁直写成功后不留残锁）
  ⑥ 架构节点锁 / 成员名单锁 / 公告锁
夹具：__lk_ 前缀（用户/成员/看板/板块/卡片/节点/公告），try/finally 全量清理（§3.3）
断言全部相对化（不硬编码全局基线数字）。
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__lk_'
BID = P + 'board'
COLKEY = BID + '::' + P + '板块'
CARD = P + 'card'
U1 = P + 'u1'          # editor，成员姓名 __lk_张三（显示姓名断言用）
U2 = P + 'u2'          # admin，成员姓名为空（账号兜底断言用）
N1 = P + '张三'
PASS = FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id=? OR card_id LIKE ?", (BID, P + '%'))
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id=? OR col_key LIKE ?", (BID, P + '%'))
    c.execute("DELETE FROM boards WHERE board_id=?", (BID,))
    c.execute("DELETE FROM actions WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (P + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
    c.execute("DELETE FROM notices WHERE title LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username IN (?,?)", (U1, U2))
    c.execute("DELETE FROM team_members WHERE name LIKE ? OR account IN (?,?)", (P + '%', U1, U2))
    c.commit(); c.close()


def make_fixtures():
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO boards(board_id,board_name,sort,created_at) VALUES(?,?,0,datetime('now'))",
              (BID, P + '锁测试看板'))
    c.execute("INSERT INTO board_columns(col_key,board_id,column_name,nature,created_at,creator) "
              "VALUES(?,?,?,?,datetime('now'),?)", (COLKEY, BID, P + '板块', '日常', U1))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_name,card_name,status,owner,cc,"
              "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),0)",
              (CARD, BID, P + '锁测试看板', P + '板块', P + '卡片', 'open', N1, '', '2026年第46周'))
    c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
              "VALUES(?,?,?,?,?,1)", (U1, hash_pw('x'), 'x', 'editor', BID))
    # ⑤ 可见性收紧（2026-11-12 严格全量）：U1 需为看板负责人才能看到夹具板块
    c.execute("UPDATE boards SET owner=? WHERE board_id=?", (U1, BID))
    c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
              "VALUES(?,?,?,?,?,1)", (U2, hash_pw('x'), 'x', 'admin', '*'))
    # U1 有姓名（姓名显示），U2 姓名为空（兜底显示账号）
    c.execute("INSERT INTO team_members(name,account) VALUES(?,?)", (N1, U1))
    c.execute("INSERT INTO team_members(name,account) VALUES('',?)", (U2,))
    c.execute("INSERT INTO org_nodes(name,node_type,parent_id) VALUES(?,?,0)", (P + '节点', 'group'))
    c.execute("INSERT INTO notices(scope,title,content,author,enabled) VALUES('all',?,?,'t',1)",
              (P + '公告', 'x'))
    c.commit(); c.close()
    c = sqlite3.connect(DB)
    nid = c.execute("SELECT id FROM org_nodes WHERE name=?", (P + '节点',)).fetchone()[0]
    nt = c.execute("SELECT id FROM notices WHERE title=?", (P + '公告',)).fetchone()[0]
    c.close()
    return nid, nt


def call(method, path, token, body=None):
    # 路径与查询分别做 URL 编码；safe 保留 '/:%' —— 调用方可预先 quote（% 序列原样透传，不二次编码）
    if '?' in path:
        p, q = path.split('?', 1)
        q = urllib.parse.quote(q, safe='=&,')
    else:
        p, q = path, ''
    p = urllib.parse.quote(p, safe='/:.%~_')
    path = p + ('?' + q if q else '')
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    from app.app import make_token
    cleanup()
    nid, ntid = make_fixtures()          # 先建夹具（token 的会话代数来自 users.active_seq）
    t1, t2 = make_token(U1), make_token(U2)
    try:
        # ---------- ① 通用锁端点 + 姓名显示 ----------
        print('① 通用锁端点与姓名显示')
        LK = 'column:' + COLKEY
        call('POST', '/api/locks/release', t1, {'key': LK})   # 清跨运行残留内存锁
        call('POST', '/api/locks/release', t2, {'key': LK})
        s, r = call('POST', '/api/locks/acquire', t1, {'key': LK})
        ok(s == 200, f'持有人认领板块锁 → 200（实际 {s} {r}）')
        s, r = call('POST', '/api/locks/acquire', t2, {'key': LK})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False),
           f'他人认领 → 409 且提示**姓名**张三（实际 {s} {r}）')
        s, r = call('GET', '/api/locks/holder?key=column:' + COLKEY, t2)
        ok(s == 200 and r.get('locked_by') == U1 and r.get('locked_by_name') == N1,
           f'holder 接口返回账号+姓名（实际 {r}）')
        s, r = call('POST', '/api/locks/release', t2, {'key': 'column:' + COLKEY})
        s, r = call('GET', '/api/locks/holder?key=column:' + COLKEY, t2)
        ok(r.get('locked_by') == U1, '非持有人 release 不生效（锁仍在张三手里）')
        s, r = call('POST', '/api/locks/heartbeat', t1, {'key': 'column:' + COLKEY})
        ok(s == 200, '持有人 heartbeat → 200')
        s, r = call('POST', '/api/locks/release', t1, {'key': 'column:' + COLKEY})
        s, r = call('GET', '/api/locks/holder?key=column:' + COLKEY, t1)
        ok(r.get('locked_by') is None, '持有人 release 后锁释放')

        # ---------- ② 板块锁 ----------
        print('② 板块锁（编辑/删除）')
        call('POST', '/api/locks/acquire', t1, {'key': 'column:' + COLKEY})
        s, r = call('PUT', '/api/columns', t2, {'col_key': COLKEY, 'board_id': BID, 'column_name': P + '板块2',
                                                'created_at': '2026-11-12', 'nature': '日常', 'year': '2026'})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人编辑板块 → 409 姓名（实际 {s} {r}）')
        s, r = call('DELETE', '/api/columns/' + urllib.parse.quote(COLKEY, safe=''), t2)
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人删除板块 → 409 姓名（实际 {s} {r}）')
        # 板块下事项被他人编辑 → 删板块同样拒绝
        call('POST', '/api/locks/release', t1, {'key': 'column:' + COLKEY})
        call('POST', f'/api/cards/{CARD}/lock', t1)
        s, r = call('DELETE', '/api/columns/' + urllib.parse.quote(COLKEY, safe=''), t2)
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False),
           f'板块下事项被张三编辑 → 删板块 409 姓名（实际 {s} {r}）')
        call('POST', f'/api/cards/{CARD}/unlock', t1)
        call('POST', '/api/locks/release', t1, {'key': 'column:' + COLKEY})   # 释放②认领的板块锁

        # ---------- ③ 看板锁 ----------
        print('③ 看板锁（改名/批量删除跳过）')
        call('POST', '/api/locks/acquire', t1, {'key': 'board:' + BID})
        s, r = call('PUT', f'/api/boards/{BID}/rename', t2, {'board_name': P + '改名'})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人改看板名 → 409 姓名（实际 {s} {r}）')
        s, r = call('POST', '/api/boards/bulk-delete', t2, {'board_ids': [BID]})
        ok(s == 200 and BID in json.dumps(r.get('skipped') or [], ensure_ascii=False) and r.get('deleted') == 0,
           f'批量删除跳过被编辑看板（实际 {s} {r}）')
        call('POST', '/api/locks/release', t1, {'key': 'board:' + BID})

        # ---------- ④ 事项锁缺陷修复（check→acquire）+ 姓名显示 ----------
        print('④ 事项锁（写路径认领 + 姓名显示 + 无残锁）')
        call('POST', f'/api/cards/{CARD}/lock', t1)
        s, r = call('GET', f'/api/cards?board_ids={BID}&size=10', t2)
        cards = [c for c in (r.get('cards') or []) if c['card_id'] == CARD]
        ok(bool(cards) and cards[0].get('locked_by') == U1 and cards[0].get('locked_by_name') == N1,
           f'列表返回 locked_by=账号 + locked_by_name=姓名（实际 {cards[0].get("locked_by")}/{cards[0].get("locked_by_name") if cards else None}）')
        s, r = call('PUT', f'/api/cards/{CARD}', t2, {'fields': {'description': 'x'}, 'version': None} if False
                    else {'fields': {'description': 'x'}})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人保存被锁卡片 → 409 姓名（实际 {s} {r}）')
        s, r = call('POST', f'/api/cards/{CARD}/subtasks', t2, {'title': P + '子事项'})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人给被锁卡片加子事项 → 409 姓名（实际 {s} {r}）')
        call('POST', f'/api/cards/{CARD}/unlock', t1)
        # 无锁直写：fresh 认领 → 写成功 → 不留残锁
        s, r = call('PUT', f'/api/cards/{CARD}', t2, {'fields': {'description': P + '直写'}})
        ok(s == 200, f'无锁直写卡片 → 200（check→acquire 不误伤，实际 {s} {r}）')
        s2, r2 = call('GET', f'/api/cards?board_ids={BID}&size=10', t1)
        row = [c for c in (r2.get('cards') or []) if c['card_id'] == CARD]
        ok(bool(row) and not row[0].get('locked_by'), '直写成功后无残锁（locked_by 为空）')

        # ---------- ⑤ 架构节点锁 ----------
        print('⑤ 架构节点锁')
        call('POST', '/api/locks/acquire', t1, {'key': f'org:{nid}'})
        s, r = call('PUT', f'/api/org/nodes/{nid}', t2, {'name': P + '节点2', 'node_type': 'group', 'parent_id': 0})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人改节点 → 409 姓名（实际 {s} {r}）')
        s, r = call('DELETE', f'/api/org/nodes/{nid}', t2)
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'他人删节点 → 409 姓名（实际 {s} {r}）')
        call('POST', '/api/locks/release', t1, {'key': f'org:{nid}'})

        # ---------- ⑥ 成员名单锁 / 公告锁 ----------
        print('⑥ 成员名单锁 / 公告锁')
        mid_row = sqlite3.connect(DB)
        mid = mid_row.execute("SELECT id FROM team_members WHERE account=?", (U2,)).fetchone()[0]
        mid_row.close()
        call('POST', '/api/locks/acquire', t1, {'key': 'team:roster'})
        s, r = call('PUT', f'/api/team/{mid}', t2, {'name': P + '改名人'})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'名单被张三锁定 → 他人编辑成员 409 姓名（实际 {s} {r}）')
        call('POST', '/api/locks/release', t1, {'key': 'team:roster'})
        call('POST', '/api/locks/acquire', t1, {'key': f'notice:{ntid}'})
        s, r = call('PUT', f'/api/notices/{ntid}', t2, {'scope': 'all', 'title': P + '公告2', 'content': 'x', 'enabled': 1, 'sort': 0})
        ok(s == 409 and N1 in json.dumps(r, ensure_ascii=False), f'公告被张三编辑 → 他人保存 409 姓名（实际 {s} {r}）')
        call('POST', '/api/locks/release', t1, {'key': f'notice:{ntid}'})

        # ---------- ⑦ 姓名为空兜底（U2 持锁 → 显示账号） ----------
        print('⑦ 姓名为空兜底')
        call('POST', f'/api/cards/{CARD}/lock', t2)
        s, r = call('GET', f'/api/cards?board_ids={BID}&size=10', t1)
        row = [c for c in (r.get('cards') or []) if c['card_id'] == CARD]
        ok(bool(row) and row[0].get('locked_by') == U2 and row[0].get('locked_by_name') == U2,
           f'持有人姓名为空 → locked_by_name 回退账号（实际 {row[0].get("locked_by_name") if row else None}）')
        s, r = call('PUT', f'/api/cards/{CARD}', t1, {'fields': {'description': 'y'}})
        blob = json.dumps(r, ensure_ascii=False)
        ok(s == 409 and U2 in blob, f'409 提示含账号兜底（实际 {s} {blob[:120]}）')
        call('POST', f'/api/cards/{CARD}/unlock', t2)
    finally:
        cleanup()
    print(f'\n==== 结果: PASS={PASS} FAIL={FAIL} ====')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
