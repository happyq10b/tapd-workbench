# -*- coding: utf-8 -*-
"""T-191 人员管理 + 到期筛选 测试：
① /api/staff/list 仅管理员（非管理员 403）、字段齐全；
② /api/staff/media 设置/清除头像并留档（user_media_history）；
③ 历史按条回滚（restore 后旧值写回，回滚本身再次留档）；
④ 快照创建/清单/整包回滚（回滚不自动产生快照）；
⑤ POST /api/profile 的头像/照片变更接入历史留档；
⑥ /api/cards due_dates 过滤（到期筛选）与 /api/due_counts 热力统计；
⑦ 非法 data URL 400。
夹具全部用 __t191_ 前缀命名空间 + finally 清理 + 残留自查（防污染真实数据）。
"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request

ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
BASE = 'http://127.0.0.1:8100'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

P = '__t191_'
BID = P + 'bid'
U1, U2 = P + 'u1', P + 'u2'
PNG1 = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
        'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
PNG2 = PNG1.replace('BQDwAEh', 'BQDwAEi')   # 内容不同的第二张（仍为合法 png data URL）
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'), data=data,
        method=method, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ct = (r.headers.get('Content-Type') or '').lower()
            if 'json' not in ct:
                return r.status, {'_binary': True, 'ct': ct, 'bytes': len(r.read())}
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}


def setup():
    c = sqlite3.connect(DB, timeout=15); c.execute('PRAGMA busy_timeout=15000')
    for u in (U1, U2):
        c.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
                  (u, hash_pw('x'), 'editor'))
    c.execute("DELETE FROM users WHERE username=?", (U1,))
    c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
              (U1, hash_pw('x'), 'editor'))
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', U1, ''))
    c.execute("""INSERT OR IGNORE INTO cards(card_id,board_id,board_name,column_name,card_name,
                 status,owner,cc,due,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,0)""",
              (P + 'c1', BID, P + '看板', P + '板块', P + '事项一', 'open', '张三', '', '2099-01-01', '2026-11-01'))
    c.execute("""INSERT OR IGNORE INTO cards(card_id,board_id,board_name,column_name,card_name,
                 status,owner,cc,due,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,0)""",
              (P + 'c2', BID, P + '看板', P + '板块', P + '事项二', 'open', '李四', '', '2099-01-02', '2026-11-01'))
    c.execute("""INSERT OR IGNORE INTO cards(card_id,board_id,board_name,column_name,card_name,
                 status,owner,cc,due,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,0)""",
              (P + 'c3', BID, P + '看板', P + '板块', P + '事项三', 'open', '王五', '', '', '2026-11-01'))
    c.commit(); c.close()


def cleanup():
    esc = P.replace('_', chr(92) + '_')
    c = sqlite3.connect(DB, timeout=15); c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM user_media_history WHERE username LIKE ? ESCAPE '\\'", ('%' + esc + '%',))
    c.execute("DELETE FROM user_media_snapshots WHERE note LIKE ? ESCAPE '\\'", (esc + '%',))
    c.execute("DELETE FROM cards WHERE card_id LIKE ? ESCAPE '\\'", ('%' + esc + '%',))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ? ESCAPE '\\'", ('%' + esc + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ? ESCAPE '\\'", ('%' + esc + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE '\\'", ('%' + esc + '%',))
    c.commit(); n = 0
    for t, col in (('boards', 'board_id'), ('users', 'username'), ('cards', 'card_id'),
                   ('board_columns', 'col_key'), ('user_media_history', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '\\'".replace("ESCAPE '\\'", "ESCAPE ?"),
                       ('%' + esc + '%', '\\')).fetchone()[0]
    n += c.execute("SELECT COUNT(*) FROM user_media_snapshots WHERE note LIKE ? ESCAPE ?",
                   (esc + '%', '\\')).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def main():
    t0 = make_token('admin'); t1 = make_token(U1)
    print('① /api/staff/list 权限与字段')
    s, r = call('GET', '/api/staff/list', t1)
    ok(s == 403, '非管理员访问 staff/list → 403（实际 %s）' % s)
    s, r = call('GET', '/api/staff/list', t0)
    ok(s == 200, '管理员访问 staff/list → 200')
    mine = [x for x in r.get('staff', []) if x['username'] == U1]
    ok(len(mine) == 1, '清单含夹具账号（绑定成员行或账号补行）')
    if mine:
        m = mine[0]
        need = ('name', 'username', 'role', 'emp_no', 'departments', 'gender', 'hire_date',
                'birth_date', 'native_province', 'native_city', 'phone', 'political_status',
                'status_text', 'has_avatar', 'has_photo', 'last_login_at', 'created_at')
        ok(all(k in m for k in need), '全字段齐备（%s…）' % ','.join(need[:6]) + '…')
        ok(m['has_avatar'] == False and m['has_photo'] == False, '夹具账号初始无头像/照片标志')

    print('② /api/staff/media 设置/清除 + 留档')
    s, r = call('POST', '/api/staff/media', t0, {'username': U1, 'field': 'avatar', 'data': PNG1})
    ok(s == 200 and r.get('changed'), '设置头像 → 200 changed（实际 %s %s）' % (s, r))
    s, r = call('POST', '/api/staff/media', t0, {'username': U1, 'field': 'avatar', 'data': PNG2})
    ok(s == 200 and r.get('changed'), '替换头像 → 200 changed')
    s, r = call('GET', '/api/staff/media/history?user=' + U1, t0)
    h = r.get('history', [])
    ok(s == 200 and len(h) == 2, '历史留档 2 条（实际 %d）' % len(h))
    ok(h and h[0]['has_new'] and h[0]['has_old'] and h[0]['changed_by'] == 'admin',
       '最新一条：旧值+新值均在、操作人=admin')
    s, r = call('GET', '/api/staff/img/%s/avatar' % U1, t0)
    ok(s == 200 and r.get('_binary') and r.get('ct', '').startswith('image/') and r.get('bytes', 0) > 0,
       '图片直出 → 200 二进制图片（实际 %s %s）' % (s, r))
    s, r = call('POST', '/api/staff/media', t0, {'username': U1, 'field': 'avatar', 'data': 'http://x/y.png'})
    ok(s == 400, '非法 data URL → 400（实际 %s）' % s)
    s, r = call('POST', '/api/staff/media', t1, {'username': U1, 'field': 'photo', 'data': PNG1})
    ok(s == 403, '非管理员设置媒体 → 403（实际 %s）' % s)

    print('③ 历史按条回滚')
    s, r = call('GET', '/api/staff/media/history?user=' + U1, t0)
    hid = r['history'][0]['id']          # 最新一条（PNG2）→ 旧值 PNG1
    s, r = call('POST', '/api/staff/media/history/%d/restore' % hid, t0)
    ok(s == 200 and r.get('changed'), '回滚最新历史 → 200 changed')
    c = sqlite3.connect(DB); cur = c.execute('SELECT avatar FROM users WHERE username=?', (U1,)).fetchone()
    ok(cur and cur[0] == PNG1, '回滚后头像=旧值 PNG1')
    c.close()
    s, r = call('GET', '/api/staff/media/history?user=' + U1, t0)
    ok(len(r['history']) == 3, '回滚本身再次留档（共 3 条，实际 %d）' % len(r['history']))

    print('④ 快照创建 / 清单 / 整包回滚')
    s, r = call('POST', '/api/staff/media/snapshots', t0, {'note': P + '快照A'})
    ok(s == 200 and r.get('id'), '创建快照 → 200（实际 %s）' % s)
    sid = r.get('id')
    call('POST', '/api/staff/media', t0, {'username': U1, 'field': 'avatar', 'data': ''})   # 清除头像
    s, r = call('GET', '/api/staff/media/snapshots', t0)
    ok(any(x['id'] == sid for x in r.get('snapshots', [])), '快照清单包含 # %s' % sid)
    s, r = call('POST', '/api/staff/media/snapshots/%d/restore' % sid, t0)
    ok(s == 200, '整包回滚 → 200（实际 %s %s）' % (s, r))
    c = sqlite3.connect(DB); cur = c.execute('SELECT avatar FROM users WHERE username=?', (U1,)).fetchone()
    ok(cur and cur[0] == PNG1, '回滚后头像还原为快照时点 PNG1')
    c.close()
    s, r = call('GET', '/api/staff/media/snapshots', t0)
    ok(len(r.get('snapshots', [])) == 1, '回滚不自动产生新快照（清单仍 1 条）')

    print('⑤ 个人资料接口接入历史留档')
    s, r = call('POST', '/api/profile', t1, {'avatar': PNG2, 'photo': PNG1})
    ok(s == 200, '本人上传头像/照片 → 200（实际 %s）' % s)
    s, r = call('GET', '/api/staff/media/history?user=' + U1, t0)
    hh = r['history']
    ok(len(hh) >= 2, 'profile 变更产生新留档（avatar+photo 两条，历史共 %d 条）' % len(hh))
    ok(all(x['changed_by'] == U1 for x in hh[:2]), '操作人记录为本人账号')

    print('⑥ 到期筛选 due_dates + due_counts')
    s, r = call('GET', '/api/cards?board_ids=' + BID + '&due_dates=2099-01-01', t0)
    ids = [x['card_id'] for x in r.get('cards', [])]
    ok(s == 200 and ids == [P + 'c1'], 'due_dates=2099-01-01 → 仅命中事项一（实际 %s）' % ids)
    s, r = call('GET', '/api/cards?board_ids=' + BID + '&due_dates='
                + urllib.parse.quote('2099-01-01,2099-01-02'), t0)
    ids = sorted(x['card_id'] for x in r.get('cards', []))
    ok(ids == [P + 'c1', P + 'c2'], '多日任一命中 → 两件（实际 %s）' % ids)
    s, r = call('GET', '/api/due_counts?board_ids=' + BID, t0)
    counts = r.get('counts', {})
    ok(counts.get('2099-01-01') == 1 and counts.get('2099-01-02') == 1,
       'due_counts：两日各 1（实际 %s）' % {k: v for k, v in counts.items() if k.startswith('2099')})
    ok(all(k for k in counts), 'due_counts 不含空日期键')
    # 到期筛选与其它筛选叠加：负责人过滤后计数应只算张三
    s, r = call('GET', '/api/due_counts?board_ids=' + BID + '&person=' + urllib.parse.quote('张三'), t0)
    ok(r.get('counts', {}).get('2099-01-01') == 1 and not r.get('counts', {}).get('2099-01-02'),
       'due_counts 与负责人筛选联动')
    # 导出与列表同口径：due_dates 透传（不解析 xlsx 内容，仅校验不报错）
    s, r = call('GET', '/api/export/xlsx?board_ids=' + BID
                + '&due_dates=' + urllib.parse.quote('2099-01-01'), t0)
    ok(s == 200, '导出透传 due_dates → 200（实际 %s）' % s)


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
