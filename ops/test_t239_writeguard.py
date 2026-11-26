# -*- coding: utf-8 -*-
"""T-239 综合追加人员写权限护栏验证（API）：
夹具：U=纯追加成员（无原生身份）；U2=板块负责人（原生身份）+ 也被追加。
【U 视角（综合模式 syn_depts）】
① 白名单板块可见  ② 评论允许  ③ 每周进展 403  ④ 新增事项 403  ⑤ 修改事项 403
⑥ 删除事项 403  ⑦ 新增待办 403  ⑧ 勾选待办 403  ⑨ 复制到该看板 403  ⑩ 移动 403
【U2 视角（原生身份）】⑪ 评论正常 ⑫ 每周进展正常（不降级）⑬ 修改事项正常
【非综合模式】⑭ U 不带 syn_depts → 看板不可见
收尾快照恢复 + 夹具零残留。"""
import json, os, sqlite3, sys, urllib.error, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
NID = 4
BOARD = 'BCP1793717004248'
TK = make_token('admin')
U = '__t239_u1'     # 纯追加成员（无原生身份）
U2 = '__t239_u2'    # 板块负责人（原生身份）+ 也被追加

OK = []
def ok(cond, label):
    OK.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + label)

def api(path, method='GET', body=None, tk=None, syn=False):
    # syn=True：模拟综合模式（真实前端在综合模式下对所有 /api 请求自动附带 syn_depts）
    if syn and 'syn_depts=' not in path and '?' in path:
        path += '&syn_depts=%d' % NID
    elif syn and 'syn_depts=' not in path:
        path += '?syn_depts=%d' % NID
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (tk or TK))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            if 'json' in r.headers.get('Content-Type', ''):
                return r.status, json.loads(r.read().decode())
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def db_rows(q, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows

def snap():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    s = {
        'scheme': [dict(r) for r in conn.execute('SELECT * FROM syn_scheme WHERE dept_node_id=?', (NID,))],
        'bcfg': [dict(r) for r in conn.execute('SELECT * FROM syn_board_config WHERE dept_node_id=?', (NID,))],
        'member': [dict(r) for r in conn.execute('SELECT * FROM syn_config_member WHERE dept_node_id=?', (NID,))],
        'smem': [dict(r) for r in conn.execute('SELECT * FROM syn_scheme_member WHERE dept_node_id=?', (NID,))],
        'invite': [dict(r) for r in conn.execute('SELECT * FROM syn_config_invite WHERE dept_node_id=?', (NID,))],
    }
    conn.close()
    return s

def restore(s):
    conn = sqlite3.connect(DB)
    for t in ('syn_scheme_member', 'syn_config_invite', 'syn_config_member', 'syn_scheme'):
        conn.execute('DELETE FROM %s WHERE dept_node_id=?' % t, (NID,))
    for r in s['scheme']:
        conn.execute('INSERT INTO syn_scheme (id,dept_node_id,owner,name,columns,extra_members,is_display,updated_at) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['owner'], r['name'], r['columns'],
                      r['extra_members'], r['is_display'], r['updated_at']))
    for r in s['member']:
        conn.execute('INSERT INTO syn_config_member (id,dept_node_id,member,owner) VALUES (?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['member'], r['owner']))
    for r in s['invite']:
        conn.execute('INSERT INTO syn_config_invite (id,dept_node_id,member,owner,status,created_at,decided_at,scheme_id) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['member'], r['owner'], r['status'],
                      r['created_at'], r['decided_at'], r['scheme_id']))
    for r in s['smem']:
        conn.execute('INSERT INTO syn_scheme_member (dept_node_id,username,scheme_id,status,updated_at) '
                     'VALUES (?,?,?,?,?)', (r['dept_node_id'], r['username'], r['scheme_id'],
                                            r['status'], r['updated_at']))
    conn.commit(); conn.close()

