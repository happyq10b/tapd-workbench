# -*- coding: utf-8 -*-
"""恢复检查：从 CSV owner 反推被误删/改名成员的原名"""
import csv, io, subprocess

data = open('data/全部看板_2026年度_总宽表.csv', encoding='utf-8-sig').read()
rows = list(csv.DictReader(io.StringIO(data)))
csv_names = set()
for r in rows:
    for o in (r.get('owner') or '').split(';'):
        o = o.strip()
        if o:
            csv_names.add(o)

PY = ("cd /root/tapd_webapp && venv/bin/python -u -c "
      "\"import sqlite3; db=sqlite3.connect('/root/tapd_webapp/app.db'); "
      "[print(r[0], '|', r[1]) for r in db.execute('SELECT id, name FROM team_members')]\"")
out = subprocess.run(['wsl.exe', '-u', 'root', '-e', 'bash', '-c', PY],
                     capture_output=True, text=True).stdout
cur = {}
for line in out.splitlines():
    if '|' in line:
        i, n = line.split('|', 1)
        cur[n.strip()] = i.strip()
print('当前成员数:', len(cur))
print('当前成员:', list(cur.keys()))
missing = sorted(csv_names - set(cur.keys()))
print('CSV有但当前成员表缺失的名字:', missing)
