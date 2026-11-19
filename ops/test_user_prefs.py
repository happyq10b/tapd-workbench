# -*- coding: utf-8 -*-
"""T-0187 个人配置持久化 + 备份/回滚 API 测试。

① PUT/GET 往返；key 白名单与大小上限
② 备份：当前全部配置完整快照（含多 key）
③ 回滚：整包替换；回滚前自动备份（版本链可回退）
④ 一致性：回滚后配置与快照一致；他人快照 404；坏快照 key 跳过
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse, urllib.error

BASE = 'http://127.0.0.1:8100'
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

P = '__upf_'
U1, U2 = P + 'u1', P + 'u2'
N = []

def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'),
                                 data=data, method=method,
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
    c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) VALUES(?,?,?,?,1)",
              (U1, hash_pw('x'), 'x', 'editor'))
    c.execute("INSERT OR IGNORE INTO users(username,password_hash,password_plain,role,active_seq) VALUES(?,?,?,?,1)",
              (U2, hash_pw('x'), 'x', 'editor'))
    c.execute("DELETE FROM user_prefs WHERE username LIKE ?", (P + '%',))
    c.execute("DELETE FROM user_pref_snapshots WHERE username LIKE ?", (P + '%',))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM user_prefs WHERE username LIKE ?", (P + '%',))
    c.execute("DELETE FROM user_pref_snapshots WHERE username LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + '%',))
    c.commit(); c.close()

try:
    setup()
    t1, t2 = make_token(U1), make_token(U2)

    print('① PUT/GET 往返 + 校验')
    s, r = call('PUT', '/api/prefs/pins', t1, {'value': {'card': {'C1': 1}, 'column': {}}})
    ok(s == 200, f'保存 pins → 200（实际 {s}）')
    s, r = call('PUT', '/api/prefs/dept_open', t1, {'value': {'核算部': 1}})
    ok(s == 200, f'保存 dept_open → 200（实际 {s}）')
    s, r = call('GET', '/api/prefs', t1)
    ok(s == 200 and r['prefs'].get('pins', {}).get('card', {}).get('C1') == 1
       and r['prefs'].get('dept_open') == {'核算部': 1}, f'GET 往返一致（实际 {r}）')
    s, r = call('PUT', '/api/prefs/BadKey!', t1, {'value': {}})
    ok(s == 400, f'非法 key → 400（实际 {s}）')
    s, r = call('PUT', '/api/prefs/big', t1, {'value': 'x' * (70 * 1024)})
    ok(s == 400, f'超 64KB → 400（实际 {s}）')

    print('② 备份：完整快照')
    s, r = call('POST', '/api/prefs/snapshots', t1, {'note': '初始状态'})
    ok(s == 200 and sorted(r.get('keys', [])) == ['dept_open', 'pins'],
       f'备份成功且 keys 完整（实际 {s} {r}）')
    sid1 = r.get('id')

    print('③ 回滚：整包替换（T-0190：回滚不再自动备份）')
    call('PUT', '/api/prefs/pins', t1, {'value': {'card': {'C2': 1}, 'column': {}}})   # 变更
    call('PUT', '/api/prefs/newkey', t1, {'value': {'a': 1}})                           # 新增 key
    s, r = call('POST', f'/api/prefs/snapshots/{sid1}/restore', t1)
    ok(s == 200 and r.get('restored_keys') == ['dept_open', 'pins'],
       f'回滚成功（实际 {s} {r}）')
    s, r = call('GET', '/api/prefs', t1)
    ok(r['prefs'].get('pins', {}).get('card', {}).get('C1') == 1
       and 'C2' not in (r['prefs'].get('pins', {}).get('card') or {})
       and 'newkey' not in r['prefs'], '回滚后配置与快照一致（新增 key 一并清除）')
    s, r = call('GET', '/api/prefs/snapshots', t1)
    auto = [x for x in r['snapshots'] if (x['note'] or '').startswith('回滚前自动备份')]
    ok(len(auto) == 0, f'回滚不自动产生快照（T-0190 口径，实际 {len(auto)} 条）')

    print('④ 一致性 / 隔离 / 边界')
    s, r = call('POST', '/api/prefs/snapshots/99999/restore', t1)
    ok(s == 404, f'不存在的快照 → 404（实际 {s}）')
    s, r = call('GET', '/api/prefs/snapshots', t2)
    ok(all(x['id'] != sid1 for x in r['snapshots']), '他人快照不可见（用户隔离）')
    s, r = call('POST', f'/api/prefs/snapshots/{sid1}/restore', t2)
    ok(s == 404, f'回滚他人快照 → 404（实际 {s}）')
    # 坏快照 key：手工插入带非法 key 的快照 → 回滚跳过脏 key
    c = sqlite3.connect(DB, timeout=15)
    c.execute("INSERT INTO user_pref_snapshots(username,data,note) VALUES(?,?, '脏key测试')",
              (U1, json.dumps({'pins': '{"card":{}}', 'bad key!': '"x"'})))
    sid_dirty = c.execute("SELECT id FROM user_pref_snapshots WHERE note='脏key测试'").fetchone()[0]
    c.commit(); c.close()
    s, r = call('POST', f'/api/prefs/snapshots/{sid_dirty}/restore', t1)
    ok(s == 200 and 'pins' in r.get('restored_keys', []) and 'bad key!' not in r.get('restored_keys', []),
       f'快照含脏 key → 跳过不落库（实际 {s} {r}）')
finally:
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    n = (c.execute("SELECT COUNT(*) FROM user_prefs WHERE username LIKE ?", (P + '%',)).fetchone()[0]
         + c.execute("SELECT COUNT(*) FROM user_pref_snapshots WHERE username LIKE ?", (P + '%',)).fetchone()[0]
         + c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (P + '%',)).fetchone()[0])
    print('夹具残留: %d' % n, flush=True)
    c.close()

fails = [m for c, m in N if not c]
print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
