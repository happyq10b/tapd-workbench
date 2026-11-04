# -*- coding: utf-8 -*-
"""#54 人员选择层级约束 —— 后端测试
1. /api/me 与 /api/boards 每看板下发 owner / participants
2. set_board_acl：保留 participants + 互斥（设负责人时从参与人剔除）
3. set_board_participants：互斥（剔除 owner）
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__hp_'
PWD = 'At159357'
U_ADMIN = PREFIX + 'admin'
U_A, U_B, U_C = PREFIX + 'a', PREFIX + 'b', PREFIX + 'c'


def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-04 12:00:00'
    for acct in (U_ADMIN, U_A, U_B, U_C):
        c.execute('DELETE FROM users WHERE username=?', (acct,))
        c.execute('DELETE FROM team_members WHERE account=?', (acct,))
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,?,?,?,?)", (acct, PREFIX + 'hash', 'admin' if acct == U_ADMIN else 'editor', '*', '*', now))
    bid = 'HP' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,?,0,?)", (bid, PREFIX + '看板', '', U_A, U_B + ',' + U_C, now))
    c.commit()
    c.close()
    return bid


def cleanup(bid):
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config'):
        c.execute('DELETE FROM ' + t + ' WHERE board_id=?', (bid,))
    c.execute('DELETE FROM boards WHERE board_id=?', (bid,))
    for acct in (U_ADMIN, U_A, U_B, U_C):
        c.execute('DELETE FROM users WHERE username=?', (acct,))
        c.execute('DELETE FROM team_members WHERE account=?', (acct,))
    c.commit()
    c.close()


def http(path, method='GET', body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + (token or '')})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    bid = setup()
    from app.app import make_token
    tok = make_token(U_ADMIN)
    try:
        # ── 1. /api/me 下发 owner/participants ──
        print('\n【1】/api/me 每看板下发 owner / participants')
        code, r = http('/api/me', token=tok)
        b = [x for x in r.get('boards', []) if x['board_id'] == bid]
        ok(code == 200 and b, '/api/me 200 且包含夹具看板')
        ok(b and b[0].get('owner') == U_A, 'me.boards.owner = %s' % (b and b[0].get('owner')))
        ok(b and b[0].get('participants') == U_B + ',' + U_C,
           'me.boards.participants = %s' % (b and b[0].get('participants')))

        # ── 2. /api/boards 下发 participants ──
        print('\n【2】/api/boards 下发 participants')
        code, r = http('/api/boards', token=tok)
        b2 = [x for x in r.get('boards', []) if x['board_id'] == bid]
        ok(b2 and b2[0].get('participants') == U_B + ',' + U_C,
           'boards.participants = %s' % (b2 and b2[0].get('participants')))

        # ── 3. 设负责人 → 从参与人剔除（互斥） ──
        print('\n【3】set_board_acl 互斥')
        code, r = http('/api/boards/%s/acl' % bid, 'PUT', {'owner': U_B}, token=tok)
        ok(code == 200 and r.get('owner') == U_B, '设 U_B 为负责人（实际 %s）' % code)
        ok(r.get('participants') == U_C, 'U_B 自动从参与人剔除（剩 %s）' % r.get('participants'))
        c = sqlite3.connect(DB)
        row = c.execute('SELECT owner,participants FROM boards WHERE board_id=?', (bid,)).fetchone()
        c.close()
        ok(row[0] == U_B and row[1] == U_C, '落库 owner=%s parts=%s' % row)

        # ── 4. 设参与人 → 剔除当前负责人 U_B（互斥；步骤3已把负责人设为 U_B） ──
        print('\n【4】set_board_participants 互斥')
        code, r = http('/api/boards/%s/participants' % bid, 'PUT',
                       {'participants': U_A + ',' + U_B + ',' + U_C}, token=tok)
        ok(code == 200, '设参与人 [U_A,U_B,U_C]（实际 %s）' % code)
        ok(r.get('participants') == U_A + ',' + U_C,
           '当前负责人 U_B 被剔除（剩 %s）' % r.get('participants'))

        # ── 5. 换负责人不影响既有参与人（不再整体清空） ──
        print('\n【5】换负责人不清空参与人')
        code, r = http('/api/boards/%s/acl' % bid, 'PUT', {'owner': U_ADMIN}, token=tok)
        ok(code == 200 and r.get('participants') == U_A + ',' + U_C,
           '换负责人后参与人保留（%s）' % r.get('participants'))
        # 设新负责人为参与人之一 → 从参与人剔除
        code, r = http('/api/boards/%s/acl' % bid, 'PUT', {'owner': U_C}, token=tok)
        ok(code == 200 and r.get('participants') == U_A,
           '新负责人 U_C 从参与人剔除（剩 %s）' % r.get('participants'))
    finally:
        cleanup(bid)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
