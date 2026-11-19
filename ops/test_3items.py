#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三事项优化 API 测试（2026-11-12）
  ① 政治面貌 datalist 移除【无党派人士】【共青团员】（前端静态断言）
  ② 看板管理负责人/参与人受归属部门约束：
     部门级归属 → 候选=该部门成员（acl/participants 端点 400）；
     中心级归属（财务中心口径）→ 不限（全员可选）
  ③ 评论 @ 候选按当前用户可见性过滤：
     池 = 看板可见（#77 口径）∩ 对当前用户可见（看板关系人 ∪ 部门同事，管理员豁免）；
     add_comment 对池外 mention 403。
夹具：__i3_ 前缀，try/finally 全量清理（§3.3）；断言全部相对化。
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__i3_'
BID = P + 'b1'            # 部门级归属看板（部门约束测试）
BID2 = P + 'b2'           # 公共看板（@ 可见性测试，不配归属）
BID3 = P + 'b3'           # 中心级归属看板（财务中心口径不限）
CARD2 = P + 'c2'
DEPT_A = P + '部门A'
DEPT_B = P + '部门B'
CENTER = P + '中心'
U1 = P + 'u1'             # 部门A 成员（部门约束：合法候选人）
U2 = P + 'u2'             # 部门B 成员（部门约束：非法候选人；管理员角色）
U3 = P + 'u3'             # @ 测试发起人（editor，部门A）
U4 = P + 'u4'             # 部门A 同事（@ 可见）
U5 = P + 'u5'             # 部门B 陌生人（@ 不可见）
U6 = P + 'u6'             # BID2 参与人（看板关系人，@ 可见）
U7 = P + 'u7'             # admin 操作者（acl/participants 需管理员以上权限发起）
N1, N2, N3, N4, N5, N6, N7 = P + '甲', P + '乙', P + '丙', P + '丁', P + '戊', P + '己', P + '庚'
PASS = FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None):
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


def cleanup():
    c = sqlite3.connect(DB)
    for bid in (BID, BID2, BID3):
        c.execute("DELETE FROM cards WHERE board_id=?", (bid,))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
        c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
        c.execute("DELETE FROM board_config WHERE board_id=?", (bid,))
    c.execute("DELETE FROM cards WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM comments WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM messages WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM actions WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.execute("DELETE FROM team_members WHERE name LIKE ? OR account LIKE ?", (P + '%', P + '%'))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
    c.commit(); c.close()


def make_fixtures():
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    # 看板：b1 部门级归属（约束生效）/ b2 公共（@ 测试）/ b3 中心级归属（不限）
    for bid in (BID, BID2, BID3):
        c.execute("INSERT INTO boards(board_id,board_name,sort,created_at) VALUES(?,?,0,datetime('now'))",
                  (bid, P + '看板'))
    c.execute("INSERT INTO board_config(board_id,dept,dept_node_id,attr,status) VALUES(?,?,0,'日常','启用')",
              (BID, DEPT_A))
    c.execute("INSERT INTO org_nodes(name,node_type,parent_id) VALUES(?,'center',0)", (CENTER,))
    # 用户与成员（departments 为 #165 单一来源）
    users = [(U1, 'editor', '*', N1, DEPT_A), (U2, 'admin', '*', N2, DEPT_B),
             (U3, 'editor', BID2, N3, DEPT_A), (U4, 'editor', '*', N4, DEPT_A),
             (U5, 'editor', '*', N5, DEPT_B), (U6, 'editor', '*', N6, ''),
             (U7, 'admin', '*', N7, '')]
    for u, role, ab, name, depts in users:
        c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
                  "VALUES(?,?,?,?,?,1)", (u, hash_pw('x'), 'x', role, ab))
        c.execute("INSERT INTO team_members(name,account,departments) VALUES(?,?,?)", (name, u, depts))
    # BID2 参与人 = U6（看板关系人）
    c.execute("UPDATE boards SET participants=? WHERE board_id=?", (U6, BID2))
    # @ 测试卡片
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,"
              "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'),0)",
              (CARD2, BID2, P + '看板', P + 'col2', P + '板块', P + '卡片', 'open', N1, '', '2026年第46周'))
    # ⑤ 板块可见性收紧（2026-11-12）：CARD2 所在板块注册 ACL，
    #    参与人 = U3（@ 发起人）+ U4（丁，@ 同事 + 评论）——否则板块不可见
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,participants)"
              " VALUES(?,?,?,?,?,'','日常','2026',0,?)",
              (BID2 + '::' + P + '板块', P + 'col2', BID2, P + '板块', '2026-11-12',
               U3 + ',' + U4))
    c.commit(); c.close()
    c = sqlite3.connect(DB)
    center_id = c.execute("SELECT id FROM org_nodes WHERE name=?", (CENTER,)).fetchone()[0]
    c.execute("UPDATE board_config SET dept_node_id=? WHERE board_id=?", (center_id, BID3))
    c.commit(); c.close()


