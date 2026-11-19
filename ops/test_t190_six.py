# -*- coding: utf-8 -*-
"""T-0190 六项调整测试：
① 偏好备份仅手动触发（回滚不自动备份）；
② 板块编辑弹窗删除按钮（板块负责人及以上可见，后端 LV_COLUMN_OWNER 同口径）；
③ 板块待办设置入口只在编辑弹窗（浏览只展示/勾选，不显示创建人）；
④ 板块行【待办：x/y】计数；
⑤ 子事项列与父事项对齐（CSS 同步断言）；
⑥ 倒计时只显示数字、逾期负数（JS 静态断言）。
"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request

ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
BASE = 'http://127.0.0.1:8100'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

P = '__t190_'
BID, U1, U2, U3 = P + 'bid', P + 'u1', P + 'u2', P + 'u3'
COLKEY = BID + '::' + P + '板块'
N = []

def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'), data=data,
        method=method, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}

def setup():
    c = sqlite3.connect(DB, timeout=15); c.execute('PRAGMA busy_timeout=15000')
    for u in (U1, U2, U3):
        c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) VALUES(?,?,?,?,1)",
                  (u, hash_pw('x'), 'x', 'editor'))
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)", (BID, P+'看板', U1, ''))
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,owner,participants,due_date) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (COLKEY, P+'cid', BID, P+'板块', '2026-11-12', 'admin', '日常', '2026', U2, '', '2099-01-01'))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15); c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM column_comments WHERE col_key LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM column_todos WHERE col_key LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM user_prefs WHERE username LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM user_pref_snapshots WHERE username LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE '\\'", ('%' + P.replace('_', chr(92)+'_') + '%',))
    c.commit(); n = 0
    for t, col in (('boards','board_id'),('users','username'),('board_columns','col_key'),
                   ('column_comments','col_key'),('column_todos','col_key'),
                   ('user_prefs','username'),('user_pref_snapshots','username')):
        n += c.execute(f'SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE chr(92)'.replace('chr(92)', "?"),
                       ('%' + P.replace('_', chr(92)+'_') + '%', chr(92))).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n

def main():
    t0 = make_token('admin'); t1 = make_token(U1); t2 = make_token(U2); t3 = make_token(U3)
    print('① 偏好备份仅手动触发（回滚不自动产生快照）')
    call('PUT', '/api/prefs/pins', t3, {'value': {'card': {'x': 1}, 'column': {}}})
    s, r = call('POST', '/api/prefs/snapshots', t3, {'note': '手动备份A'})
    ok(s == 200, '手动备份 → 200')
    sid = r.get('id')
    # 改动当前配置后再回滚
    call('PUT', '/api/prefs/pins', t3, {'value': {'card': {}, 'column': {'y': 1}}})
    s, r = call('POST', f'/api/prefs/snapshots/{sid}/restore', t3)
    ok(s == 200, f'回滚 → 200（实际 {s} {r}）')
    s, r = call('GET', '/api/prefs/snapshots', t3)
    ids = [x['id'] for x in r.get('snapshots', [])]
    ok(len(ids) == 1 and sid in ids, f'回滚后快照数量不变=1（仅手动那条，实际 {ids}）')
    # 他人快照隔离
    s, _ = call('POST', f'/api/prefs/snapshots/{sid}/restore', t1)
    ok(s == 404, '他人快照回滚 → 404（用户隔离）')

    print('② 板块删除权限：板块负责人及以上（后端 LV_COLUMN_OWNER）')
    call('POST', '/api/locks/acquire', t2, {'key': 'column:' + COLKEY})   # U2=板块负责人持锁
    s, r = call('DELETE', '/api/columns/' + urllib.parse.quote(COLKEY), t2)
    ok(s == 200, f'板块负责人(U2) 删除板块 → 200（实际 {s} {r}）')
    ok(r.get('ok') is True, '删除成功响应 ok=true')
    # 重建板块，验证普通编辑（无板块责任）被拒
    c = sqlite3.connect(DB, timeout=15); c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,owner,participants) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (COLKEY, P+'cid', BID, P+'板块', '2026-11-12', 'admin', '日常', '2026', U2, ''))
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)", (BID, P+'看板', U1, ''))
    c.commit(); c.close()
    s, r = call('DELETE', '/api/columns/' + urllib.parse.quote(COLKEY), t3)
    ok(s == 403, f'无板块责任普通编辑(U3) 删除 → 403（实际 {s} {r}）')

    print('③④⑤⑥ 静态断言（前端源码结构）')
    html = open(ROOT + '/src/static/index.html', encoding='utf-8').read()
    # ③ 浏览界面待办：无添加行/删除按钮/创建人；编辑弹窗有待办管理
    ok('cd_todo_add_row' not in html, '浏览界面已移除待办添加行')
    ok("esc(t.created_by||'')" not in html.split('function renderCdTodos')[1].split('async function cdAddTodo')[0],
       '浏览界面待办项不显示创建人账号')
    ok('id="c_todos_group"' in html and 'colAddTodo' in html, '编辑板块弹窗含待办管理区块')
    # ④ 板块行待办计数
    ok('【待办：${meta.todo_done}/${meta.todo_total}】' in html, '板块行显示【待办：x/y】（slot-subtask 槽位与事项行对齐）')
    ok("d['todo_total']" in open(ROOT + '/src/app/app.py', encoding='utf-8').read(), '后端 columns 载荷输出待办计数')
    # ⑤ 子事项列对齐：.sub-node .fcols 与 .fcols 同列数同宽
    import re as _re
    m1 = _re.search(r'\.fcols\{[^}]*grid-template-columns:([^;]+);gap:0 8px;align-items:center;\s*width:(\d+)px', html)
    m2 = _re.search(r'\.sub-node \.fcols\{grid-template-columns:([^;]+);gap:0 8px;width:(\d+)px', html)
    ok(m1 and m2 and m1.group(1) == m2.group(1) and m1.group(2) == m2.group(2),
       f'子事项行 fcols 与父事项行列定义完全一致（{m2.group(1) if m2 else "?"} / {m2.group(2) if m2 else "?"}px）')
    # ⑥ 倒计时纯数字（剥离注释后检查函数体）
    body = html.split('function cdText(due)')[1].split('\n}')[0]
    body_code = '\n'.join(l.split('//')[0] for l in body.splitlines())
    ok('天' not in body_code and "'今天'" not in body_code and '逾期' not in body_code,
       'cdText 只返回数字（无 天/今天/逾期 文案）')

setup()
try:
    main()
finally:
    n = cleanup()
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails or n:
        sys.exit(1)