def cleanup():
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM syn_scheme_member WHERE username LIKE '%t239%'")
    conn.execute("DELETE FROM syn_config_invite WHERE member LIKE '%t239%' OR owner LIKE '%t239%'")
    conn.execute("DELETE FROM syn_config_member WHERE member LIKE '%t239%' OR owner LIKE '%t239%'")
    conn.execute("DELETE FROM syn_scheme WHERE owner LIKE '%t239%'")
    conn.execute("DELETE FROM messages WHERE receiver LIKE '%t239%' OR sender LIKE '%t239%'"
                 " OR (kind='system' AND content LIKE '%追加邀请%')")
    conn.execute("DELETE FROM card_week_progress WHERE card_id IN (SELECT card_id FROM cards WHERE card_name LIKE '%t239%')")
    conn.execute("DELETE FROM comments WHERE card_id IN (SELECT card_id FROM cards WHERE card_name LIKE '%t239%')")
    conn.execute("DELETE FROM card_subtasks WHERE card_id IN (SELECT card_id FROM cards WHERE card_name LIKE '%t239%')")
    conn.execute("DELETE FROM cards WHERE card_name LIKE '%t239%'")
    conn.execute("DELETE FROM board_columns WHERE column_name LIKE '%t239%'")
    conn.execute("DELETE FROM users WHERE username LIKE '%t239%'")
    conn.commit(); conn.close()

