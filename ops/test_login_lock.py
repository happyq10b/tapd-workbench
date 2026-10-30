# -*- coding: utf-8 -*-
"""登录失败锁定策略的端到端回归测试。

覆盖：
  1. 失败 1~4 次 → 401（不限流）
  2. 第 5 次失败 → 429 冷却 180 秒
  3. 冷却期内继续失败 → 仍 429，且计数继续累加
  4. 第 10 次失败 → 423 永久锁定
  5. 锁定后任何密码都拒绝
  6. **密码成功一次 → 失败计数立即清 0**（含冷却期内用正确密码登录）
  7. admin 可查看锁定列表并重置
  8. 锁定状态查询接口

用法：先起服务（默认 127.0.0.1:8100），再
    python ops/test_login_lock.py
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('TAPD_BASE', 'http://127.0.0.1:8100')
DB = os.environ.get('TAPD_DB', os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src', 'app.db'))
TEST_USER = '__lock_test_user__'
TEST_PWD = 'rightpass123'

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw, make_token   # noqa: E402

passed = 0
failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  FAIL ' + msg)


def http(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except Exception:
            return e.code, {}


def db():
    return sqlite3.connect(DB)


def reset_attempts():
    c = db()
    c.execute('DELETE FROM login_attempts WHERE username=?', (TEST_USER,))
    c.commit()
    c.close()


def attempts_row():
    c = db()
    row = c.execute('SELECT fail_count, locked FROM login_attempts WHERE username=?',
                     (TEST_USER,)).fetchone()
    c.close()
    return row


def setup_user():
    c = db()
    c.execute('DELETE FROM users WHERE username=?', (TEST_USER,))
    c.execute('DELETE FROM login_attempts WHERE username=?', (TEST_USER,))
    c.execute("""INSERT INTO users (username,password_hash,role,allowed_boards,
                 allowed_columns,created_at)
                 VALUES (?,?,'viewer','*','*',datetime('now','localtime'))""",
              (TEST_USER, hash_pw(TEST_PWD)))
    c.commit()
    c.close()


def teardown():
    c = db()
    c.execute('DELETE FROM users WHERE username=?', (TEST_USER,))
    c.execute('DELETE FROM login_attempts WHERE username=?', (TEST_USER,))
    c.commit()
    c.close()


print('=== 登录失败锁定策略 ===')
setup_user()

# ---------- 1) 前 4 次失败 → 401，不限流 ----------
print('\n【用例1】失败 1~4 次 → 401')
for i in range(1, 5):
    code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
    ok(code == 401, f'第 {i} 次失败返回 401（实际 {code}）')
row = attempts_row()
ok(row is not None and row[0] == 4, f'失败计数累计到 4（实际 {row[0] if row else None}）')
ok(row is not None and int(row[1]) == 0, '未锁定')

# ---------- 2) 第 5 次 → 429 冷却 ----------
print('\n【用例2】第 5 次失败 → 429 冷却 180 秒')
code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
ok(code == 429, f'第 5 次失败返回 429（实际 {code}）')
ok('180' in str(r.get('detail', '')), f'提示含冷却秒数 180：{r.get("detail")}')
row = attempts_row()
ok(row[0] == 5, f'失败计数为 5（实际 {row[0]}）')

# ---------- 3) 冷却期内继续失败 → 仍 429 且计数累加 ----------
print('\n【用例3】冷却期内继续失败 → 429 且计数累加（否则永远到不了 10 次锁定）')
for i in range(6, 10):
    code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
    ok(code == 429, f'第 {i} 次失败返回 429（实际 {code}）')
row = attempts_row()
ok(row[0] == 9, f'冷却期内计数继续累加到 9（实际 {row[0]}）')

# ---------- 4) 第 10 次 → 423 永久锁定 ----------
print('\n【用例4】第 10 次失败 → 423 永久锁定')
code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
ok(code == 423, f'第 10 次失败返回 423（实际 {code}）')
ok('管理员' in str(r.get('detail', '')), f'提示需找管理员：{r.get("detail")}')
row = attempts_row()
ok(row[0] == 10 and int(row[1]) == 1, f'锁定标记已置位（fail={row[0]}, locked={row[1]}）')

# ---------- 5) 锁定后任何密码都拒绝 ----------
print('\n【用例5】锁定后即使密码正确也拒绝')
code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': TEST_PWD})
ok(code == 423, f'正确密码也被拒绝（实际 {code}）')

# ---------- 6) 密码成功一次 → 计数清 0 ----------
print('\n【用例6】密码成功一次 → 失败计数立即清 0')
reset_attempts()
for i in range(4):
    http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
ok(attempts_row()[0] == 4, '先错 4 次，计数 = 4')
code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': TEST_PWD})
ok(code == 200, f'密码正确 → 登录成功（实际 {code}）')
ok(attempts_row() is None, '成功后计数记录被清空（DELETE 整行）')

# 冷却期内用正确密码登录，同样放行且清零
reset_attempts()
for i in range(5):
    http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
ok(attempts_row()[0] == 5, '先错 5 次进入冷却，计数 = 5')
code, r = http('/api/login', 'POST', {'username': TEST_USER, 'password': TEST_PWD})
ok(code == 200, f'冷却期内密码正确 → 仍然放行（实际 {code}）')
ok(attempts_row() is None, '冷却期内成功后计数同样清 0')

# ---------- 7) admin 查看与重置 ----------
print('\n【用例7】admin 查看锁定列表并重置')
reset_attempts()
for i in range(5):
    http('/api/login', 'POST', {'username': TEST_USER, 'password': 'wrong'})
tok = make_token('admin')
code, r = http('/api/admin/login-locks', token=tok)
ok(code == 200, f'admin 查询锁定列表（实际 {code}）')
ok(r.get('thresholds', {}).get('fail') == 5, '阈值 fail=5')
ok(r.get('thresholds', {}).get('cooldown') == 180, '阈值 cooldown=180')
ok(r.get('thresholds', {}).get('lock') == 10, '阈值 lock=10')
found = [x for x in r.get('locks', []) if x['username'] == TEST_USER]
ok(len(found) == 1 and found[0]['fail_count'] == 5, '列表里能看到该账号且失败数为 5')
ok(found and found[0]['retry_after'] > 0, f'冷却剩余秒数 > 0（{found[0]["retry_after"] if found else "?"}）')

code, r = http('/api/admin/login-lock/reset', 'POST', {'username': TEST_USER}, token=tok)
ok(code == 200, f'admin 重置（实际 {code}）')
ok(attempts_row() is None, '重置后计数记录被清空')
code, r = http('/api/login/lock-status?username=' + TEST_USER)
ok(not r.get('blocked'), '重置后不再受限')

# ---------- 8) 锁定状态查询接口 ----------
print('\n【用例8】锁定状态查询接口')
code, r = http('/api/login/lock-status?username=__no_such_user__')
ok(code == 200 and not r.get('blocked'), '不存在的账号不受限')

teardown()
print(f'\n结果：{passed} 通过 / {failed} 失败')
sys.exit(1 if failed else 0)
