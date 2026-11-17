# -*- coding: utf-8 -*-
"""T-204m 复现实验：删除统筹组员任命 → 重启服务 → 验证「复活」是否发生。
守则 §3.4：D1 已备份（ops/backup_db_20261117_repro.db）；D3 行数与串全程记录。"""
import sys, os, sqlite3, subprocess, json, urllib.request

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'


def state(label):
    c = sqlite3.connect('src/app.db')
    c.row_factory = sqlite3.Row
    appt = c.execute("SELECT id FROM org_appointments WHERE node_id=12 AND member_id=17").fetchone()
    wg = c.execute("SELECT workgroups FROM team_members WHERE id=17").fetchone()[0]
    n = c.execute('SELECT COUNT(*) FROM org_appointments').fetchone()[0]
    c.close()
    print(f"[{label}] 统筹任命={'在(id=%s)' % appt['id'] if appt else '无'} "
          f"legacy串={wg!r} 全表={n}", flush=True)
    return bool(appt)


def restart():
    subprocess.run([r'ops\.localvenv\Scripts\python.exe', 'ops/local-ctl.py', 'restart'],
                   capture_output=True, timeout=120)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2)
            return
        except Exception:
            import time
            time.sleep(0.5)


def del_appt():
    sys.path.insert(0, 'src')
    from app.app import make_token
    c = sqlite3.connect('src/app.db')
    aid = c.execute("SELECT id FROM org_appointments WHERE node_id=12 AND member_id=17").fetchone()
    c.close()
    if not aid:
        print('（无统筹任命可删）')
        return False
    req = urllib.request.Request(BASE + '/api/org/appointments/%d' % aid[0], method='DELETE')
    req.add_header('Authorization', 'Bearer ' + make_token('admin'))
    urllib.request.urlopen(req, timeout=15).read()
    return True


print('== ① 删除前基线 ==', flush=True)
state('删除前')
print('== ② 删除任命 ==', flush=True)
print('删除执行:', del_appt(), flush=True)
state('删除后')
print('== ③ 重启服务（触发 init_db / _migrate_org）==', flush=True)
restart()
print('== ④ 重启后（用户复现的「复活」点）==', flush=True)
alive = state('重启后')
print('\n结论：', '❌ 复活复现（init_db 回填）' if alive else '✅ 未复活', flush=True)
sys.exit(0)
