# -*- coding: utf-8 -*-
"""dev 环境端到端验证修复：删除统筹任命（写 WAL）→ tapd snap dev（修复版）→ 重启 → 不复活。
dev 库含王伟娜统筹任命（用户 09:23 推的快照数据）。"""
import sqlite3, subprocess, sys

DB = '/opt/tapd-dev/app.db'
SVC = 'tapd-dev'

def q(sql, *p):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(sql, p)]
    c.close()
    return rows

def exe(sql, *p):
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute(sql, p)
    c.commit()
    c.close()

def state(label):
    rows = q("SELECT a.id, m.name FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
             " WHERE a.node_id=12 AND m.name='王伟娜'")
    n = q('SELECT COUNT(*) AS n FROM org_appointments')[0]['n']
    print(f"[{label}] 统筹王伟娜={'在(id=%s)' % rows[0]['id'] if rows else '无'} 全表={n}", flush=True)
    return bool(rows)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120).stdout

print('== ① 基线 ==', flush=True)
existed = state('删除前')
if not existed:
    print('dev 库无王伟娜统筹任命，补造一条（模拟初始状态）')
    exe("INSERT INTO org_appointments (node_id, member_id, role_key, is_primary)"
        " SELECT 12, id, 'member', 0 FROM team_members WHERE name='王伟娜'")
    state('补造后')

print('== ② 删除（写 WAL，服务运行中）==', flush=True)
exe("DELETE FROM org_appointments WHERE node_id=12 AND member_id=17")
state('删除后')

print('== ③ tapd snap dev（修复版 do_snap：checkpoint 而非 rm）==', flush=True)
print(sh('/usr/local/bin/tapd snap dev')[-200:], flush=True)

print('== ④ 重启 dev 服务（触发 init_db）==', flush=True)
sh('systemctl restart %s; sleep 4' % SVC)
state('重启后')

final = state('复查')
print('\n结论：', '✅ 修复生效——删除保持、不再复活' if not final else '❌ 仍复活', flush=True)
