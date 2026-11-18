# -*- coding: utf-8 -*-
"""T-205c（2026-11-18 #147）：登录页版本号（超管个人界面配置）

① 未配置 → /api/login/notice 的 version 为空（登录页不显示）
② 超管写入合法格式 → 200、回读一致
③ editor 写入 → 403（仅超级管理员）
④ 普通管理员（role=admin）写入 → 403（require_super 口径）
⑤ 非法格式 → 400 fail-fast
⑥ 空串清除 → 200、回读为空
⑦ 登录页静态断言：login.html 有 appVer 容器 + 拉取逻辑；index.html 有 pf_version 输入框
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8100'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw   # noqa: E402

DB = os.path.join(ROOT, 'src', 'app.db')
U1 = '__t205c_editor'      # editor
U2 = '__t205c_admin'       # role=admin 普通管理员
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (token or TK_A))
    body = json.dumps(data).encode() if data is not None else None
    if body:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


c = sqlite3.connect(DB)
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
          (U1, hash_pw('Xx12345678')))
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'admin')",
          (U2, hash_pw('Xx12345678')))
c.commit()
c.close()

TK_A = make_token('admin')
TK_U1 = make_token(U1)
TK_U2 = make_token(U2)
try:
    # ① 初始未配置（先清掉可能的存量）
    api('/api/version', 'PUT', {'version': ''})
    st, d = api('/api/login/notice')
    ok(st == 200 and d.get('version') == '', f'① 未配置时 version 为空（st={st}，v={d.get("version")!r}）')

    # ② 超管写入合法格式
    st, d = api('/api/version', 'PUT', {'version': 'v2026.11.18'})
    ok(st == 200 and d.get('version') == 'v2026.11.18', f'② 超管写入 200（st={st}，v={d.get("version")}）')
    st, d = api('/api/login/notice')
    ok(st == 200 and d.get('version') == 'v2026.11.18', '② 公开端点回读一致（登录页可展示）')

    # ③④ 权限
    st, _ = api('/api/version', 'PUT', {'version': 'v2026.01.01'}, token=TK_U1)
    ok(st == 403, f'③ editor 写入 → 403（st={st}）')
    st, _ = api('/api/version', 'PUT', {'version': 'v2026.01.01'}, token=TK_U2)
    ok(st == 403, f'④ role=admin 普通管理员写入 → 403（st={st}）')

    # ⑤ 非法格式
    for bad in ('2026.11.18', 'v26.11.18', 'v2026/11/18', 'abc'):
        st, d = api('/api/version', 'PUT', {'version': bad})
        ok(st == 400, f'⑤ 非法格式 {bad!r} → 400（st={st}）')

    # ⑥ 空串清除
    st, d = api('/api/version', 'PUT', {'version': ''})
    ok(st == 200, f'⑥ 空串清除 200（st={st}）')
    st, d = api('/api/login/notice')
    ok(d.get('version') == '', '⑥ 清除后回读为空')

    # ⑦ 前端静态断言
    with open(os.path.join(ROOT, 'src', 'static', 'login.html'), encoding='utf-8') as f:
        login_html = f.read()
    with open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8') as f:
        idx_html = f.read()
    ok('id="appVer"' in login_html and 'd.version' in login_html,
       '⑦ login.html 有版本号容器与拉取逻辑')
    ok('id="pf_version"' in idx_html and 'saveAppVersion' in idx_html and 'pfVersionGroup' in idx_html,
       '⑦ index.html 个人界面有版本号输入框与保存函数')
finally:
    api('/api/version', 'PUT', {'version': ''})   # 环境还原
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM users WHERE username IN (?,?)', (U1, U2))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%\\_t205c%' ESCAPE '\\'").fetchone()[0]
    c.close()
    print('夹具清理后残留:', n)

fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
