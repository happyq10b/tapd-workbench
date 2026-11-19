#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#130 API 测试：事项级权限控制
  ① 待办任务（子待办）仅**事项负责人**可发起；非负责人 403 明确提示
  ② 状态勾选/状态更新仅**事项负责人**可操作；非负责人 403 明确提示
  ③ 参与人仍可改内容字段（描述等）—— 确认未误伤既有权限口径
  ④ 管理员直通
夹具：__pm_ 前缀（用户/成员/看板/板块/卡片），try/finally 全量清理（§3.3）
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__pm_'
BID = P + 'board'
CA = P + 'cardA'      # 负责人 = __pm_测试员（__pm_u1）
CB = P + 'cardB'      # 负责人 = __pm_别人；__pm_u1 是参与人
U1 = P + 'u1'
PASS = FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id=? OR card_name LIKE ?", (BID, P + '%'))
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id=?", (BID,))
    c.execute("DELETE FROM boards WHERE board_id=?", (BID,))
    c.execute("DELETE FROM actions WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username=?", (U1,))
    c.execute("DELETE FROM team_members WHERE name=? OR account=?", (P + '测试员', U1))
    c.commit(); c.close()


def make_fixtures():
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO boards(board_id,board_name,sort,created_at) VALUES(?,?,0,datetime('now'))",
              (BID, P + '权限测试看板'))
    c.execute("INSERT INTO board_columns(col_key,board_id,column_name,nature,participants) VALUES(?,?,?,?,?)",
              (BID + '::' + P + '板块', BID, P + '板块', '日常', U1))   # ⑤ 可见性收紧：U1 需为板块参与人
    for cid, owner, cc in ((CA, P + '测试员', ''), (CB, P + '别人', P + '测试员')):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_name,card_name,status,owner,cc,"
                  "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),0)",
                  (cid, BID, P + '权限测试看板', P + '板块', P + ('卡A' if cid == CA else '卡B'),
                   'open', owner, cc, '2026年第46周'))
    c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
              "VALUES(?,?,?,?,?,1)", (U1, hash_pw('x'), 'x', 'editor', BID))
    c.execute("INSERT INTO team_members(name,account) VALUES(?,?)", (P + '测试员', U1))
    c.commit(); c.close()


def call(method, path, token, body=None):
    safe = path.split('?')[0]
    query = urllib.parse.quote(path.split('?', 1)[1], safe='=&,') if '?' in path else ''
    path = safe + ('?' + query if query else '')
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
    try:
        make_fixtures()
        t1 = make_token(U1)       # 负责人（卡A）/ 参与人（卡B）
        ta = make_token('admin')  # 管理员

        # 可见性自检：__pm_u1 能看到夹具卡
        st, d = call('GET', '/api/cards?board_ids=' + BID, t1)
        ok(st == 200 and len(d.get('cards', [])) == 2, '夹具可见性自检：__pm_u1 可见 2 卡（%d）' % len(d.get('cards', [])))

        print('== ① 负责人操作自己的卡 A ==')
        st, r = call('POST', '/api/cards/%s/subtasks' % CA, t1, {'title': P + '待办1'})
        ok(st == 200, '负责人发起待办 → 200')
        st, r = call('PUT', '/api/cards/' + CA, t1, {'fields': {'status': 'done', 'status_name': '已完成'}})
        ok(st == 200, '负责人勾选完成 → 200')

        print('== ② 非负责人（参与人）操作卡 B ==')
        st, r = call('POST', '/api/cards/%s/subtasks' % CB, t1, {'title': P + '待办2'})
        ok(st == 403 and '仅事项负责人' in json.dumps(r, ensure_ascii=False),
           '非负责人发起待办 → 403：%s' % json.dumps(r, ensure_ascii=False)[:80])
        st, r = call('PUT', '/api/cards/' + CB, t1, {'fields': {'status': 'done', 'status_name': '已完成'}})
        ok(st == 403 and '仅事项负责人可变更事项状态' in json.dumps(r, ensure_ascii=False),
           '非负责人改状态 → 403：%s' % json.dumps(r, ensure_ascii=False)[:80])
        st, r = call('PUT', '/api/cards/' + CB, t1, {'fields': {'description': P + '参与人改内容'}})
        ok(st == 200, '参与人改内容字段（描述）→ 200（未误伤既有口径）')

        print('== ③ 管理员直通 ==')
        st, r = call('POST', '/api/cards/%s/subtasks' % CB, ta, {'title': P + '管理员待办'})
        ok(st == 200, '管理员发起待办 → 200')
        st, r = call('PUT', '/api/cards/' + CB, ta, {'fields': {'status': 'progressing', 'status_name': '进行中'}})
        ok(st == 200, '管理员改状态 → 200')

        print('\n结果：PASS=%d FAIL=%d' % (PASS, FAIL))
    finally:
        cleanup()
        c = sqlite3.connect(DB)
        left = c.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE ?", (P + '%',)).fetchone()[0]
        lu = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (U1,)).fetchone()[0]
        c.close()
        print('残留自查：cards=%d users=%d（应为 0 0）' % (left, lu))
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
