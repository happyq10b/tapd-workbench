# -*- coding: utf-8 -*-
"""补回王伟娜被旧 bug 误删的收入组串（触发收入组节点侧 legacy 回写）+ 全量核验。"""
import sys, os

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import _org_sync_legacy, dbq

_org_sync_legacy(7)   # 收入组节点侧回写：现有组员串补节点名
row = dbq('SELECT workgroups FROM team_members WHERE id=?', (17,))
print('王伟娜修正后串 =', repr(row[0]['workgroups']))
c = sqlite3_connect = __import__('sqlite3').connect('src/app.db')
n_all = c.execute('SELECT COUNT(*) FROM org_appointments').fetchone()[0]
wwn = c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                " WHERE a.node_id=12 AND m.name='王伟娜'").fetchone()[0]
c.close()
print('org_appointments 全表 =', n_all, '；王伟娜统筹任命 =', wwn, '（0=保持删除状态）')
