# -*- coding: utf-8 -*-
"""审查王伟娜·统筹组任命在本地库的实际数据形态（legacy 串是否仍挂统筹）。"""
import sqlite3

c = sqlite3.connect('src/app.db')
c.row_factory = sqlite3.Row
n = c.execute("SELECT id, name, node_type, wg_id FROM org_nodes WHERE name='统筹'").fetchone()
print('统筹节点:', dict(n) if n else None)
nid = n['id'] if n else None
for r in c.execute("SELECT m.id, m.name, m.workgroups, a.role_key FROM team_members m"
                   " LEFT JOIN org_appointments a ON a.member_id=m.id AND a.node_id=?"
                   " WHERE m.name='王伟娜'", (nid,)):
    print('成员:', dict(r))
for r in c.execute("SELECT a.id, a.member_id, a.role_key, m.name FROM org_appointments a"
                   " JOIN team_members m ON m.id=a.member_id WHERE a.node_id=?", (nid,)):
    print('统筹任命:', dict(r))
# 王伟娜的全部任命
for r in c.execute("SELECT a.node_id, n.name, n.node_type, a.role_key FROM org_appointments a"
                   " JOIN org_nodes n ON n.id=a.node_id JOIN team_members m ON m.id=a.member_id"
                   " WHERE m.name='王伟娜'"):
    print('王伟娜任命:', dict(r))
c.close()
