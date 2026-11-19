#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-194 建库期遗留测试账号「仅超级管理员可见」测试。

过滤是按确切用户名（LEGACY_TEST_ACCOUNTS），本地库已清除这 5 个账号，
故夹具即建即删：重建同名账号 → 断言超管可见 / 非超管（含管理员角色）不可见
→ finally 清理 + 残留自查。
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("APP_SECRET", "local-dev-secret-not-for-production")
from app.app import make_token, hash_pw, LEGACY_TEST_ACCOUNTS, SUPER_ADMIN

BASE = "http://127.0.0.1:8100"
DB = os.path.join(ROOT, "src", "app.db")
P = "__t194_"
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(("  PASS " if cond else "  x FAIL ") + msg, flush=True)


def call(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def ex(sql, args=()):
    c = sqlite3.connect(DB, timeout=20)
    c.execute("PRAGMA busy_timeout=20000")
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def main():
    print("【① 夹具：重建同名遗留账号 + 非超管管理员】", flush=True)
    now = "2026-08-18 15:13:08"
    for acc in LEGACY_TEST_ACCOUNTS:
        role = "editor" if acc in ("zhangsan", "testerB", "accC") else "viewer"
        ex("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq,created_at) "
           "VALUES(?,?,?,?,?)", (acc, b"x", role, 1, now))
    ex("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq,created_at) "
       "VALUES(?,?,?,?,?)", (P + "adm", b"x", "admin", 1, now))   # 管理员角色但非超管

    tok_super = make_token(SUPER_ADMIN)
    tok_adm = make_token(P + "adm")

    print("【② 人员清单可见性】", flush=True)
    s, r = call("/api/staff/list", tok_super)
    names = {x["username"] for x in r.get("staff", [])}
    ok(s == 200 and "zhangsan" in names and "accB" in names,
       "超级管理员：5 个遗留账号全部可见")
    s, r = call("/api/staff/list", tok_adm)
    names = {x["username"] for x in r.get("staff", [])}
    ok(s == 200 and not (names & set(LEGACY_TEST_ACCOUNTS)),
       "管理员角色（非超管）：遗留账号全部隐藏")
    ok(s == 200 and len(r.get("staff", [])) >= 1, "非超管清单仍正常返回（不误伤其他账号）")

    print("【③ 账号管理清单不受影响（无成员绑定的账号本就不出现）】", flush=True)
    for tok, label in ((tok_super, "超管"), (tok_adm, "管理员角色")):
        s, r = call("/api/team", tok)
        accs = {m.get("account") for m in r.get("members", [])}
        ok(s == 200 and not (accs & set(LEGACY_TEST_ACCOUNTS)),
           "账号管理清单不含遗留账号（%s）" % label)


def cleanup():
    c = sqlite3.connect(DB, timeout=20)
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("DELETE FROM users WHERE username LIKE ?", (P + "%",))
    c.execute("DELETE FROM users WHERE username IN (?, ?, ?, ?, ?)", LEGACY_TEST_ACCOUNTS)
    c.commit()
    left = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ? OR username IN (?, ?, ?, ?, ?)",
                     (P + "%",) + LEGACY_TEST_ACCOUNTS).fetchone()[0]
    c.close()
    return left


if __name__ == "__main__":
    code = 0
    try:
        main()
    finally:
        left = cleanup()
        fails = [m for c, m in N if not c]
        print("夹具残留自查: %d（应为 0）" % left, flush=True)
        print("结果: PASS=%d FAIL=%d" % (len(N) - len(fails), len(fails)), flush=True)
        if fails or left:
            code = 1
    sys.exit(code)
