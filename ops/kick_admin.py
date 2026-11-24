#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-212 强制下线 admin（2026-11-24 用户需求）——本地 / 服务器生产 / 服务器开发。

用法：
    python ops/kick_admin.py local|prod|dev [--yes]

原理：
    kick API（/api/admin/online/kick）仅超管可调且「禁止踢自己」（SUPER_ADMIN=admin
    无法经 API 踢 admin 自身）→ 改走**会话代数 +1**（users.active_seq）：
    · token 立即失效（verify_token 校验 active_seq）→ 页面下次请求 401 → goLogin
    · WS 心跳校验 token（T-212 加固）→ 失效连接 ≤25s 内被服务端主动断开
    · 单点「已在线」判定随之解除
    active_seq 是会话计数器（非业务数据），+1 幂等安全、可回退（-1）；
    UPDATE 前打印原值，精确主键单行，行数≠1 即中止。

环境目标（与 sync.sh 实际部署一致，targets.sh 的 DEV_REMOTE_DIR 已过时勿抄）：
    local : 本机 sqlite（src/app.db）+ 本地服务 127.0.0.1:8100
    prod  : root@123.207.252.195  /opt/tapd-workbench/app.db   （tapd-web，  8000）
    dev   : root@123.207.252.195  /opt/tapd-dev/app.db         （tapd-dev，  8001）

依赖：本地 SSH 免密（ops/secrets/tapd_deploy_key，与 sync.sh 同一通道）。
"""
import os
import subprocess
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOCAL_DB = os.path.join(ROOT, 'src', 'app.db')
LOCAL_DB = os.path.normpath(LOCAL_DB)

SERVER_IP = '123.207.252.195'
SSH_USER = 'root'
KEY = os.path.join(HERE, 'secrets', 'tapd_deploy_key')
SSH_OPTS = ['-i', KEY, '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=20']
# 服务器端路径：sync.sh 同款（targets.sh 的 DEV_REMOTE_DIR 与实际部署不符）
REMOTE = {
    'prod': '/opt/tapd-workbench/app.db',
    'dev': '/opt/tapd-dev/app.db',
}

REMOTE_PY = r'''
import sqlite3, sys
# ssh 'python3 - -- <db>' → sys.argv = ['-', '--', '<db>']（'-' 是脚本占位）
db = sys.argv[-1]
c = sqlite3.connect(db, timeout=15)
c.execute('PRAGMA busy_timeout=15000')
row = c.execute("SELECT active_seq FROM users WHERE username='admin'").fetchone()
if not row:
    print('  [ERROR] admin 账号不存在于', db); sys.exit(1)
old = int(row[0] or 0)
cur = c.execute("UPDATE users SET active_seq=active_seq+1 WHERE username='admin'")
n = cur.rowcount
c.commit()
row2 = c.execute("SELECT active_seq FROM users WHERE username='admin'").fetchone()
c.close()
if n != 1:
    print('  [ERROR] 更新行数=%d（应为 1），已中止' % n); sys.exit(1)
print('  seq: %d -> %d（token 全部作废）' % (old, row2[0]))
'''


def kick_local():
    print('==> 本地环境（%s）' % LOCAL_DB)
    if not os.path.exists(LOCAL_DB):
        print('  [ERROR] 本地库不存在：%s' % LOCAL_DB)
        return 1
    c = sqlite3.connect(LOCAL_DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    row = c.execute("SELECT active_seq FROM users WHERE username='admin'").fetchone()
    if not row:
        print('  [ERROR] admin 账号不存在')
        c.close()
        return 1
    old = int(row[0] or 0)
    cur = c.execute("UPDATE users SET active_seq=active_seq+1 WHERE username='admin'")
    n = cur.rowcount
    c.commit()
    row2 = c.execute("SELECT active_seq FROM users WHERE username='admin'").fetchone()
    c.close()
    if n != 1:
        print('  [ERROR] 更新行数=%d（应为 1），已中止' % n)
        return 1
    print('  seq: %d -> %d（token 全部作废）' % (old, row2[0]))
    print('  完成：本地页面下次请求即回登录页；WS 心跳 ≤25s 内被服务端断开。')
    return 0


def kick_remote(env):
    db = REMOTE[env]
    label = '生产' if env == 'prod' else '开发'
    print('==> 服务器%s环境（%s@%s:%s）' % (label, SSH_USER, SERVER_IP, db))
    r = subprocess.run(
        ['ssh'] + SSH_OPTS + ['-T', '%s@%s' % (SSH_USER, SERVER_IP), 'python3 - --', db],
        input=REMOTE_PY, capture_output=True, text=True, timeout=60)
    out = (r.stdout or '').strip()
    err = (r.stderr or '').strip()
    if out:
        print(out)
    if r.returncode != 0:
        print('  [ERROR] 远端执行失败 (exit=%d)%s' % (r.returncode, ('：' + err[-300:]) if err else ''))
        return 1
    print('  完成：%s 页面下次请求即回登录页；WS 心跳 ≤25s 内被服务端断开。' % label)
    return 0


def main():
    args = [a for a in sys.argv[1:] if a != '--yes']
    env = args[0] if args else ''
    if env not in ('local', 'prod', 'dev'):
        print('用法: python ops/kick_admin.py local|prod|dev [--yes]')
        return 2
    if env == 'local':
        return kick_local()
    return kick_remote(env)


if __name__ == '__main__':
    sys.exit(main())