def main():
    from app.app import make_token
    cleanup()
    make_fixtures()          # 先建夹具（token 会话代数来自 users.active_seq）
    t1, t2, t3, t7 = make_token(U1), make_token(U2), make_token(U3), make_token(U7)
    try:
        # ---------- ① 政治面貌 ----------
        print('① 政治面貌 datalist 移除两项')
        html = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        i0 = html.find('pf_political_list')
        seg = html[i0:html.find('</datalist>', i0)] if i0 >= 0 else ''
        ok('群众' in seg and '中共党员' in seg and '民主党派成员' in seg,
           '其余选项保持不变（群众/中共党员/中共预备党员/民主党派成员）')
        ok('共青团员' not in seg and '无党派人士' not in seg,
           '【共青团员】【无党派人士】已从下拉移除')

        # ---------- ② 部门约束：部门级归属 ----------
        print('② 看板负责人/参与人受归属部门约束（部门级 → 400）')
        s, r = call('PUT', f'/api/boards/{BID}/acl', t7, {'owner': U2})
        ok(s == 400 and N2 in json.dumps(r, ensure_ascii=False),
           f'负责人非本部门（乙）→ 400 且提示姓名（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID}/acl', t7, {'owner': U1})
        ok(s == 200, f'负责人本部门（甲）→ 200（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID}/participants', t7,
                    {'participants': U1 + ',' + U2})
        ok(s == 400 and N2 in json.dumps(r, ensure_ascii=False),
           f'参与人含非本部门（乙）→ 400 且提示姓名（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID}/participants', t7,
                    {'participants': U1})
        ok(s == 200, f'参与人全部本部门 → 200（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID}/participants', t7, {'participants': ''})
        ok(s == 200, '清空参与人 → 200（空名单不受约束）')

        # ---------- ②' 中心级归属（财务中心口径）→ 不限 ----------
        print("②' 中心级归属（财务中心口径）→ 不限")
        s, r = call('PUT', f'/api/boards/{BID3}/acl', t7, {'owner': U2})
        ok(s == 200, f'中心级归属可任选负责人（乙）→ 200（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID3}/participants', t7,
                    {'participants': U1 + ',' + U2})
        ok(s == 200, f'中心级归属参与人可跨部门 → 200（实际 {s} {r}）')
        s, r = call('PUT', f'/api/boards/{BID3}/participants', t7, {'participants': ''})
        ok(s == 200, '清理 b3 参与人 → 200')

        # ---------- ③ @ 可见性过滤 ----------
        print('③ 评论 @ 按当前用户可见性过滤')
        s, r = call('GET', f'/api/cards/{CARD2}/mention_pool', t3)
        names = r.get('names') or []
        ok(N4 in names, f'部门A 同事（丁）在池中（实际 {names}）')
        ok(N6 in names, f'看板参与人（己）在池中（实际 {names}）')
        ok(N5 not in names, f'部门B 陌生人（戊）不可见 → 不在池中（实际 {names}）')
        ok(N2 not in names, '与发起人无交集的成员不在池中')
        # 管理员豁免：池不受发起人可见性限制（仍受看板可见约束）
        s, r = call('GET', f'/api/cards/{CARD2}/mention_pool', t2)
        names_admin = r.get('names') or []
        ok(N5 in names_admin, f'管理员发起时陌生人（戊）回到池中（实际 {names_admin}）')
        # add_comment 校验：池外 mention 403
        s, r = call('POST', f'/api/cards/{CARD2}/comments', t3,
                    {'content': P + '评论', 'mentions': [N5]})
        ok(s == 403 and N5 in json.dumps(r, ensure_ascii=False),
           f'@ 不可见成员（戊）→ 403（实际 {s} {r}）')
        s, r = call('POST', f'/api/cards/{CARD2}/comments', t3,
                    {'content': P + '评论', 'mentions': [N4]})
        ok(s == 200, f'@ 可见成员（丁）→ 200（实际 {s} {r}）')
        # 池外 mention 未入库（comments.mentions 只含可见成员）
        c = sqlite3.connect(DB)
        row = c.execute('SELECT mentions FROM comments WHERE card_id=? ORDER BY id DESC LIMIT 1',
                        (CARD2,)).fetchone()
        ok(row is not None and N5 not in (row[0] or ''),
           '不存在绕过校验的残留 mention 数据')
        c.close()
    finally:
        cleanup()
    # ---------- 夹具残留自查（cleanup 之后） ----------
    print('夹具残留自查')
    c = sqlite3.connect(DB)
    q = lambda s_: c.execute(s_).fetchone()[0]
    ok(q("SELECT COUNT(*) FROM users WHERE username LIKE '%" + P + "%'") == 0, 'users 无残留')
    ok(q("SELECT COUNT(*) FROM team_members WHERE name LIKE '%" + P + "%'") == 0, 'team_members 无残留')
    ok(q("SELECT COUNT(*) FROM boards WHERE board_id LIKE '%" + P + "%'") == 0, 'boards/board_config 无残留')
    ok(q("SELECT COUNT(*) FROM org_nodes WHERE name LIKE '%" + P + "%'") == 0, 'org_nodes 无残留')
    c.close()
    print(f'\n===== 结果：PASS {PASS} / FAIL {FAIL} =====')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
