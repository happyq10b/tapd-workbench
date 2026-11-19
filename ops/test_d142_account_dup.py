# -*- coding: utf-8 -*-
"""#142 账号唯一性专项测试（夹具 __t_acc 前缀，try/finally 清理）"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)


def api(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get('detail', '')
        except Exception:
            detail = ''
        return e.code, {'detail': detail}


def main():
    from app.app import make_token
    tk = make_token('admin')
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        # 夹具：原成员 + 已绑定账号
        c.execute("INSERT INTO team_members (id,name,workgroups,account) "
                  "VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_原成员','','__t_acc1')")
        mid_orig = c.execute("SELECT id FROM team_members WHERE name='__t_原成员'").fetchone()['id']
        c.commit()

        print('【1】添加与已有成员相同账号的新成员 → 409 拒绝')
        st, d = api('POST', '/api/team', tk, {'name': '__t_新成员', 'account': '__t_acc1', 'password': 'x12345', 'role': 'viewer'})
        ok(st == 409, '返回 409（实际 %s）' % st)
        ok('账号已存在' in d.get('detail', ''), '错误文案：%s' % d.get('detail', ''))
        row = c.execute("SELECT account FROM team_members WHERE id=?", (mid_orig,)).fetchone()
        ok(row and row['account'] == '__t_acc1', '原成员账号未被清空（=%s）' % (row['account'] if row else None))
        dup = c.execute("SELECT COUNT(*) n FROM team_members WHERE name='__t_新成员'").fetchone()['n']
        ok(dup == 0, '未产生新成员记录（副作用为零）')

        print('【2】PUT 把成员 B 的账号改成成员 A 已绑账号 → 409 拒绝')
        c.execute("INSERT INTO team_members (id,name,workgroups,account) "
                  "VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_成员B','','')")
        mid_b = c.execute("SELECT id FROM team_members WHERE name='__t_成员B'").fetchone()['id']
        c.commit()
        st, d = api('PUT', '/api/team/%d' % mid_b, tk, {'name': '__t_成员B', 'account': '__t_acc1'})
        ok(st == 409 and '账号已存在' in d.get('detail', ''), '返回 409 + 文案（%s %s）' % (st, d.get('detail', '')))
        row = c.execute("SELECT account FROM team_members WHERE id=?", (mid_orig,)).fetchone()
        ok(row['account'] == '__t_acc1', '原成员账号依然完好')

        print('【3】未绑定的已有 users 账号 → 仍允许绑定（正常重绑流程）')
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns) VALUES ('__t_acc_free','x','viewer','*','*')")
        c.commit()
        st, d = api('POST', '/api/team', tk, {'name': '__t_成员C', 'account': '__t_acc_free', 'password': 'x12345', 'role': 'viewer'})
        ok(st == 200, '绑定成功（%s）' % st)
        mid_c = c.execute("SELECT id FROM team_members WHERE name='__t_成员C'").fetchone()['id']

        print('【4】唯一账号的新成员 → 正常添加')
        st, d = api('POST', '/api/team', tk, {'name': '__t_成员D', 'account': '__t_acc_d', 'password': 'x12345', 'role': 'viewer'})
        ok(st == 200, '添加成功（%s）' % st)
    finally:
        c.execute("DELETE FROM team_members WHERE name LIKE '__t_%'")
        c.execute("DELETE FROM users WHERE username LIKE '\\_\\_t\\_%' ESCAPE '\\'")
        c.commit()
        c.close()
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))


main()
