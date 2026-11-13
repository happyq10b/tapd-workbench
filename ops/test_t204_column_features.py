# -*- coding: utf-8 -*-
"""T-204（2026-11-13）板块功能增强 —— 后端 API 实测：
  ① 板块评论 @ 提及（候选池 / 池外拒绝 / 消息投递 / mentions 落库）
  ② 板块操作记录（column_actions 流水 + GET /api/columns/actions）
  ③ 板块待办权限（板块负责人及以上可追加；参与人 403；管理员放行）
  ④ _mention_pool_names 重构等价性（card 版 == board 版）

夹具纪律：__t204_ 前缀命名空间；try/finally 清理；结束跑零残留自查。
夹具不整造看板 —— 挂在真实看板下（仅新增一个 __t204 前缀板块，测完 API 删除）。
"""
import os, sqlite3, sys, urllib.request, urllib.parse, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ---------- 夹具 ----------
# 夹具看板：不挂 board_config（dept_node_id 缺省）→ 公共看板，全员可见 ——
# 这样 u1（板块参与人）/ u2（板块负责人）无需架构归属即可获得看板级可见性，
# 板块级可见性再由板块 ACL（participants / owner）精确控制。
conn.execute("INSERT INTO boards (board_id, board_name, sort) VALUES ('__t204_B1','__t204 测试看板',9200)")
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t204_u1',?,'user')", (hash_pw('Xx12345678'),))
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t204_u2',?,'user')", (hash_pw('Xx12345678'),))
conn.commit()
conn.close()

TK_ADMIN = make_token('admin')
TK_U1 = make_token('__t204_u1')     # 板块参与人（可见、非负责人 → 待办 403 预期）
TK_U2 = make_token('__t204_u2')     # 板块负责人（待办 200 预期）

_bid = '__t204_B1'

COL_KEY = _bid + '::__t204板块'
CLEANED = {'col': False}


def cleanup():
    # ① 板块本体（API 删除 = 走真实级联路径；失败则直删兜底）
    if not CLEANED['col']:
        try:
            api('/api/columns/' + urllib.parse.quote(COL_KEY, safe=''), 'DELETE', token=TK_ADMIN)
        except Exception:
            pass
        CLEANED['col'] = True
    c = sqlite3.connect(DB)
    # ② 看板 / 账号 / 成员 / 消息残留（兜底直删）
    c.execute("DELETE FROM column_comments WHERE col_key LIKE '%__t204板块%'")
    c.execute("DELETE FROM column_todos WHERE col_key LIKE '%__t204板块%'")
    c.execute("DELETE FROM column_actions WHERE col_key LIKE '%__t204板块%'")
    c.execute("DELETE FROM board_columns WHERE col_key LIKE '%__t204板块%'")
    c.execute("DELETE FROM board_config WHERE board_id LIKE '__t204_%'")
    c.execute("DELETE FROM boards WHERE board_id LIKE '__t204_%'")
    c.execute("DELETE FROM messages WHERE receiver LIKE '__t204_%' OR content LIKE '%__t204板块%'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t204_%' OR account LIKE '__t204_%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t204_%'")
    c.commit()
    c.close()


def residue_check():
    c = sqlite3.connect(DB)
    pairs = [
        ("users", "username LIKE '__t204_%'"),
        ("team_members", "name LIKE '__t204_%' OR account LIKE '__t204_%'"),
        ("boards", "board_id LIKE '__t204_%'"),
        ("board_config", "board_id LIKE '__t204_%'"),
        ("board_columns", "col_key LIKE '%__t204板块%'"),
        ("column_comments", "col_key LIKE '%__t204板块%'"),
        ("column_todos", "col_key LIKE '%__t204板块%'"),
        ("column_actions", "col_key LIKE '%__t204板块%'"),
        ("messages", "receiver LIKE '__t204_%' OR content LIKE '%__t204板块%'"),
    ]
    bad = []
    for t, w in pairs:
        n = c.execute(f'SELECT COUNT(*) FROM {t} WHERE {w}').fetchone()[0]
        if n:
            bad.append(f'{t}={n}')
    c.close()
    return bad


