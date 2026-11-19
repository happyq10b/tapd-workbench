# -*- coding: utf-8 -*-
"""T-191i 状态联动校验实测：
① 板块设「已完成」：存在未完成事项 → 400（文案含数量）；全部完成 → 200；
   设「进行中/未完成」不受限（只拦「设为完成」这一个方向）；
② 父事项设「已完成」：存在未完成子事项 → 400；全部子事项完成 → 200；
③ 倒计时停用是前端渲染规则（不涉后端），此处不测。
夹具 __t191i_ 前缀 + finally 清理 + 残留自查。
"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request

ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
BASE = 'http://127.0.0.1:8100'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

P = '__t191i_'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


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
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    cleanup()
    c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
              (P + 'u1', hash_pw('x'), 'editor'))
    c.execute("INSERT INTO boards(board_id,board_name,owner) VALUES(?,?,?)",
              (P + 'bid', P + '看板', 'admin'))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,year,completion) VALUES(?,?,?,?,?,?,?,?,?)",
              (P + 'bid::' + P + '板块', P + 'cid', P + 'bid', P + '板块', '2026-11-13', 'admin',
               '日常', '2026', 'open'))
    for cid, st, parent in ((P + 'c1', 'done', ''), (P + 'c2', 'open', ''),
                            (P + 'cp', 'open', ''), (P + 's1', 'open', P + 'cp')):
        c.execute("""INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,
                     status,owner,cc,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                  (cid, P + 'bid', P + '看板', P + 'cid', P + '板块', P + cid[1:], st, '', '',
                   '2026-11-13', parent))
    c.commit(); c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('users', 'username')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('users', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def main():
    t0 = make_token('admin')
    colkey = urllib.parse.quote(P + 'bid::' + P + '板块')

    print('① 板块完成门槛')
    s, r = call('PUT', '/api/columns', t0,
                {'col_key': P + 'bid::' + P + '板块', 'board_id': P + 'bid', 'completion': 'done'})
    ok(s == 400 and '未完成' in (r.get('detail') or ''),
       '板块下有未完成事项 → 400（%s）' % (r.get('detail') or '')[:50])
    # 全部事项（c1/c2/cp/s1，含子事项）完成后再设 → 200
    # （cp 设完成本身受父事项门槛约束 → 先完成子事项 s1）
    call('PUT', '/api/cards/' + P + 's1', t0, {'fields': {'status': 'done'}})
    call('PUT', '/api/cards/' + P + 'cp', t0, {'fields': {'status': 'done'}})
    call('PUT', '/api/cards/' + P + 'c2', t0, {'fields': {'status': 'done'}})
    s, r = call('PUT', '/api/columns', t0,
                {'col_key': P + 'bid::' + P + '板块', 'board_id': P + 'bid', 'completion': 'done'})
    ok(s == 200, '全部事项完成后板块设完成 → 200（实际 %s）' % s)
    # 设「进行中」不受限（只拦「设为完成」方向）
    s, r = call('PUT', '/api/columns', t0,
                {'col_key': P + 'bid::' + P + '板块', 'board_id': P + 'bid', 'completion': 'progressing'})
    ok(s == 200, '设「进行中」不受限 → 200')

    print('② 父事项完成门槛')
    # 重置夹具状态（① 的收尾把 s1/cp 都改成 done 了）
    call('PUT', '/api/cards/' + P + 's1', t0, {'fields': {'status': 'open'}})
    call('PUT', '/api/cards/' + P + 'cp', t0, {'fields': {'status': 'open'}})
    s, r = call('PUT', '/api/cards/' + P + 'cp', t0, {'fields': {'status': 'done'}})
    ok(s == 400 and '子事项' in (r.get('detail') or ''),
       '子事项未完成 → 400（%s）' % (r.get('detail') or '')[:50])
    call('PUT', '/api/cards/' + P + 's1', t0, {'fields': {'status': 'done'}})
    s, r = call('PUT', '/api/cards/' + P + 'cp', t0, {'fields': {'status': 'done'}})
    ok(s == 200, '全部子事项完成后父事项设完成 → 200（实际 %s）' % s)
    # 子事项自己设完成不受限（无下级）
    s, r = call('PUT', '/api/cards/' + P + 's1', t0, {'fields': {'status': 'open'}})
    ok(s == 200, '子事项状态回改不受限 → 200')


if __name__ == '__main__':
    setup()
    try:
        main()
    finally:
        left = cleanup()
    fails = [m for c, m in N if not c]
    print('\n===== 结果: %d/%d 通过，残留=%d =====' % (len(N) - len(fails), len(N), left), flush=True)
    for m in fails:
        print('FAIL: ' + m)
    sys.exit(1 if (fails or left) else 0)
