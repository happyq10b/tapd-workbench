#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""板块级可见性收紧测试（2026-11-12，用户确认「严格全量执行」）
  ⑤层口径：板块可见 = 板块负责人/参与人 ∪ 对该看板权限 ≥ 看板负责人
  （看板负责人 boards.owner + 架构负责人岗位任命负责范围，与 perm.py
   effective_level 架构层映射一致）；未配置 ACL 的板块普通成员一律不可见。
  同时回归「非法的锁资源标识」修复（真实形态 col_key 含全角括号与斜杠）。
夹具：__vis_ 前缀，try/finally 全量清理（§3.3）。
"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__vis_'
B = P + 'b1'                      # 测试看板（三个板块：一配置两未配置）
C1 = P + 'C1'                     # 配置：负责人 U2 + 参与人 U3；col_key 含全角括号/斜杠（复现锁修复）
C2, C3 = P + 'C2', P + 'C3'       # 未配置任何 ACL
CARD1, CARD2, CARD3 = P + 'k1', P + 'k2', P + 'k3'
U1, U2, U3, U4, U5 = (P + x for x in ('u1', 'u2', 'u3', 'u4', 'u5'))
PASS = FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'),
                                 data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def cleanup():
    c = sqlite3.connect(DB)
    for t, w in (('cards', 'board_id=?'), ('board_columns', 'board_id=?'),
                 ('boards', 'board_id=?'), ('board_config', 'board_id=?')):
        c.execute(f'DELETE FROM {t} WHERE {w}', (B,))
    c.execute("DELETE FROM org_appointments WHERE member_id IN "
              "(SELECT id FROM team_members WHERE account LIKE ?)", (P + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (P + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.commit(); c.close()


def make_fixtures():
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO boards(board_id,board_name,sort,created_at) VALUES(?,?,0,datetime('now'))",
              (B, P + '看板'))
    c.execute("UPDATE boards SET owner=? WHERE board_id=?", (U4, B))   # U4 = 看板负责人
    # 板块：C1 配置 owner/participants；col_key 含全角括号与斜杠（真实形态，兼验锁修复）
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants)"
              " VALUES(?,?,?,?,?,?,'日常','2026',0,?,?)",
              (B + '::' + C1, C1, B, C1, '2026-11-12', '', U2, U3))
    for cid in (C2, C3):
        c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned)"
                  " VALUES(?,?,?,?,?,'','日常','2026',0)", (B + '::' + cid, cid, B, cid, '2026-11-12'))
    # 卡片各一张（column_id 显式）
    for cid, kid in ((C1, CARD1), (C2, CARD2), (C3, CARD3)):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
                  "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'),0)",
                  (kid, B, P + '看板', cid, cid, P + '卡片' + cid[-2:], 'open', '', '', '2026年第46周'))
    # 用户（allowed_boards=B：账号级白名单给出架构层可见看板）
    for u, role in ((U1, 'editor'), (U2, 'editor'), (U3, 'editor'), (U4, 'editor'), (U5, 'editor')):
        c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq)"
                  " VALUES(?,?,?,?,?,1)", (u, hash_pw('x'), 'x', role, B))
        c.execute("INSERT INTO team_members(name,account) VALUES(?,?)", (P + '名' + u[-2:], u))
    # U5 = 组长：架构 group 节点绑定看板 B + group_leader 任命（架构负责人岗位 → 负责范围覆盖 B）
    c.execute("INSERT INTO workgroups(name,parent_id,boards) VALUES(?,0,?)", (P + '组', B))
    wid = c.execute("SELECT id FROM workgroups WHERE name=?", (P + '组',)).fetchone()[0]
    c.execute("INSERT INTO org_nodes(name,node_type,parent_id,wg_id) VALUES(?,'group',0,?)", (P + '节点', wid))
    nid = c.execute("SELECT id FROM org_nodes WHERE name=?", (P + '节点',)).fetchone()[0]
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (U5,)).fetchone()[0]
    c.execute("INSERT INTO org_appointments(node_id,member_id,role_key) VALUES(?,?,'group_leader')", (nid, mid))
    c.commit(); c.close()


def cols_and_cards(token):
    s, r = call('GET', f'/api/cards?board_ids={B}&size=50', token)
    if s != 200:
        return s, [], []
    return s, [c['column_id'] for c in (r.get('columns') or [])], \
           [k['card_id'] for k in (r.get('cards') or [])]


