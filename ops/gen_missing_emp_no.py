# -*- coding: utf-8 -*-
"""#155 为未匹配到人员资料（xlsx）的成员随机生成 ID（no+5位随机数），全局唯一，幂等可重跑
判定口径：姓名不在人员资料.xlsx 中 → 视为未匹配（无论当前 emp_no 是回填的内部编号还是空）"""
import csv, io, json, os, random, sqlite3

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
XLSX_JSON = os.environ.get('TEMP', '.') + '/renyuan2.json'   # edsdk 读取的 xlsx 数据缓存

d = json.load(io.open(XLSX_JSON, encoding='utf-8'))
xl_names = set()
for r in csv.DictReader(io.StringIO(d.get('csv_data', ''))):
    xl_names.add(r['姓名'].strip())

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

def occupied():
    s = set()
    for r in c.execute('SELECT id, emp_no FROM team_members'):
        if r['emp_no']:
            s.add(r['emp_no'])
        s.add(str(r['id']))
    return s

occ = occupied()
targets = [dict(r) for r in c.execute('SELECT id, name, emp_no FROM team_members') if r['name'].strip() not in xl_names]
print('未匹配成员: %d 人' % len(targets))

for m in targets:
    old = m['emp_no'] or '(空)'
    while True:
        cand = 'no%d' % random.randint(10000, 99999)
        if cand not in occ:
            break
    occ.add(cand)
    c.execute('UPDATE team_members SET emp_no=? WHERE id=?', (cand, m['id']))
    print('  %s（成员%d）：%s → %s' % (m['name'], m['id'], old, cand))

c.commit()
dup = c.execute('SELECT COUNT(*) FROM (SELECT emp_no FROM team_members WHERE emp_no<>"" GROUP BY emp_no HAVING COUNT(*)>1)').fetchone()[0]
total = c.execute('SELECT COUNT(*) FROM team_members').fetchone()[0]
c.close()
print('成员总数: %d；工号重复: %d' % (total, dup))
