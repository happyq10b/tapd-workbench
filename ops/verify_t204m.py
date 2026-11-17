# -*- coding: utf-8 -*-
"""验证①：空 org_appointments 的库 → init_db 仍正常回填（迁移语义保留）。
验证②：单步调用 _org_sync_member_legacy 观察 Bug B（legacy 串清理失效）。"""
import sys, os, shutil, sqlite3

sys.path.insert(0, 'src')
sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

# ---------- 验证①：副本库空表 → 回填 ----------
shutil.copy2('src/app.db', 'ops/_repro_empty.db')
c = sqlite3.connect('ops/_repro_empty.db')
c.execute('DELETE FROM org_appointments')
c.commit()
c.close()
import app.init_db as idb
idb.DB_FILE = 'ops/_repro_empty.db'     # 指向副本
idb.init_db()
c = sqlite3.connect('ops/_repro_empty.db')
n = c.execute('SELECT COUNT(*) FROM org_appointments').fetchone()[0]
wwn = c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                " WHERE m.name='王伟娜' AND a.role_key='member'").fetchone()[0]
c.close()
print(f'验证① 空表首迁移：回填 {n} 条任命（王伟娜组员 {wwn} 条）→', '✓ 语义保留' if n > 0 else '✗ 回填失效！')

# ---------- 验证②：单步 _org_sync_member_legacy ----------
from app.app import _org_sync_member_legacy, dbq
row = dbq('SELECT workgroups FROM team_members WHERE id=?', (17,))
before = row[0]['workgroups']
print(f'验证② 调用前串 = {before!r}')
# 当前王伟娜剩余 group 任命
rows = dbq('''SELECT n.name FROM org_appointments a JOIN org_nodes n ON n.id=a.node_id
              WHERE a.member_id=17 AND n.node_type IN ('group','special')''')
names = set(r['name'] for r in rows)
print(f'         剩余 group 任职 = {names}')
_org_sync_member_legacy(17)
row = dbq('SELECT workgroups FROM team_members WHERE id=?', (17,))
after = row[0]['workgroups']
print(f'         调用后串 = {after!r}')
removed = set(before.split(';')) - set(after.split(';'))
added = set(after.split(';')) - set(before.split(';'))
print(f'         移除={removed or "无"} 新增={added or "无"}')
