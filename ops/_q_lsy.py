# -*- coding: utf-8 -*-
"""只读排查：线上 lsy 的架构身份与 arch_scope 派生"""
import sqlite3
c = sqlite3.connect('/opt/tapd-workbench/app.db')
c.row_factory = sqlite3.Row

print('=== lsy 用户 ===')
for r in c.execute("SELECT username, role, allowed_boards FROM users WHERE username LIKE '%lsy%'"):
    print(dict(r))
print('=== lsy 成员绑定 ===')
for r in c.execute("SELECT id, name, account FROM team_members WHERE account LIKE '%lsy%'"):
    print(dict(r))
print('=== lsy 任命 ===')
for r in c.execute("""SELECT a.node_id, n.name, n.node_type, a.role_key, a.is_primary
                      FROM org_appointments a
                      JOIN team_members m ON m.id=a.member_id
                      JOIN org_nodes n ON n.id=a.node_id
                      WHERE m.account LIKE '%lsy%'"""):
    print(dict(r))
print('=== org_nodes.owner 含 lsy ===')
for r in c.execute("SELECT id, name, node_type, owner FROM org_nodes WHERE owner LIKE '%lsy%'"):
    print(dict(r))
print('=== workgroups.leader 含 lsy ===')
for r in c.execute("SELECT id, name, leader FROM workgroups WHERE leader LIKE '%林姝言%' OR leader LIKE '%lsy%'"):
    print(dict(r))
