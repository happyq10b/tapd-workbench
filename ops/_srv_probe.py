# -*- coding: utf-8 -*-
"""服务器端取证：统筹组任命状态、王伟娜任命行 id、以及最近的删除请求痕迹。"""
import sqlite3

DB = '/opt/tapd-workbench/app.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print('== 统筹组(node 12)当前任命 ==')
for r in c.execute("SELECT a.id, a.member_id, m.name, a.role_key FROM org_appointments a"
                   " JOIN team_members m ON m.id=a.member_id WHERE a.node_id=12"):
    print('  ', dict(r))
print('== 王伟娜(member 17)全部任命 ==')
for r in c.execute("SELECT a.id, a.node_id, n.name, a.role_key FROM org_appointments a"
                   " JOIN org_nodes n ON n.id=a.node_id WHERE a.member_id=17"):
    print('  ', dict(r))
print('== org_appointments 最大 id ==')
print('  ', c.execute('SELECT MAX(id) FROM org_appointments').fetchone()[0])
print('== 王伟娜 team_members.workgroups ==')
print('  ', c.execute("SELECT workgroups FROM team_members WHERE id=17").fetchone()[0])
print('== 审计日志中统筹/王伟娜相关最近5条 ==')
for r in c.execute("SELECT ts, username, action, detail FROM audit_logs"
                   " WHERE detail LIKE '%王伟娜%' OR detail LIKE '%统筹%'"
                   " ORDER BY id DESC LIMIT 5"):
    print('  ', dict(r))
c.close()
