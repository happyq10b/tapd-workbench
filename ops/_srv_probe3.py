# -*- coding: utf-8 -*-
"""服务器取证③：WAL 状态、checkpoint 合并前后对比、两环境 init_db 修复标记。"""
import sqlite3, subprocess, os

PROD = '/opt/tapd-workbench/app.db'

print('== ① 生产库文件状态（主文件/WAL/SHM）==')
os.system('ls -la %s*' % PROD)

print('== ② checkpoint 前读取（主+WAL 合并视图）==')
c = sqlite3.connect(PROD, timeout=20)
c.row_factory = sqlite3.Row
wwn = c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                " WHERE a.node_id=12 AND m.name='王伟娜'").fetchone()[0]
print('  统筹王伟娜 =', wwn, '（有=覆盖后旧数据 / 无=删除还在 WAL）')
print('  audit max ts =', c.execute('SELECT MAX(ts) FROM audit_logs').fetchone()[0])

print('== ③ 主动 checkpoint(PASSIVE，服务运行中安全) ==')
try:
    r = c.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
    print('  busy=log, log=合并页数, checkpointed=', r)
except Exception as e:
    print('  checkpoint 异常:', e)
c.close()

c = sqlite3.connect(PROD, timeout=20)
wwn2 = c.execute("SELECT COUNT(*) FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                 " WHERE a.node_id=12 AND m.name='王伟娜'").fetchone()[0]
print('== ④ checkpoint 后重读 ==')
print('  统筹王伟娜 =', wwn2, '（若由「有」变「无」= 用户的删除一直在 WAL 里）')
c.close()

print('== ⑤ 两环境 init_db 修复标记（acnt 条件）==')
for f in ('/opt/tapd-workbench/app/init_db.py', '/opt/tapd-dev/app/init_db.py'):
    try:
        t = open(f, encoding='utf-8').read()
        print('  ', f, '→ acnt 修复:', 'acnt' in t, '；g in names 修复:', 'if g in names' in open(
            f.replace('init_db.py', 'app.py'), encoding='utf-8').read())
    except Exception as e:
        print('  ', f, 'ERR', e)