def main():
    S = snap()
    try:
        # 夹具：用户 + 板块（owner=U2，原生身份）+ 卡（owner=U2）
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U, hash_pw('Xx123456')))
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U2, hash_pw('Xx123456')))
        conn.commit(); conn.close()
        tk_u = make_token(U)      # ⚠️ token 绑定 active_seq —— 用户落库后签发
        tk_u2 = make_token(U2)

        st, dcol = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t239_板块',
                                                'nature': '日常', 'year': '2026', 'owner': U2,
                                                'created_at': '2026-11-26'})
        assert st in (200, 201), '板块创建失败: %s %s' % (st, dcol)
        col_key = BOARD + '::__t239_板块'
        col_row = db_rows("SELECT column_id FROM board_columns WHERE col_key=?", (col_key,))
        col_id = col_row[0]['column_id'] if col_row else ''
        st, dcard = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t239_卡',
                                               'fields': {'column_name': '__t239_板块', 'column_id': col_id,
                                                          'owner': U2, 'begin': '2026-11-23', 'due': '2026-11-29'}})
        assert st in (200, 201), '卡创建失败: %s %s' % (dcard)
        card_id = dcard['card_id']

        # 方案：白名单 = 夹具板块；U/U2 均被追加 → 接受
        st, d1 = api('/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': 'T239方案', 'columns': col_key, 'extra_members': U + ',' + U2},
        ], 'display_index': 0})
        assert st == 200, '方案保存失败: %s %s' % (st, d1)
        for tkx, who in ((tk_u, U), (tk_u2, U2)):
            st, dinv = api('/api/syn-invites', tk=tkx)
            invs = [x for x in (dinv.get('invites') or []) if x['owner'] == 'admin']
            assert invs, who + ' 未收到邀请'
            api('/api/syn-invites/%d/decide' % invs[0]['id'], 'POST', {'accept': True}, tk=tkx)
            # #129b 接受≠适用：勾选全部方案并确定（模拟弹窗操作），恢复"已适用"前提
            _, dmy = api('/api/syn-my-schemes?dept_node_id=%d' % NID, tk=tkx)
            ids = [s['id'] for s in (dmy.get('schemes') or [])]
            api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': ids}, tk=tkx)

        SYN = 'syn_depts=%d' % NID
        # ── U 视角（纯追加，无原生身份）──
        st, d = api('/api/cards?board_id=%s&size=100' % BOARD, tk=tk_u, syn=True)
        names = [c['card_name'] for c in (d.get('cards') or [])]
        ok('__t239_卡' in names, '① 白名单板块内容可见')
        st, d2 = api('/api/cards/%s/comments' % card_id, 'POST', {'content': '追加人员可以评论'}, tk=tk_u, syn=True)
        ok(st in (200, 201), '② 评论允许（HTTP %s）' % st)
        st, d3 = api('/api/cards/%s/week-progress' % card_id, 'POST',
                     {'items': {'2026年第48周': 'x'}}, tk=tk_u, syn=True)
        ok(st == 403, '③ 每周进展 → 403（HTTP %s）' % st)
        st, d4 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t239_越权新建',
                                            'fields': {'column_name': '__t239_板块', 'column_id': col_id}}, tk=tk_u, syn=True)
        ok(st == 403, '④ 新增事项 → 403（HTTP %s）' % st)
        st, d5 = api('/api/cards/%s' % card_id, 'PUT',
                     {'fields': {'description': '越权修改'}}, tk=tk_u, syn=True)
        ok(st == 403, '⑤ 修改事项 → 403（HTTP %s）' % st)
        st, d6 = api('/api/cards/%s' % card_id, 'DELETE', tk=tk_u, syn=True)
        ok(st == 403, '⑥ 删除事项 → 403（HTTP %s）' % st)
        st, d7 = api('/api/cards/%s/subtasks' % card_id, 'POST', {'title': '越权待办'}, tk=tk_u, syn=True)
        ok(st == 403, '⑦ 新增待办 → 403（HTTP %s）' % st)
        st, dtmp = api('/api/cards/%s/subtasks' % card_id, 'POST', {'title': '占位待办'})
        sid0 = (db_rows('SELECT id FROM card_subtasks WHERE card_id=? ORDER BY id DESC LIMIT 1', (card_id,)) or [{}])[0].get('id')
        st, d8 = api('/api/cards/%s/subtasks/%s' % (card_id, sid0), 'PUT',
                     {'done': 1, 'title': '占位待办'}, tk=tk_u, syn=True)
        ok(st == 403, '⑧ 勾选/修改待办 → 403（HTTP %s）' % st)
        st, d9 = api('/api/cards/copy', 'POST', {'card_id': card_id, 'board_id': BOARD,
                                                 'column_id': col_id, 'column_name': '__t239_板块'}, tk=tk_u, syn=True)
        ok(st == 403, '⑨ 复制事项到该看板 → 403（HTTP %s）' % st)
        st, d10 = api('/api/cards/%s/move' % card_id, 'PUT',
                      {'board_id': BOARD, 'column_id': col_id, 'column_name': '__t239_板块'}, tk=tk_u, syn=True)
        ok(st == 403, '⑩ 移动事项 → 403（HTTP %s）' % st)

        # ── U2 视角（原生身份 = 板块负责人 + 也被追加 → 原有权限不受影响）──
        st, d11 = api('/api/cards/%s/comments' % card_id, 'POST', {'content': '负责人评论'}, tk=tk_u2, syn=True)
        ok(st in (200, 201), '⑪ U2 评论正常（HTTP %s）' % st)
        st, d12 = api('/api/cards/%s/week-progress' % card_id, 'POST',
                      {'items': {'2026年第48周': '负责人进展'}}, tk=tk_u2, syn=True)
        ok(st in (200, 201), '⑫ U2 每周进展正常（原生身份不降级，HTTP %s）' % st)
        st, d13 = api('/api/cards/%s' % card_id, 'PUT',
                      {'fields': {'description': '负责人修改'}}, tk=tk_u2, syn=True)
        ok(st == 200, '⑬ U2 修改事项正常（HTTP %s）' % st)

        # ── ⑭ 非综合模式：U 不带 syn_depts → 白名单看板内容不可见 ──
        st, d14 = api('/api/cards?board_id=%s&size=100' % BOARD, tk=tk_u)
        names14 = [c['card_name'] for c in (d14.get('cards') or [])]
        ok('__t239_卡' not in names14, '⑭ 非综合模式 U 不可见该看板内容（%s）' % names14[:3])
    finally:
        cleanup()
        restore(S)
        conn = sqlite3.connect(DB)
        left = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t239%'").fetchone()[0]
        left2 = conn.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE '%t239%'").fetchone()[0]
        conn.close()
        ok(left == 0 and left2 == 0, '清理 夹具零残留（users=%s cards=%s）' % (left, left2))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

main()