def main():
    # ---------- ① 建板块（真实 PUT 路径，u2=负责人、u1=参与人） ----------
    st, r = api('/api/columns', 'PUT', {
        'col_key': '', 'board_id': _bid, 'column_name': '__t204板块',
        'created_at': '2026-11-13', 'year': '2026', 'nature': '日常',
        'owner': '__t204_u2', 'participants': '__t204_u1', 'description': ''}, TK_ADMIN)
    ok(st == 200, f'① PUT /api/columns 创建夹具板块 → {st}')
    key = r.get('col_key') or COL_KEY

    # ---------- ② 板块评论 ----------
    st, r = api('/api/columns/mention_pool?col_key=' + urllib.parse.quote(key, safe=''), token=TK_ADMIN)
    pool_admin = (r or {}).get('names') or []
    ok(st == 200 and isinstance(pool_admin, list), f'② GET mention_pool(admin) → {st}, {len(pool_admin)} 人')

    st, r = api('/api/columns/mention_pool?col_key=' + urllib.parse.quote(key, safe=''), token=TK_U1)
    ok(st == 200 and isinstance((r or {}).get('names'), list), f'② GET mention_pool(参与人) → {st}（可见即可评口径）')

    # 池外成员拒绝被 @（防直调 API）
    st, r = api('/api/columns/comments', 'POST',
                {'col_key': key, 'content': '提及池外成员', 'mentions': ['不存在的成员']}, TK_ADMIN)
    ok(st == 403, f'② POST 评论 @池外成员 → {st}（预期 403）')

    # 普通评论（无提及）
    st, r = api('/api/columns/comments', 'POST', {'col_key': key, 'content': '第一条板块评论'}, TK_U1)
    ok(st == 200, f'② POST 评论（参与人，无提及）→ {st}（可见即可评）')

    # 带提及评论：提及对象取自真实候选池（池非空才做，否则登记跳过）
    if pool_admin:
        target = pool_admin[0]
        st, r = api('/api/columns/comments', 'POST',
                    {'col_key': key, 'content': '带提及评论', 'mentions': [target]}, TK_ADMIN)
        ok(st == 200, f'② POST 评论 @「{target}」→ {st}')
        c = sqlite3.connect(DB)
        row = c.execute('SELECT mentions FROM column_comments WHERE col_key=? AND content=?',
                        (key, '带提及评论')).fetchone()
        ok(row is not None and target in (row[0] or ''), '② mentions 落库（分号分隔姓名）')
        recv = c.execute('SELECT account FROM team_members WHERE name=?', (target,)).fetchone()
        if recv and (recv[0] or '').strip():
            m = c.execute('SELECT COUNT(*) FROM messages WHERE receiver=? AND kind=? AND content LIKE ?',
                          (recv[0].strip(), 'mention', '%__t204板块%')).fetchone()[0]
            ok(m >= 1, f'② 提及消息已投递给 {recv[0].strip()}（{m} 条）')
        else:
            print('SKIP ② 消息投递（提及对象未绑定登录账号）', flush=True)
        c.close()
    else:
        print('SKIP ② 提及接受路径（该看板候选池为空）', flush=True)

    # 评论列表：升序 + mentions 字段返回
    st, r = api('/api/columns/comments?col_key=' + urllib.parse.quote(key, safe=''), token=TK_U1)
    cs = (r or {}).get('comments') or []
    ok(st == 200 and len(cs) >= 2 and cs[0]['content'] == '第一条板块评论',
       f'② GET 评论列表 → {st}，{len(cs)} 条，升序')
    ok('mentions' in cs[0], '② 评论行带 mentions 字段')

    # ---------- ③ 板块操作记录 ----------
    st, r = api('/api/columns/actions?col_key=' + urllib.parse.quote(key, safe=''), token=TK_U1)
    acts = (r or {}).get('actions') or []
    kinds = [a['action'] for a in acts]
    ok(st == 200, f'③ GET /api/columns/actions → {st}（可见即可查）')
    ok('create' in kinds, f'③ 含 create（实际：{kinds}）')
    ok('comment' in kinds, '③ 含 comment')

    # ---------- ④ 板块待办权限 ----------
    st, r = api('/api/columns/todos', 'POST', {'col_key': key, 'name': '__t204 待办甲'}, TK_U1)
    ok(st == 403, f'④ 参与人加板块待办 → {st}（预期 403）')
    st, r = api('/api/columns/todos', 'POST', {'col_key': key, 'name': '__t204 待办乙'}, TK_U2)
    ok(st == 200, f'④ 板块负责人加板块待办 → {st}（预期 200）')
    st, r = api('/api/columns/todos', 'POST', {'col_key': key, 'name': '__t204 待办丙'}, TK_ADMIN)
    ok(st == 200, f'④ 管理员加板块待办 → {st}（预期 200）')
    st, r = api('/api/columns/actions?col_key=' + urllib.parse.quote(key, safe=''), token=TK_ADMIN)
    kinds2 = [a['action'] for a in ((r or {}).get('actions') or [])]
    ok('todo_add' in kinds2, f'④ 操作记录含 todo_add（实际：{kinds2}）')
    st, todos = api('/api/columns/todos?col_key=' + urllib.parse.quote(key, safe=''), token=TK_U2)
    tids = [t['id'] for t in (todos or {}).get('todos') or []]
    ok(st == 200 and len(tids) == 2, f'④ 待办清单 = 2 条（实际 {len(tids)}）')
    if tids:
        st, _ = api('/api/columns/todos/%d' % tids[0], 'PUT', {'done': True}, TK_U2)
        ok(st == 200, '④ 勾选待办（负责人）→ 200')
        st, _ = api('/api/columns/todos/%d' % tids[0], 'DELETE', None, TK_U2)
        ok(st == 200, '④ 删除待办（负责人）→ 200')

    # ---------- ⑤ _mention_pool_names 重构等价性（真实卡片） ----------
    try:
        from app.app import _mention_pool_names, _mention_pool_names_for_board, dbq
        card = dbq('SELECT card_id, board_id FROM cards WHERE deleted=0 LIMIT 1')
        if card:
            a = _mention_pool_names(card[0]['card_id'], 'admin')
            b = _mention_pool_names_for_board(card[0]['board_id'], 'admin')
            ok(a == b, f'⑤ 候选池重构等价（card 版 == board 版，{len(a)} 人）')
        else:
            print('SKIP ⑤（库中无事项）', flush=True)
    except Exception as e:
        ok(False, f'⑤ 等价性检查异常：{e}')

    # ---------- 清理 + 零残留自查 ----------
    cleanup()
    bad = residue_check()
    ok(not bad, '零残留自查（__t204_ 前缀无残留）' + ('' if not bad else ' → ' + '、'.join(bad)))

    n_pass = sum(1 for x in PASSED if x)
    print(f'\n=== {n_pass}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if n_pass == len(PASSED) else 1)


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            cleanup()
            bad = residue_check()
            print('finally 清理完成，残留：', bad or '无', flush=True)
        except Exception as e:
            print('finally 清理异常：', e, flush=True)
