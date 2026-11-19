# -*- coding: utf-8 -*-
"""#154 ID（工号）修改：超管专属 + 全局唯一 409 带占用者姓名（API 层）"""
import json, os, sqlite3, sys, urllib.request, urllib.error

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

from app.app import make_token, hash_pw

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_id_%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_id%'")
    c.execute("INSERT INTO team_members (id,name,workgroups,account,emp_no) VALUES "
              "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_id_甲','','__t_ida','T99001')")
    c.execute("INSERT INTO team_members (id,name,workgroups,account,emp_no) VALUES "
              "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_id_乙','','__t_idb','T99002')")
    # 无工号成员（回退展示内部编号）——用于内部编号撞号校验
    c.execute("INSERT INTO team_members (id,name,workgroups,account,emp_no) VALUES "
              "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_id_丙','','','')")
    mid_a = c.execute("SELECT id FROM team_members WHERE name='__t_id_甲'").fetchone()[0]
    mid_b = c.execute("SELECT id FROM team_members WHERE name='__t_id_乙'").fetchone()[0]
    mid_c = c.execute("SELECT id FROM team_members WHERE name='__t_id_丙'").fetchone()[0]
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_ida',?,'admin','')", (hash_pw('Xx12345678'),))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_idb',?,'viewer','')", (hash_pw('Xx12345678'),))
    c.commit(); c.close()
    return mid_a, mid_b, mid_c

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_id_%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_id%'")
    c.commit(); c.close()

def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

mid_a, mid_b, mid_c = setup()
try:
    tk_super = make_token('admin')
    tk_adm = make_token('__t_ida')     # role=admin 但非超管

    print('【① 非超管管理员改 ID → 403】')
    st, d = api(tk_adm, 'PUT', '/api/team/%d' % mid_a, {'name': '__t_id_甲', 'emp_no': 'T99999'})
    ok(st == 403, '403：%s' % (d.get('detail') or ''))

    print('【② 超管改 ID 撞他人工号 → 409 带姓名】')
    st, d = api(tk_super, 'PUT', '/api/team/%d' % mid_a, {'name': '__t_id_甲', 'emp_no': 'T99002'})
    ok(st == 409 and '__t_id_乙' in (d.get('detail') or ''), '409：%s' % (d.get('detail') or ''))

    print('【③ 超管改 ID 撞他人回退展示的内部编号 → 409 带姓名】')
    st, d = api(tk_super, 'PUT', '/api/team/%d' % mid_a, {'name': '__t_id_甲', 'emp_no': str(mid_c)})
    ok(st == 409 and '__t_id_丙' in (d.get('detail') or ''), '409：%s' % (d.get('detail') or ''))

    print('【④ 超管改成唯一 ID → 200 且 /api/team 读回】')
    st, d = api(tk_super, 'PUT', '/api/team/%d' % mid_a, {'name': '__t_id_甲', 'emp_no': 'T99003'})
    ok(st == 200, '200')
    st, team = api(tk_super, 'GET', '/api/team')
    row = next((m for m in team['members'] if m['id'] == mid_a), None)
    ok(row and row['emp_no'] == 'T99003', '读回 emp_no=T99003')

    print('【⑤ 清空 ID → 回退成员编号展示】')
    st, d = api(tk_super, 'PUT', '/api/team/%d' % mid_a, {'name': '__t_id_甲', 'emp_no': ''})
    ok(st == 200, '200')
    st, team = api(tk_super, 'GET', '/api/team')
    row = next((m for m in team['members'] if m['id'] == mid_a), None)
    ok(row and row['emp_no'] == '', 'emp_no 已清空')

    print('【⑥ 与自身同值提交 → 幂等 200】')
    st, d = api(tk_super, 'PUT', '/api/team/%d' % mid_b, {'name': '__t_id_乙', 'emp_no': 'T99002'})
    ok(st == 200, '200（不视为撞号）')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
finally:
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM team_members WHERE name LIKE '__t_id_%'").fetchone()[0]
    c.close()
    print('夹具残留: %d' % n)
