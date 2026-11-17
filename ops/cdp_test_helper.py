# -*- coding: utf-8 -*-
"""CDP 测试账号隔离与下线公共模块（2026-11-17 #128 · 用户立规「不允许测试占用 admin」）。

背景：CDP 探针曾以真实 admin 账号登录页面（产生 WS 连接 = 在线列表「admin 在线」），
脚本结束杀进程后又因 Chrome 子进程（network service）存活而复活连接（#T-204k）。

三重防线（所有 CDP 脚本必须走本模块）：
  1. 页面登录一律用一次性测试账号 __cdp_ui（role='admin' 保证页面能力位），不用真实账号；
  2. 结束时 kill_profile_chrome() 按 profile 树杀（/T 含全部子进程）并复查计数归零；
  3. force_offline_and_remove() 把测试账号 active_seq+1 强制下线后从 users 表删除——
     token 立即失效、在线列表不可能再出现该账号（零残留）。
"""
import os
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(ROOT, 'src', 'app.db')
TEST_UI_USER = '__cdp_ui'


def _sys_path_src():
    import sys
    src = os.path.join(ROOT, 'src')
    if src not in sys.path:
        sys.path.insert(0, src)
    os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')


def ensure_test_ui_account():
    """创建（幂等）CDP 页面登录专用测试账号，返回其 token。role='admin' 保证
    页面能力位（ME.is_admin）与真实 admin 相同，但账号本身是一次性的。"""
    _sys_path_src()
    from app.app import make_token, hash_pw
    c = sqlite3.connect(DB)
    c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?, 'admin')",
              (TEST_UI_USER, hash_pw('Xx' + TEST_UI_USER + '99')))
    c.commit()
    c.close()
    return make_token(TEST_UI_USER)


def kill_profile_chrome(tag):
    """按 CommandLine 匹配 profile 关键字，整棵进程树强杀（/T），并复查残留归零。
    tag = profile 目录名（如 'cdp_t204j'）。wmic 输出 GBK —— 必须忽略解码错误。"""
    pat = "name='chrome.exe' and CommandLine like '%%%s%%'" % tag
    try:
        out = subprocess.run(['wmic', 'process', 'where', pat,
                              'get', 'ProcessId', '/FORMAT:VALUE'],
                             capture_output=True, timeout=20).stdout.decode('gbk', errors='ignore')
        pids = [ln.split('=')[1].strip() for ln in out.splitlines() if ln.startswith('ProcessId=')]
        for pid in pids:
            subprocess.run(['taskkill', '/PID', pid, '/T', '/F'],
                           capture_output=True, timeout=15)
        # 复查（含子进程）——非零则再补一轮
        out2 = subprocess.run(['wmic', 'process', 'where', pat,
                               'get', 'ProcessId', '/FORMAT:VALUE'],
                              capture_output=True, timeout=20).stdout.decode('gbk', errors='ignore')
        left = [ln.split('=')[1].strip() for ln in out2.splitlines() if ln.startswith('ProcessId=')]
        for pid in left:
            subprocess.run(['taskkill', '/PID', pid, '/T', '/F'],
                           capture_output=True, timeout=15)
    except Exception:
        pass


def force_offline_and_remove(username=TEST_UI_USER):
    """测试账号强制下线并删除：active_seq+1 使存量 token 全部失效，随后删号零残留。
    （在线状态由 WS 连接产生：浏览器已树杀 + 账号已删 → 在线列表不可能再出现。）"""
    try:
        c = sqlite3.connect(DB, timeout=15)
        c.execute("PRAGMA busy_timeout=15000")
        c.execute("UPDATE users SET active_seq=active_seq+1 WHERE username=?", (username,))
        c.execute("DELETE FROM users WHERE username=?", (username,))
        c.execute("DELETE FROM user_prefs WHERE username=?", (username,))
        c.execute("DELETE FROM messages WHERE receiver=? OR sender=?", (username, username))
        c.commit()
        c.close()
    except Exception:
        pass


def cleanup(tag):
    """标准收尾：树杀浏览器 → 测试账号强制下线并删除。所有 CDP 脚本 finally 必调。"""
    kill_profile_chrome(tag)
    force_offline_and_remove()
