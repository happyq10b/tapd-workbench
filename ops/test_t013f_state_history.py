# -*- coding: utf-8 -*-
"""T-013f 状态快照 API 测试：通知/个人状态变更记录 / 查询 / 回滚 / 越权"""
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


U = '__t_sh_u'
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA busy_timeout=5000')
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (U, hash_pw('Xx12345678')))
c.execute("UPDATE users SET status_text='__t_旧状态__' WHERE username=?", (U,))
# 真实 login_notice 备份（§3.3：cleanup 恢复，不再无条件 DELETE——曾误删真实通知两次）
_orig_notice = c.execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()
c.execute("INSERT INTO app_settings (key,value) VALUES ('login_notice','__t_旧通知__') "
          "ON CONFLICT(key) DO UPDATE SET value='__t_旧通知__'")
c.commit(); c.close()
_ORIG_NOTICE = _orig_notice[0] if _orig_notice else None

try:
    tk_a = make_token('admin')
    tk_u = make_token(U)

    print('【① 超管改登入通知 → login_notice 快照记录（旧值留存）】', flush=True)
    st, d = api(tk_a, 'POST', '/api/profile',
                {'status_text': '__t_新通知__', 'gender': '', 'hire_date': '', 'birth_date': '',
                 'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''})
    ok(st == 200, '保存成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    row = c.execute("SELECT old_value,new_value,changed_by FROM state_history "
                    "WHERE scope='login_notice' AND new_value='__t_新通知__'").fetchone()
    ok(row and row[0] == '__t_旧通知__' and row[2] == 'admin', '快照记录旧值→新值+操作人')
    RID_N = c.execute("SELECT id FROM state_history WHERE scope='login_notice' "
                      "AND new_value='__t_新通知__'").fetchone()[0]
    c.close()

    print('【② 非超管改个人状态 → profile_status 快照】', flush=True)
    st, d = api(tk_u, 'POST', '/api/profile',
                {'status_text': '__t_新状态__', 'gender': '', 'hire_date': '', 'birth_date': '',
                 'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''})
    ok(st == 200, '保存成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    row = c.execute("SELECT old_value,new_value,entity FROM state_history "
                    "WHERE scope='profile_status' AND new_value='__t_新状态__'").fetchone()
    ok(row and row[0] == '__t_旧状态__' and row[2] == U, '个人状态快照（按用户名归属）')
    RID_S = c.execute("SELECT id FROM state_history WHERE scope='profile_status' "
                      "AND new_value='__t_新状态__'").fetchone()[0]
    c.close()

    print('【③ 查询端点（管理员）+ 越权 403】', flush=True)
    st, d = api(tk_a, 'GET', '/api/state-history?limit=50')
    scopes = set(x['scope'] for x in d.get('items', []))
    ok(st == 200 and {'login_notice', 'profile_status'} <= scopes, '管理员可查两类快照')
    st, d = api(tk_u, 'GET', '/api/state-history')
    ok(st == 403, '非管理员查询 → 403')

    print('【④ 回滚登入通知 → 旧值写回 + 回滚本身留痕】', flush=True)
    st, d = api(tk_a, 'POST', '/api/state-history/%d/rollback' % RID_N)
    ok(st == 200 and d.get('restored_value') == '__t_旧通知__', '回滚返回恢复值')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    cur = c.execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()[0]
    ok(cur == '__t_旧通知__', '通知已恢复旧值')
    rb = c.execute("SELECT old_value,new_value FROM state_history WHERE scope='login_notice' "
                   "ORDER BY id DESC LIMIT 1").fetchone()
    ok(rb[0] == '__t_新通知__' and rb[1] == '__t_旧通知__', '回滚动作本身留痕（可再回滚）')
    c.close()

    print('【⑤ 回滚个人状态 → 该用户状态恢复】', flush=True)
    st, d = api(tk_a, 'POST', '/api/state-history/%d/rollback' % RID_S)
    ok(st == 200, '回滚成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    cur = c.execute("SELECT status_text FROM users WHERE username=?", (U,)).fetchone()[0]
    ok(cur == '__t_旧状态__', '个人状态已恢复旧值')
    c.close()

finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM state_history WHERE old_value LIKE '__t\\_%' ESCAPE '\\' "
              "OR new_value LIKE '__t\\_%' ESCAPE '\\'")
    c.execute("DELETE FROM users WHERE username=?", (U,))
    # 恢复真实 login_notice（有真实值 → 写回；本无 → 删测试行）
    if _ORIG_NOTICE is not None:
        c.execute("INSERT INTO app_settings (key,value) VALUES ('login_notice',?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_ORIG_NOTICE,))
    else:
        c.execute("DELETE FROM app_settings WHERE key='login_notice'")
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM state_history WHERE old_value LIKE '%__t_%' OR new_value LIKE '%__t_%'").fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (U,)).fetchone()[0]
    n3 = c.execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()
    print('夹具残留检查: history=%d users=%d notice_restored=%s' % (
        n1, n2, (n3 or [''])[0][:20]), flush=True)
    c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
