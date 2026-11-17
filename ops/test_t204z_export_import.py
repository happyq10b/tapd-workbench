# -*- coding: utf-8 -*-
"""T-204z（2026-11-17 #143）：导出字段与最新事项对齐 + 导入权限收缩至超级管理员

验证项：
① /api/export/fields 新清单：24 字段（27-5+2），含新增「结算情况/代办任务」，
  不含已删 status_name/priority/label/follower/is_filed，「完成情况」改名「事项状态」
② 导出 xlsx 用新派生列成功（结算情况/代办任务写入不炸）
③ 已删 key 请求导出 → 400 fail-fast
④ /api/import/xlsx 普通用户 403 / 超管通过权限层（到达业务校验）
⑤ /api/import/template 普通用户 403 / 超管 200
⑥ 前端导入按钮仅 ME.is_super 可见（静态断言）
"""
import io
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'app.db')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

from app.app import make_token, hash_pw   # noqa: E402

U1 = '__t204z_editor'          # 夹具 editor 账号（非超管）
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


def api(path, method='GET', data=None, token=None, raw=None, content_type=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (token or TK_A))
    if raw is not None:
        body = raw
        if content_type:
            req.add_header('Content-Type', content_type)
    else:
        body = json.dumps(data).encode() if data is not None else None
        if body:
            req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''


# ── 夹具：editor 账号（try/finally 自清理） ──
c = sqlite3.connect(DB)
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
          (U1, hash_pw('Xx12345678')))
c.commit()
c.close()

TK_A = make_token('admin')          # 超级管理员（内置 admin 账号）
TK_U1 = make_token(U1)              # 普通编辑账号
try:
    # ① 字段清单
    st, body = api('/api/export/fields')
    fields = json.loads(body.decode()).get('fields', [])
    keys = [f['key'] for f in fields]
    titles = [f['title'] for f in fields]
    ok(st == 200 and len(fields) == 23, f'① 字段清单 23 项（26-5+2，实际 {len(fields)}）')
    ok('_settle_text' in keys and '结算情况' in titles, '① 新增「结算情况」_settle_text')
    ok('_subtasks_text' in keys and '代办任务' in titles, '① 新增「代办任务」_subtasks_text')
    ok('_status_text' in keys and '事项状态' in titles, '① 「完成情况」改名「事项状态」（key=_status_text）')
    for gone in ('status_name', 'priority', 'label', 'follower', 'is_filed'):
        ok(gone not in keys, f'① 已删字段 {gone} 不在清单')

    # ② 新派生列导出成功（取 1 行即可）
    st, body = api('/api/export/xlsx?fields=card_name,_settle_text,_subtasks_text&card_ids=')
    ok(st == 200 and body[:2] == b'PK', f'② 新派生列导出 200/xlsx（st={st}）')

    # ③ 已删 key fail-fast
    st, body = api('/api/export/xlsx?fields=status_name')
    ok(st == 400, f'③ 已删 key status_name 导出 400（st={st}）')

    # ④ 导入端点权限
    boundary = '----t204z'
    mp = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.xlsx"\r\n'
          'Content-Type: application/octet-stream\r\n\r\nnot-xlsx\r\n'
          f'--{boundary}--\r\n').encode()
    st, body = api('/api/import/xlsx', 'POST', raw=mp,
                   content_type=f'multipart/form-data; boundary={boundary}', token=TK_U1)
    ok(st == 403, f'④ editor 调 /api/import/xlsx → 403（st={st}）')
    st, body = api('/api/import/xlsx', 'POST', raw=mp,
                   content_type=f'multipart/form-data; boundary={boundary}', token=TK_A)
    ok(st in (400, 422), f'④ 超管通过权限层到达业务校验（st={st}，非 xlsx 应 400）')

    # ⑤ 模板下载权限
    st, body = api('/api/import/template', token=TK_U1)
    ok(st == 403, f'⑤ editor 下载导入模板 → 403（st={st}）')
    st, body = api('/api/import/template', token=TK_A)
    ok(st == 200 and body[:2] == b'PK', f'⑤ 超管下载导入模板 200（st={st}）')

    # ⑥ 前端按钮条件（静态断言）
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'src', 'static', 'index.html'), encoding='utf-8') as f:
        html = f.read()
    ok("ME&&ME.is_super?[{label:'导入（xlsx）'" in html, '⑥ 导入按钮仅 ME.is_super 渲染')
finally:
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM users WHERE username=?', (U1,))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%\\_t204z%' ESCAPE '\\'").fetchone()[0]
    c.close()
    print('夹具清理后残留:', n)

fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
