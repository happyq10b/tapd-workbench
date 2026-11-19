# -*- coding: utf-8 -*-
"""孤儿任命成因盘点（只读）：member_id 分布 vs 现存成员 id 范围 vs 导入时间线"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else 'src/app.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

def q(sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]

print('=== 1. 孤儿任命的 member_id 范围与数量 ===')
r = q("""SELECT MIN(a.member_id) AS min_id, MAX(a.member_id) AS max_id, COUNT(*) AS n
         FROM org_appointments a
         WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)""")
print(r)
print('=== 2. 现存 team_members 的 id 范围 ===')
r = q("SELECT MIN(id) AS min_id, MAX(id) AS max_id, COUNT(*) AS n FROM team_members")
print(r)
print('=== 3. 现存成员 id 的分布（判断是否重新导入后 id 重排）===')
r = q("""SELECT (id/100)*100 AS id段, COUNT(*) AS n FROM team_members GROUP BY id段 ORDER BY id段""")
print(r)
print('=== 4. 孤儿 member_id 分布（每 100 一段）===')
r = q("""SELECT (a.member_id/100)*100 AS id段, COUNT(*) AS n
         FROM org_appointments a
         WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
         GROUP BY id段 ORDER BY id段""")
print(r)
print('=== 5. team_members 最近创建时间（导入时间线）===')
r = q("""SELECT substr(created_at,1,10) AS day, COUNT(*) AS n, MIN(id) AS min_id, MAX(id) AS max_id
         FROM team_members GROUP BY day ORDER BY day""")
print(r)
print('=== 6. 孤儿任命的 node 分布（前 10）===')
r = q("""SELECT a.node_id, n.name, COUNT(*) AS n FROM org_appointments a
         LEFT JOIN org_nodes n ON n.id=a.node_id
         WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
         GROUP BY a.node_id ORDER BY n DESC LIMIT 10""")
print(r)
print('=== 7. 孤儿任命的 role_key ===')
r = q("""SELECT a.role_key, COUNT(*) AS n FROM org_appointments a
         WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
         GROUP BY a.role_key""")
print(r)
print('=== 8. 孤儿任命的创建时间范围 ===')
r = q("""SELECT MIN(created_at) AS 最早, MAX(created_at) AS 最晚 FROM org_appointments a
         WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)""")
print(r)
c.close()
