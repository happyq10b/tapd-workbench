# -*- coding: utf-8 -*-
"""T-013c 离岗状态 API 测试：名单剔除 / 筛选不可见 / 历史数据不动 / 删除同口径"""
import json, os, sqlite3, sys, urllib.parse, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
RES = []


def ok(cond, msg):
    RES.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    path = urllib.parse.quote(path, safe='/?&=')
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk,
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


MID, ACC, MNAME, CARD = 990413, '__t_lg_u', '__t_离岗成员__', '__t_lg_card'
# 夹具锚点节点（任取一个 dept 节点 + 任一 workgroup）
c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
node = c.execute("SELECT id,name FROM org_nodes WHERE node_type='dept' ORDER BY id LIMIT 1").fetchone()
NID, NNAME = node
wg = c.execute("SELECT id FROM workgroups ORDER BY id LIMIT 1").fetchone()
WID = wg[0]
snap = {
    'node': c.execute('SELECT owner,participants FROM org_nodes WHERE id=?', (NID,)).fetchone(),
    'wg_leader': c.execute('SELECT leader FROM workgroups WHERE id=?', (WID,)).fetchone()[0],
}
c.close()

try:
    tk = make_token('admin')
    print('【setup 夹具】', flush=True)
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (ACC, hash_pw('Xx12345678')))
    c.execute("INSERT INTO team_members (id,name,account,status,departments) VALUES (?,?,?,?,?)",
              (MID, MNAME, ACC, '', NNAME))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?, 'backbone',1)", (NID, MID))
    # 参与人加入节点 + 负责人名单元
    row = c.execute('SELECT participants FROM org_nodes WHERE id=?', (NID,)).fetchone()
    parts = [x for x in (row[0] or '').split(',') if x.strip()]
    if ACC not in parts:
        parts.append(ACC)
        c.execute('UPDATE org_nodes SET participants=? WHERE id=?', (','.join(parts), NID))
    c.execute("UPDATE cards SET deleted=0 WHERE card_id=?", (CARD,))
    c.execute("INSERT OR REPLACE INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id) "
              "VALUES (?,'__t_lg_b','__t_离岗测试看板','__t_板块','__t_历史事项','open',?, 'w1',datetime('now'),0,'')", (CARD, MNAME))
    c.commit(); c.close()

    st, d = api(tk, 'GET', '/api/filter-options')
    ok(MNAME in d.get('people', []), '夹具就位：负责人筛选候选含该成员（历史数据在）')

    print('【① 设为离岗 → 任命/参与人/负责人名单剔除】', flush=True)
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'status': 'departed'})
    ok(st == 200, '保存成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    n_appt = c.execute('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,)).fetchone()[0]
    ok(n_appt == 0, 'org_appointments 任命已剔除（%d 条残留）' % n_appt)
    parts = c.execute('SELECT participants FROM org_nodes WHERE id=?', (NID,)).fetchone()[0]
    ok(ACC not in [x.strip() for x in parts.split(',')], '节点参与人已剔除该账号')
    st_row = c.execute('SELECT status FROM team_members WHERE id=?', (MID,)).fetchone()[0]
    ok(st_row == 'departed', 'status 已落库')
    c.close()

    print('【② 筛选候选不再可见，历史数据保持不变】', flush=True)
    st, d = api(tk, 'GET', '/api/filter-options')
    ok(MNAME not in d.get('people', []), '负责人筛选候选已无该成员')
    st, d = api(tk, 'GET', '/api/cards?q=__t_历史事项')
    ok(d.get('total', 0) == 1 and d['cards'][0]['owner'] == MNAME, '历史事项照常显示（owner 名字不变）')
    st, d = api(tk, 'GET', '/api/team')
    mem = next((m for m in d['members'] if m['id'] == MID), None)
    ok(mem and mem.get('status') == 'departed', '/api/team 下发 status=departed（账号管理可见可恢复）')

    print('【③ 中心全员补齐不回流】', flush=True)
    # 触发一次部门同步（补齐在 _ensure_center_participants_all）后，中心参与人不应含离岗账号
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'departments': []})
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    center = c.execute("SELECT participants FROM org_nodes WHERE node_type='center' ORDER BY id LIMIT 1").fetchone()[0]
    ok(ACC not in [x.strip() for x in center.split(',')], '离岗账号未回流中心参与人')
    c.close()

    print('【④ 恢复在岗 → status 复位，名单不自动回填】', flush=True)
    st, d = api(tk, 'PUT', '/api/team/%d' % MID, {'name': MNAME, 'status': ''})
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    st_row = c.execute('SELECT status FROM team_members WHERE id=?', (MID,)).fetchone()[0]
    n_appt = c.execute('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,)).fetchone()[0]
    ok(st_row == '' and n_appt == 0, '状态复位且名单未回填（需重新任命）')
    c.close()

    print('【⑤ 删除成员 → 同口径剔除 + 名单清理】', flush=True)
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute('UPDATE team_members SET status="" WHERE id=?', (MID,))
    # 重新造任命与参与人，验证删除路径
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?, 'backbone',1)", (NID, MID))
    row = c.execute('SELECT participants FROM org_nodes WHERE id=?', (NID,)).fetchone()
    parts = [x for x in (row[0] or '').split(',') if x.strip()]
    if ACC not in parts:
        parts.append(ACC)
        c.execute('UPDATE org_nodes SET participants=? WHERE id=?', (','.join(parts), NID))
    c.commit(); c.close()
    st, d = api(tk, 'DELETE', '/api/team/%d' % MID)
    ok(st == 200, '删除成功')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    ok(c.execute('SELECT COUNT(*) FROM team_members WHERE id=?', (MID,)).fetchone()[0] == 0, '成员已删除')
    ok(c.execute('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,)).fetchone()[0] == 0, '任命已剔除')
    parts = c.execute('SELECT participants FROM org_nodes WHERE id=?', (NID,)).fetchone()[0]
    ok(ACC not in [x.strip() for x in parts.split(',')], '参与人已剔除')
    c.close()
    st, d = api(tk, 'GET', '/api/cards?q=__t_历史事项')
    ok(d.get('total', 0) == 1, '删除后历史事项仍完整显示')

finally:
    # ---------- cleanup：夹具零残留 + 还原节点快照 ----------
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE member_id=?", (MID,))
    c.execute("DELETE FROM team_members WHERE id=?", (MID,))
    c.execute("DELETE FROM users WHERE username=?", (ACC,))
    c.execute("DELETE FROM cards WHERE card_id=?", (CARD,))
    c.execute("DELETE FROM boards WHERE board_id='__t_lg_b'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_lg_b'")
    c.execute('UPDATE org_nodes SET owner=?, participants=? WHERE id=?',
              (snap['node'][0], snap['node'][1], NID))
    c.execute('UPDATE workgroups SET leader=? WHERE id=?', (snap['wg_leader'], WID))
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM team_members WHERE id=?", (MID,)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (ACC,)).fetchone()[0]
    n3 = c.execute("SELECT COUNT(*) FROM cards WHERE card_id=?", (CARD,)).fetchone()[0]
    n4 = c.execute("SELECT COUNT(*) FROM app_settings WHERE key LIKE '__t_lg%'").fetchone()[0]
    print('夹具残留检查: members=%d users=%d cards=%d settings=%d' % (n1, n2, n3, n4), flush=True)
    c.close()

n = sum(RES)
print('结果: PASS=%d/%d' % (n, len(RES)), flush=True)
sys.exit(0 if n == len(RES) else 1)
