# -*- coding: utf-8 -*-
"""深挖：删除统筹任命后 legacy 串异常（移除了收入组、保留统筹）——查触发器/任命状态/函数行为。"""
import sqlite3, sys, os
sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

c = sqlite3.connect('src/app.db')
c.row_factory = sqlite3.Row
print('== 触发器 ==')
for r in c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'"):
    print(r['name'], ':', (r['sql'] or '')[:200])
print('== 王伟娜(id=17) 当前全部任命 ==')
for r in c.execute("SELECT a.id, a.node_id, n.name, n.node_type, a.role_key FROM org_appointments a"
                   " JOIN org_nodes n ON n.id=a.node_id WHERE a.member_id=17"):
    print('  ', dict(r))
print('== 收入组节点 ==')
for r in c.execute("SELECT id, name, node_type, wg_id FROM org_nodes WHERE name LIKE '%收入%'"):
    print('  ', dict(r))
print('== 王伟娜 legacy 串 ==')
print('  ', c.execute("SELECT workgroups FROM team_members WHERE id=17").fetchone()[0])
print('== 同名成员检查 ==')
for r in c.execute("SELECT id, name, account, workgroups FROM team_members WHERE name LIKE '%王伟娜%'"):
    print('  ', dict(r))
c.close()

# 直接单步调用 _org_sync_member_legacy 观察 names 与 keep
sys.path.insert(0, 'src')
from app import app as appmod
rows = appmod.dbq('''SELECT n.name FROM org_appointments a JOIN org_nodes n ON n.id=a.node_id
              WHERE a.member_id=? AND n.node_type IN ('group','special')''', (17,))
names = set(r['name'] for r in rows)
print('== 单步 _org_sync_member_legacy(17)：剩余 group 任职 names =', names)
row = appmod.dbq('SELECT workgroups FROM team_members WHERE id=?', (17,))
gs = [x.strip() for x in (row[0]['workgroups'] or '').split(';') if x.strip()]
keep = [g for g in gs if g not in names]
print('== gs =', gs, '→ keep =', keep)