def main():
    from app.app import make_token
    cleanup()
    make_fixtures()
    t1, t2, t3, t4, t5 = (make_token(u) for u in (U1, U2, U3, U4, U5))
    try:
        print('① 列表可见面（严格全量：未配置板块普通成员不可见）')
        s, cols, cards = cols_and_cards(t1)
        ok(s == 200 and not cols and not cards,
           f'普通成员 U1（非负责人/参与人）→ 板块与事项全部不可见（实际 {cols}/{cards}）')
        s, cols, cards = cols_and_cards(t2)
        ok(s == 200 and cols == [C1] and cards == [CARD1],
           f'板块负责人 U2 → 仅看到自己负责的板块（实际 {cols}/{cards}）')
        s, cols, cards = cols_and_cards(t3)
        ok(s == 200 and cols == [C1] and cards == [CARD1],
           f'板块参与人 U3 → 仅看到参与的板块（实际 {cols}/{cards}）')
        s, cols, cards = cols_and_cards(t4)
        ok(s == 200 and sorted(cols) == [C1, C2, C3] and sorted(cards) == [CARD1, CARD2, CARD3],
           f'看板负责人 U4 → 全部板块可见（实际 {cols}/{cards}）')
        s, cols, cards = cols_and_cards(t5)
        ok(s == 200 and sorted(cols) == [C1, C2, C3],
           f'架构负责人（组长，负责范围覆盖）→ 全部板块可见（实际 {cols}）')
        s, cols, cards = cols_and_cards(make_token('admin'))
        ok(s == 200 and sorted(cols) == [C1, C2, C3], '管理员 → 全量可见')

        print('② 直调 API 越权读写拦截（详情类读接口走 check_card_access）')
        s, r = call('GET', f'/api/cards/{CARD2}/comments', t1)
        ok(s == 403, f'普通成员直读未配置板块事项评论 → 403（实际 {s} {r}）')
        s, r = call('GET', f'/api/cards/{CARD1}/comments', t1)
        ok(s == 403, f'普通成员直读已配置板块（非参与）事项评论 → 403（实际 {s}）')
        s, r = call('PUT', f'/api/cards/{CARD2}', t1, {'fields': {'description': P + '越权'}})
        ok(s in (403, 404), f'普通成员直写未配置板块事项 → 拒绝（实际 {s}）')
        s, r = call('GET', f'/api/cards/{CARD2}/comments', t3)
        ok(s == 403, f'板块参与人 U3 读未参与板块（C2）事项 → 403（实际 {s}）')
        s, r = call('GET', f'/api/cards/{CARD1}/comments', t3)
        ok(s == 200, f'板块参与人 U3 读参与板块（C1）事项 → 200（实际 {s}）')

        print('③ 配置生效联动（参与人加入 → 立即可见）')
        c = sqlite3.connect(DB)
        c.execute("UPDATE board_columns SET participants=? WHERE column_id=?", (U3 + ',' + U1, C2))
        c.commit(); c.close()
        s, cols, cards = cols_and_cards(t1)
        ok(s == 200 and cols == [C2] and cards == [CARD2],
           f'U1 被加为 C2 参与人 → 仅 C2 可见（实际 {cols}/{cards}）')

        print('④ 锁修复联动（真实形态 col_key 含全角括号与斜杠）')
        s, r = call('POST', '/api/locks/acquire', t2, {'key': 'column:' + B + '::' + C1})
        ok(s == 200, f'板块负责人认领含全角/斜杠 col_key 锁 → 200（实际 {s} {r}）')
        s, r = call('POST', '/api/locks/acquire', t3, {'key': 'column:' + B + '::' + C1})
        ok(s == 409, '他人认领 → 409')
        s, r = call('PUT', '/api/columns', t3,
                    {'col_key': B + '::' + C1, 'board_id': B, 'column_name': C1,
                     'created_at': '2026-11-12', 'nature': '日常', 'year': '2026'})
        ok(s == 409, f'他人保存被锁板块 → 409（实际 {s}）')
        s, r = call('POST', '/api/locks/release', t2, {'key': 'column:' + B + '::' + C1})
        ok(s == 200, '持有人释放 → 200')
        s, r = call('PUT', '/api/columns', t2,
                    {'col_key': B + '::' + C1, 'board_id': B, 'column_name': C1,
                     'created_at': '2026-11-12', 'nature': '日常', 'year': '2026'})
        ok(s == 200, f'板块负责人编辑板块（原「非法的锁资源标识」场景）→ 200（实际 {s} {r}）')
        s, r = call('POST', '/api/locks/acquire', t1, {'key': 'bogus:xyz'})
        ok(s == 400, '未知前缀 key 仍被拒 → 400（实际 %s）' % s)
    finally:
        cleanup()
    # 残留自查必须在 cleanup 之后（§3.3）
    print('⑤ 夹具残留自查（清理后）')
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM boards WHERE board_id LIKE ?", (P + '%',)).fetchone()[0] \
        + c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (P + '%',)).fetchone()[0] \
        + c.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE ?", (P + '%',)).fetchone()[0] \
        + c.execute("SELECT COUNT(*) FROM team_members WHERE account LIKE ?", (P + '%',)).fetchone()[0] \
        + c.execute("SELECT COUNT(*) FROM cards WHERE board_id LIKE ?", (P + '%',)).fetchone()[0]
    c.close()
    ok(n == 0, f'零残留（实际 {n}）')
    print(f'\n==== 结果: PASS={PASS} FAIL={FAIL} ====')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
