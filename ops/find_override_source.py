# -*- coding: utf-8 -*-
"""定位覆盖生产库的快照来源：遍历本地快照，比对 audit_logs 行数与文件大小。"""
import sqlite3, os, glob, datetime

root = 'data/db-snapshots'
print(f"{'快照':<44}{'audit':>7}{'大小':>10}  快照文件时间")
print('-' * 84)
for d in sorted(glob.glob(os.path.join(root, '*')), reverse=True):
    db = os.path.join(d, 'app.db')
    if not os.path.isfile(db):
        continue
    try:
        c = sqlite3.connect(db)
        n = c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]
        c.close()
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(db))
        print(f"{os.path.basename(d):<44}{n:>7}{os.path.getsize(db):>10}  {mt:%m-%d %H:%M}")
    except Exception as e:
        print(os.path.basename(d), 'ERR', e)
c = sqlite3.connect('src/app.db')
print('-' * 84)
print('本地现库 audit =', c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0],
      ' 大小 =', os.path.getsize('src/app.db'))
c.close()
