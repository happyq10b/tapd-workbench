# -*- coding: utf-8 -*-
"""T-0188：板块评论/待办端点 + 板块截止日期（倒计时）API 测试。
覆盖：评论可见即可评/越权 403；待办增删改/编辑权/锁互斥 409；
     截止日期落库回读/改名随迁评论待办/删除板块级联清空。
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse, urllib.error

ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = ROOT + '/src/app.db'
P = '__cdm_'
BID, U1, U2, U3 = P + 'bid', P + 'u1', P + 'u2', P + 'u3'
COLKEY = BID + '::' + P + '板块'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'), data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def setup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    for u in (U1, U2, U3):
        c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) VALUES(?,?,?,?,1)",
                  (u, hash_pw('Xx12345678'), 'x', 'editor'))
    # U1 = 看板负责人；U2 在 allowed_boards（可见）；U3 完全不可见
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', U1, U2))
    c.execute("UPDATE users SET allowed_boards=? WHERE username=?", (BID, U2))
    c.execute("UPDATE users SET allowed_boards='__none_zz' WHERE username=?", (U3,))
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,owner,participants)"
              " VALUES(?,?,?,?,?,?,?,?,?,?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026', '', ''))
    c.commit()
    c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM column_comments WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM column_todos WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM cards WHERE board_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.commit()
    c.close()


def main():
    t0, t1, t2, t3 = make_token('admin'), make_token(U1), make_token(U2), make_token(U3)
    print('① 板块评论：可见即可评 / 越权 403')
    s, r = call('POST', '/api/columns/comments', t2, {'col_key': COLKEY, 'content': '  测试评论甲  '})
    ok(s == 200, f'看板参与人发评论 → 200（实际 {s} {r}）')
    s, r = call('GET', '/api/columns/comments?col_key=' + urllib.parse.quote(COLKEY), t2)
    ok(s == 200 and len(r.get('comments', [])) == 1 and r['comments'][0]['content'] == '测试评论甲'
       and r['comments'][0]['username'] == U2,
       f'评论列表含内容（trim 后入库）与作者（实际 {s} {r}）')
    s, r = call('POST', '/api/columns/comments', t3, {'col_key': COLKEY, 'content': '越权'})
    ok(s == 403, f'不可见用户发评论 → 403（实际 {s}）')
    s, r = call('POST', '/api/columns/comments', t2, {'col_key': COLKEY, 'content': '   '})
    ok(s == 400, '空评论 → 400')
    s, r = call('GET', '/api/columns/comments?col_key=' + urllib.parse.quote(COLKEY), t3)
    ok(s == 403, '不可见用户读评论 → 403')

    print('② 板块待办：编辑身份可见即可改 + 锁互斥（与事项子事项同口径）')
    s, r = call('POST', '/api/columns/todos', t2, {'col_key': COLKEY, 'name': '待办零'})
    ok(s == 200, f'看板参与人（editor + 可见）加待办 → 200（实际 {s} {r}）')
    s, r = call('POST', '/api/columns/todos', t3, {'col_key': COLKEY, 'name': '越权待办'})
    ok(s == 403, f'不可见用户加待办 → 403（实际 {s}）')
    s, r = call('POST', '/api/columns/todos', t1, {'col_key': COLKEY, 'name': '待办一'})
    ok(s == 200, f'看板负责人加待办 → 200（实际 {s} {r}）')
    s, r = call('POST', '/api/columns/todos', t1, {'col_key': COLKEY, 'name': '待办二'})
    ok(s == 200, '加第二条待办 → 200')
    s, r = call('GET', '/api/columns/todos?col_key=' + urllib.parse.quote(COLKEY), t2)
    todos = r.get('todos', [])
    ok(s == 200 and len(todos) == 3, f'待办列表 3 条（实际 {s} {len(todos)}）')
    tid = todos[0]['id'] if todos else 0
    s, r = call('PUT', f'/api/columns/todos/{tid}', t1, {'done': True})
    ok(s == 200, f'勾选待办 → 200（实际 {s} {r}）')
    s, r = call('GET', '/api/columns/todos?col_key=' + urllib.parse.quote(COLKEY), t2)
    done_flag = [x for x in r.get('todos', []) if x['id'] == tid]
    ok(done_flag and done_flag[0]['done'] == 1, '勾选状态已落库')
    # 锁互斥：T2 持有板块编辑锁 → T1 改待办 409
    call('POST', '/api/locks/acquire', t2, {'key': 'column:' + COLKEY})
    s, r = call('PUT', f'/api/columns/todos/{tid}', t1, {'done': False})
    ok(s == 409, f'板块被他人锁定时改待办 → 409（实际 {s} {r}）')
    s, r = call('PUT', f'/api/columns/todos/{tid}', t2, {'done': False})
    ok(s == 200, f'持锁人本人改待办 → 200（实际 {s}）')
    call('POST', '/api/locks/release', t2, {'key': 'column:' + COLKEY})
    s, r = call('DELETE', f'/api/columns/todos/{tid}', t1)
    ok(s == 200, f'删除待办 → 200（实际 {s}）')

    print('③ 板块截止日期（倒计时数据源）')
    s, r = call('PUT', '/api/columns', t0, {'col_key': COLKEY, 'board_id': BID, 'column_name': P + '板块',
                                            'created_at': '2026-11-12', 'year': '2026', 'due_date': '2026-12-31'})
    ok(s == 200, f'设置板块截止日期 → 200（实际 {s} {r}）')
    s, r = call('GET', '/api/boards/' + BID + '/columns', t1)
    meta = [c for c in r.get('columns', []) if c['col_key'] == COLKEY]
    ok(meta and meta[0].get('due_date') == '2026-12-31', f'板块清单下发 due_date（实际 {meta and meta[0].get("due_date")}）')
    s, r = call('PUT', '/api/columns', t0, {'col_key': COLKEY, 'board_id': BID, 'column_name': P + '板块',
                                            'created_at': '2026-11-12', 'year': '2026', 'due_date': 'bad-date'})
    ok(s == 400, '非法日期格式 → 400')
    s, r = call('PUT', '/api/columns', t0, {'col_key': COLKEY, 'board_id': BID, 'column_name': P + '板块',
                                            'created_at': '2026-11-12', 'year': '2026', 'due_date': ''})
    ok(s == 200, '清空截止日期 → 200')

    print('④ 改名随迁 + 删除级联')
    call('POST', '/api/columns/comments', t1, {'col_key': COLKEY, 'content': '随迁测试'})
    call('POST', '/api/columns/todos', t1, {'col_key': COLKEY, 'name': '随迁待办'})
    NEWKEY = BID + '::' + P + '板块改'
    s, r = call('PUT', '/api/columns', t0, {'col_key': COLKEY, 'board_id': BID, 'column_name': P + '板块改',
                                            'created_at': '2026-11-12', 'year': '2026'})
    ok(s == 200, f'板块改名 → 200（实际 {s} {r}）')
    c = sqlite3.connect(DB)
    nc = c.execute("SELECT COUNT(*) FROM column_comments WHERE col_key=?", (NEWKEY,)).fetchone()[0]
    nt = c.execute("SELECT COUNT(*) FROM column_todos WHERE col_key=?", (NEWKEY,)).fetchone()[0]
    oc = c.execute("SELECT COUNT(*) FROM column_comments WHERE col_key=?", (COLKEY,)).fetchone()[0]
    c.close()
    ok(nc == 2 and nt == 3 and oc == 0, f'评论/待办随新 col_key（评论 {nc}/待办 {nt}/旧 key 残留 {oc}）')
    s, r = call('DELETE', '/api/columns/' + urllib.parse.quote(NEWKEY), t0)
    ok(s == 200, f'删除板块 → 200（实际 {s} {r}）')
    c = sqlite3.connect(DB)
    nc = c.execute("SELECT COUNT(*) FROM column_comments WHERE col_key=?", (NEWKEY,)).fetchone()[0]
    nt = c.execute("SELECT COUNT(*) FROM column_todos WHERE col_key=?", (NEWKEY,)).fetchone()[0]
    c.close()
    ok(nc == 0 and nt == 0, f'删除板块级联清空评论/待办（评论 {nc}/待办 {nt}）')

    print('⑤ 夹具残留自查（清理后）')


if __name__ == '__main__':
    try:
        cleanup()
        setup()
        main()
    finally:
        cleanup()
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    sys.exit(1 if fails else 0)
