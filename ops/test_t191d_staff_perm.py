# -*- coding: utf-8 -*-
"""T-191d 人员管理权限实测：
① 准入：普通成员 / 小组组长 → 403；部门负责人 / 中心负责人 / 总经理 / 管理员 → 200；
② 范围：部门负责人只见本部门（含子组成员），scope='dept'；总经理/中心负责人 scope='all' 全量；
③ 图片直出范围校验：部门负责人看外部门人员图片 → 403，本部门 → 200；
④ 媒体管理范围校验：设置外部门人员头像 → 403，本部门 → 200；
⑤ 历史范围过滤：部门负责人看不到外部门条目；恢复外部门条目 → 403，本部门 → 200；
⑥ 快照级整包操作：部门负责人 → 403；总经理 → 200；
⑦ /api/me 能力位：can_manage_staff / staff_scope_all。
夹具 __t191d_ 前缀 + finally 清理 + 残留自查。
"""
import json, os, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
BASE = 'http://127.0.0.1:8100'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

P = '__t191d_'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'), data=data,
        method=method, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            ct = (r.headers.get('Content-Type') or '').lower()
            if 'json' not in ct:
                return r.status, {'_binary': True}
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}


def setup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.row_factory = sqlite3.Row
    cleanup()
    now = '2026-11-12 22:00:00'
    # 账号：中心负责人 / 部门负责人(D1) / 总经理 / 组长 / 普通成员；两部门各有 2 名成员
    accts = {'ch': 'editor', 'dl': 'editor', 'gm': 'editor', 'gl': 'editor',
             'pln': 'editor', 'd1a': 'editor', 'd1b': 'editor', 'd2a': 'editor'}
    for a, role in accts.items():
        c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
                  (P + a, hash_pw('x'), role))
    # 组织架构：中心 C → 部门 D1 → 组 G1；部门 D2
    c.execute("INSERT INTO org_nodes(id,name,node_type,parent_id,created_at) VALUES(900001,?,'center',0,?)",
              (P + '中心C', now))
    c.execute("INSERT INTO org_nodes(id,name,node_type,parent_id,created_at) VALUES(900002,?,'dept',900001,?)",
              (P + '部门D1', now))
    c.execute("INSERT INTO org_nodes(id,name,node_type,parent_id,created_at) VALUES(900003,?,'group',900002,?)",
              (P + '组G1', now))
    c.execute("INSERT INTO org_nodes(id,name,node_type,parent_id,created_at) VALUES(900004,?,'dept',900001,?)",
              (P + '部门D2', now))
    # 成员：D1a/D1b 归 D1；G1a 归 G1（组名入 departments）；D2a 归 D2
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '张一', P + 'd1a', P + '部门D1', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '张二', P + 'd1b', P + '部门D1,' + P + '组G1', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '李一', P + 'd2a', P + '部门D2', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '组长郭', P + 'gl', P + '组G1', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '部长杜', P + 'dl', P + '部门D1', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '主任陈', P + 'ch', P + '中心C', now))
    c.execute("INSERT INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '总经理高', P + 'gm', '', now))
    # 任命：部门负责人(dept_head@D1) / 中心负责人(center_head@C) / 总经理(gm) / 组长(group_leader@G1)
    def appt(node, acct, rk):
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (P + acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) VALUES(?,?,?,0,?)",
                  (node, mid, rk, now))
    appt(900002, 'dl', 'dept_head')
    appt(900001, 'ch', 'center_head')
    appt(900001, 'gm', 'gm')
    appt(900003, 'gl', 'group_leader')
    c.commit(); c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('users', 'username'), ('team_members', 'name'), ('team_members', 'account'),
                   ('org_nodes', 'name'), ('user_media_history', 'username')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    for t, col in (('user_media_snapshots', 'note'),):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (P.replace('_', e + '_') + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id BETWEEN 900001 AND 900004")
    c.execute("DELETE FROM org_nodes WHERE id BETWEEN 900001 AND 900004")
    c.commit()
    n = 0
    for t, col in (('users', 'username'), ('team_members', 'account'), ('org_nodes', 'name'),
                   ('user_media_history', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    n += c.execute("SELECT COUNT(*) FROM org_appointments WHERE node_id BETWEEN 900001 AND 900004").fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


PNG1 = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
        'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
PNG2 = PNG1.replace('BQDwAEh', 'BQDwAEi')


def main():
    t_admin = make_token('admin')
    t_ch = make_token(P + 'ch')      # 中心负责人
    t_dl = make_token(P + 'dl')      # 部门负责人（D1，含子组 G1）
    t_gm = make_token(P + 'gm')      # 总经理
    t_gl = make_token(P + 'gl')      # 小组组长（不开放）
    t_pln = make_token(P + 'pln')    # 普通成员
    t_d1a = make_token(P + 'd1a')    # D1 普通成员

    print('① 准入：403 / 200')
    ok(call('GET', '/api/staff/list', t_pln)[0] == 403, '普通成员 → 403')
    ok(call('GET', '/api/staff/list', t_gl)[0] == 403, '小组组长 → 403（部门负责人以下不开放）')
    s, r = call('GET', '/api/staff/list', t_dl)
    ok(s == 200 and r.get('scope') == 'dept', '部门负责人 → 200 scope=dept')
    s, r = call('GET', '/api/staff/list', t_ch)
    ok(s == 200 and r.get('scope') == 'all', '中心负责人 → 200 scope=all')
    s, r = call('GET', '/api/staff/list', t_gm)
    ok(s == 200 and r.get('scope') == 'all', '总经理 → 200 scope=all')
    s, r = call('GET', '/api/staff/list', t_admin)
    ok(s == 200 and r.get('scope') == 'all', '管理员 → 200 scope=all')

    print('② 范围：部门负责人只见本部门（含子组），看不到 D2 与未绑定账号')
    s, r = call('GET', '/api/staff/list', t_dl)
    names = [x['username'] or x['name'] for x in r.get('staff', [])]
    ok(P + 'd1a' in names and P + 'd1b' in names, '本部门成员可见（d1a/d1b）')
    ok(P + 'gl' in names, '子组成员可见（组长郭 departments 含组G1）')
    ok(P + 'd2a' not in names, '外部门成员不可见（d2a）')
    ok('admin' not in names, '未绑定账号不可见（admin）')
    s, r = call('GET', '/api/staff/list', t_gm)
    names = [x['username'] or x['name'] for x in r.get('staff', [])]
    ok(P + 'd2a' in names and 'admin' in names, '总经理全量（含外部门与未绑定账号）')

    print('③ 图片直出范围')
    ok(call('GET', '/api/staff/img/%sd1a/avatar' % P, t_dl)[0] in (200, 404),
       '本部门人员图片 → 放行（200/404 取决于是否上传）')
    ok(call('GET', '/api/staff/img/%sd2a/avatar' % P, t_dl)[0] == 403, '外部门人员图片 → 403')
    ok(call('GET', '/api/staff/img/%sd1a/avatar' % P, t_pln)[0] == 403, '普通成员访问图片 → 403')
    ok(call('GET', '/api/staff/img/%sd2a/avatar' % P, t_gm)[0] in (200, 404), '总经理 → 放行')

    print('④ 媒体管理范围')
    ok(call('POST', '/api/staff/media', t_dl,
            {'username': P + 'd2a', 'field': 'avatar', 'data': PNG1})[0] == 403,
       '部门负责人设置外部门人员头像 → 403')
    s, r = call('POST', '/api/staff/media', t_dl,
                {'username': P + 'd1a', 'field': 'avatar', 'data': PNG1})
    ok(s == 200 and r.get('changed'), '部门负责人设置本部门人员头像 → 200（实际 %s）' % s)
    s, r = call('POST', '/api/staff/media', t_dl,
                {'username': P + 'd1a', 'field': 'photo', 'data': PNG2})
    ok(s == 200, '部门负责人设置本部门人员照片 → 200')
    s, r = call('POST', '/api/staff/media', t_admin,
                {'username': P + 'd1a', 'field': 'avatar', 'data': PNG2})
    ok(s == 200, '管理员替换（产生可回滚历史）→ 200')

    print('⑤ 历史范围过滤与按条回滚')
    s, r = call('GET', '/api/staff/media/history', t_dl)
    us = {x['username'] for x in r.get('history', [])}
    ok(us <= {P + 'd1a'}, '部门负责人历史仅见本部门（实际 %s）' % {u.replace(P, '') for u in us})
    # 造一条**范围外**的历史（管理员改 d2a 头像）→ 部门负责人不得恢复
    call('POST', '/api/staff/media', t_admin,
         {'username': P + 'd2a', 'field': 'avatar', 'data': PNG1})
    s, r = call('GET', '/api/staff/media/history', t_admin)
    hid_out = next(x['id'] for x in r['history'] if x['username'] == P + 'd2a')
    ok(call('POST', '/api/staff/media/history/%d/restore' % hid_out, t_dl)[0] == 403,
       '部门负责人恢复范围外条目 → 403')
    ok(call('POST', '/api/staff/media/history/%d/restore' % hid_out, t_pln)[0] == 403,
       '普通成员恢复任何条目 → 403')
    s, r = call('GET', '/api/staff/media/history', t_dl)
    us = {x['username'] for x in r.get('history', [])}
    ok(P + 'd2a' not in us, '范围外条目不出现在部门负责人的历史清单里')
    s, r = call('GET', '/api/staff/media/history?user=' + P + 'd1a', t_dl)
    ok(s == 200, '按用户过滤历史 → 200')

    print('⑥ 快照级整包操作')
    ok(call('GET', '/api/staff/media/snapshots', t_dl)[0] == 403, '部门负责人查快照 → 403')
    ok(call('POST', '/api/staff/media/snapshots', t_dl, {'note': P + 'x'})[0] == 403,
       '部门负责人创建快照 → 403')
    s, r = call('POST', '/api/staff/media/snapshots', t_gm, {'note': P + '快照G'})
    ok(s == 200, '总经理创建快照 → 200')
    if s == 200:
        ok(call('POST', '/api/staff/media/snapshots/%d/restore' % r['id'], t_dl)[0] == 403,
           '部门负责人回滚快照 → 403')
        ok(call('POST', '/api/staff/media/snapshots/%d/restore' % r['id'], t_gm)[0] == 200,
           '总经理回滚快照 → 200')

    print('⑦ /api/me 能力位')
    ok(call('GET', '/api/me', t_dl)[1].get('can_manage_staff') is True
       and call('GET', '/api/me', t_dl)[1].get('staff_scope_all') is False,
       '部门负责人：can_manage_staff=True staff_scope_all=False')
    ok(call('GET', '/api/me', t_gm)[1].get('staff_scope_all') is True, '总经理：staff_scope_all=True')
    ok(call('GET', '/api/me', t_pln)[1].get('can_manage_staff') is False, '普通成员：can_manage_staff=False')
    ok(call('GET', '/api/me', t_gl)[1].get('can_manage_staff') is False, '小组组长：can_manage_staff=False')


if __name__ == '__main__':
    setup()
    try:
        main()
    finally:
        left = cleanup()
    fails = [m for c, m in N if not c]
    print('\n===== 结果: %d/%d 通过，残留=%d =====' % (len(N) - len(fails), len(N), left), flush=True)
    for m in fails:
        print('FAIL: ' + m)
    sys.exit(1 if (fails or left) else 0)
