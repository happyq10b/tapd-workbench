# -*- coding: utf-8 -*-
"""服务器取证②：生产库数据时点指纹 + 发布快照内容比对。"""
import sqlite3, glob, os

DB = '/opt/tapd-workbench/app.db'
c = sqlite3.connect(DB)
print('== 生产库指纹 ==')
print('audit 行数:', c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0])
print('audit max id:', c.execute('SELECT MAX(id) FROM audit_logs').fetchone()[0])
print('audit 最近6条时间戳:')
for r in c.execute('SELECT ts, username, action FROM audit_logs ORDER BY id DESC LIMIT 6'):
    print('  ', r)
print('org_appointments 行数:', c.execute('SELECT COUNT(*) FROM org_appointments').fetchone()[0])
print('统筹王伟娜:', c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m"
                             " ON m.id=a.member_id WHERE a.node_id=12 AND m.name='王伟娜'").fetchone()[0])
c.close()

print('\n== 各发布快照指纹 ==')
for d in sorted(glob.glob('/var/backups/tapd-workbench/release/prod/prod-2026111*'), reverse=True)[:6]:
    db = os.path.join(d, 'app.db')
    if not os.path.isfile(db):
        print(os.path.basename(d), '无 app.db')
        continue
    c = sqlite3.connect(db)
    n = c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]
    mx = c.execute('SELECT MAX(id) FROM audit_logs').fetchone()[0]
    wwn = c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                    " WHERE a.node_id=12 AND m.name='王伟娜'").fetchone()[0]
    c.close()
    print(f"{os.path.basename(d):36} audit={n:>6} max_id={mx:>6} 统筹王伟娜={'在' if wwn else '无'}")
