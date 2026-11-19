# -*- coding: utf-8 -*-
"""T-013d 协作部门 API 测试：配置校验 / 负责人可见授权 / 名单不显示 / 可见即可评论"""
import json, os, sqlite3, sys, urllib.parse, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
RES = []


def ok(cond, msg):
    RES.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    path = urllib.parse.quote(path, safe='/?&=')
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk,
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


BOARD, CARD, ACC, MNAME = '__t_cb_board', '__t_cb_card', '__t_cb_u', '__t_协作部门成员__'
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA busy_timeout=5000')
center = c.execute("SELECT id FROM org_nodes WHERE node_type='center' ORDER BY id LIMIT 1").fetchone()[0]
# 专用夹具部门（避免与真实部门的负责人唯一约束冲突）
c.execute("INSERT INTO org_nodes (name,parent_id,node_type) VALUES ('__t_cb_dept',?,'dept')", (center,))
D1 = c.execute("SELECT id FROM org_nodes WHERE name='__t_cb_dept'").fetchone()[0]
D2 = c.execute("SELECT id FROM org_nodes WHERE node_type='dept' AND parent_id=? AND id!=? ORDER BY id LIMIT 1", (center, D1)).fetchone()[0]
c.execute("INSERT OR IGNORE INTO boards (board_id,board_name,sort,created_at) VALUES (?,?,0,datetime('now'))", (BOARD, BOARD))
c.execute("INSERT OR REPLACE INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id) "
          "VALUES (?,'__t_cb_board','__t_cb_board','__t_cb_col','__t_协作测试事项','open','','',datetime('now'),0,'')", (CARD,))
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (ACC, hash_pw('Xx12345678')))
c.execute("INSERT OR IGNORE INTO team_members (id,name,account) VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),?,?)", (MNAME, ACC))
MID = c.execute('SELECT id FROM team_members WHERE account=?', (ACC,)).fetchone()[0]
c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?, 'dept_head',1)", (D1, MID))
c.execute("INSERT OR REPLACE INTO board_config (board_id,dept,dept_node_id,attr,status,remark,collab_depts) "
          "VALUES (?,'财务中心',?,'日常','启用','','')", (BOARD, center))
c.commit(); c.close()
CID = None

try:
    tk_admin = make_token('admin')
    tk_u = make_token(ACC)

    print('【① 授权前：协作部门负责人不可见该看板】', flush=True)
    st, d = api(tk_u, 'GET', '/api/boards')
    ok(BOARD not in [b['board_id'] for b in d.get('boards', [])], '未配置协作 → 看板不可见')

    print('【② 更新配置启用协作部门（含非法 id 自动剔除）】', flush=True)
    _c2 = sqlite3.connect(DB); CID = _c2.execute("SELECT id FROM board_config WHERE board_id=?", (BOARD,)).fetchone()[0]; _c2.close()
    st, d = api(tk_admin, 'PUT', '/api/board-config/%d' % CID,
                {'board_id': BOARD, 'dept': '财务中心', 'dept_node_id': center, 'attr': '日常', 'status': '启用',
                 'collab_depts': [str(D1), str(D2), '999999']})
    ok(st == 200, '配置更新成功')
    st, d = api(tk_admin, 'GET', '/api/board-config')
    cfg = next((x for x in d['items'] if x['board_id'] == BOARD), {})
    CID = cfg.get('id')
    got = sorted([int(x) for x in (cfg.get('collab_depts') or '').split(',') if x])
    ok(got == sorted([D1, D2]), '非法 id 被剔除，合法协作部门落库：%s' % got)

    print('【③ 授权后：协作部门负责人可见（看板/板块/事项），不进参与人名单】', flush=True)
    st, d = api(tk_u, 'GET', '/api/boards')
    ok(BOARD in [b['board_id'] for b in d.get('boards', [])], '看板可见')
    st, d = api(tk_u, 'GET', '/api/cards?board_ids=' + BOARD)
    ok(d.get('total', 0) == 1, '事项可见（%s 条）' % d.get('total'))
    st, d = api(tk_admin, 'GET', '/api/boards')
    b = next((x for x in d['boards'] if x['board_id'] == BOARD), {})
    parts = (b.get('participants') or '')
    ok(ACC not in parts, '参与人名单不含协作负责人（纯可见）：%r' % parts)

    print('【④ 可见即可评论：viewer 角色的协作负责人可发评论】', flush=True)
    st, d = api(tk_u, 'POST', '/api/cards/%s/comments' % CARD, {'content': '__t_协作评论__', 'mentions': []})
    ok(st == 200, '评论成功（viewer + 仅可见身份）')
    st, d = api(tk_admin, 'GET', '/api/cards/%s/comments' % CARD)
    ok(any(c['content'] == '__t_协作评论__' for c in d.get('comments', [])), '评论已落库')

    print('【⑤ 非中心归属 → 协作部门强制清空】', flush=True)
    d2name = c2 = None
    import sqlite3 as _s
    _c = _s.connect(DB); d2name = _c.execute('SELECT name FROM org_nodes WHERE id=?', (D2,)).fetchone()[0]; _c.close()
    st, d = api(tk_admin, 'PUT', '/api/board-config/%d' % CID,
                {'dept': d2name, 'dept_node_id': D2, 'attr': '日常', 'status': '启用',
                 'collab_depts': [str(D1)]})
    ok(st == 200, '保存成功')
    st, d = api(tk_admin, 'GET', '/api/board-config')
    cfg = next((x for x in d['items'] if x['board_id'] == BOARD), {})
    ok((cfg.get('collab_depts') or '') == '', '非中心归属 → 协作部门清空')

    print('【⑥ 授权随之收回：改回中心归属但清空协作 → 不可见】', flush=True)
    api(tk_admin, 'PUT', '/api/board-config/%d' % CID,
        {'dept': '财务中心', 'dept_node_id': center, 'attr': '日常', 'status': '启用', 'collab_depts': []})
    st, d = api(tk_u, 'GET', '/api/boards')
    ok(BOARD not in [b['board_id'] for b in d.get('boards', [])], '协作清空 → 看板不再可见')

finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    if CID:
        c.execute('DELETE FROM board_config WHERE id=?', (CID,))
    else:
        c.execute("DELETE FROM board_config WHERE board_id=?", (BOARD,))
    c.execute("DELETE FROM comments WHERE content='__t_协作评论__'")
    c.execute("DELETE FROM cards WHERE card_id=?", (CARD,))
    c.execute("DELETE FROM boards WHERE board_id=?", (BOARD,))
    c.execute("DELETE FROM org_appointments WHERE member_id=?", (MID,))
    c.execute("DELETE FROM org_nodes WHERE name='__t_cb_dept'")
    c.execute("DELETE FROM team_members WHERE account=?", (ACC,))
    c.execute("DELETE FROM users WHERE username=?", (ACC,))
    c.commit()
    n = [c.execute(sql, (k,)).fetchone()[0] for sql, k in (
        ("SELECT COUNT(*) FROM board_config WHERE board_id=?", BOARD),
        ("SELECT COUNT(*) FROM team_members WHERE account=?", ACC),
        ("SELECT COUNT(*) FROM users WHERE username=?", ACC),
        ("SELECT COUNT(*) FROM cards WHERE card_id=?", CARD),
        ("SELECT COUNT(*) FROM org_nodes WHERE name=?", '__t_cb_dept'))]
    print('夹具残留检查: config=%d members=%d users=%d cards=%d nodes=%d' % tuple(n), flush=True)
    c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
