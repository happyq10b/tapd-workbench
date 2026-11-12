# -*- coding: utf-8 -*-
"""T-013b 登录页通知栏 API 测试：超管登入通知 / 非超管个人状态不变 / 公开端点"""
import json, os, sqlite3, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
RES = []


def ok(cond, msg):
    RES.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
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


def db_val(sql, args=()):
    c = sqlite3.connect(DB)
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


# ---------- setup：夹具（__t_notice_ 前缀，finally 清理） ----------
# T-0175 教训：cleanup 不得删除真实配置——备份原值，测完恢复（本测试曾两次误清
# 用户配置的「热烈欢迎核算部小伙伴测试~」）
c = sqlite3.connect(DB)
LOGIN_NOTICE_ORIG = None
try:
    _r = c.execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()
    LOGIN_NOTICE_ORIG = _r[0] if _r else None
    c.execute("INSERT INTO app_settings (key, value) VALUES ('login_notice','') "
              "ON CONFLICT(key) DO UPDATE SET value=''")
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES ('__t_notice_v','x','viewer')")
    c.execute("UPDATE users SET status_text='__t_原状态__' WHERE username='__t_notice_v'")
    c.execute("UPDATE users SET status_text='__t_超管原状态__' WHERE username='admin'")
    c.commit()
finally:
    c.close()

try:
    tk_super = make_token('admin')
    tk_v = make_token('__t_notice_v')

    print('【① 公开端点：未配置时返回空（前端显示默认提示）】', flush=True)
    st, d = api(tk_v, 'GET', '/api/login/notice')
    ok(st == 200 and d.get('notice') == '', '未配置 → notice 为空')

    print('【② 超管保存个人界面 → 写入登入通知，个人状态列保持原值】', flush=True)
    st, d = api(tk_super, 'POST', '/api/profile',
                {'status_text': '11月20日 22:00 系统升级，届时暂停登录',
                 'gender': '', 'hire_date': '', 'birth_date': '',
                 'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''})
    ok(st == 200, '保存成功')
    st, d = api(tk_v, 'GET', '/api/login/notice')
    ok(d.get('notice') == '11月20日 22:00 系统升级，届时暂停登录', '通知已落库（公开端点可取）')
    row = db_val("SELECT status_text FROM users WHERE username='admin'")
    ok(row[0] == '__t_超管原状态__', '超管 users.status_text 未被顶替（顶栏个人状态不变）：%r' % row[0])
    st, d = api(tk_super, 'GET', '/api/me')
    ok(d.get('login_notice') == '11月20日 22:00 系统升级，届时暂停登录', '/api/me 下发 login_notice（回显用）')
    ok(d.get('status_text') == '__t_超管原状态__', '/api/me 的 status_text 仍为个人状态')

    print('【③ 非超管保存个人界面 → 个人状态照旧更新，通知不受影响】', flush=True)
    st, d = api(tk_v, 'POST', '/api/profile',
                {'status_text': '__t_新状态__',
                 'gender': '', 'hire_date': '', 'birth_date': '',
                 'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''})
    ok(st == 200, '保存成功')
    row = db_val("SELECT status_text FROM users WHERE username='__t_notice_v'")
    ok(row[0] == '__t_新状态__', '非超管个人状态正常更新')
    st, d = api(tk_v, 'GET', '/api/login/notice')
    ok(d.get('notice') == '11月20日 22:00 系统升级，届时暂停登录', '通知未被非超管改动')

    print('【④ 超管清空通知 → 公开端点回空（登录页回默认提示）】', flush=True)
    api(tk_super, 'POST', '/api/profile',
        {'status_text': '', 'gender': '', 'hire_date': '', 'birth_date': '',
         'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''})
    st, d = api(tk_v, 'GET', '/api/login/notice')
    ok(d.get('notice') == '', '清空后 notice 为空')

finally:
    # ---------- cleanup：夹具零残留 ----------
    c = sqlite3.connect(DB)
    try:
        if LOGIN_NOTICE_ORIG is None:
            c.execute("DELETE FROM app_settings WHERE key='login_notice'")
        else:
            c.execute("INSERT INTO app_settings (key, value) VALUES ('login_notice',?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (LOGIN_NOTICE_ORIG,))
        c.execute("DELETE FROM users WHERE username='__t_notice_v'")
        c.execute("UPDATE users SET status_text='' WHERE username='admin'")
        c.commit()
        n1 = c.execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()[0]
        n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t_notice%'").fetchone()[0]
        print('夹具残留检查: notice恢复=%r users=%d' % (n1, n2), flush=True)
    finally:
        c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
