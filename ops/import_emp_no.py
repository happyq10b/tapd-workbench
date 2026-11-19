# -*- coding: utf-8 -*-
"""#153b 按《人员资料.xlsx》姓名匹配，填充 team_members.emp_no（工号）"""
import csv, io, sqlite3

rows = list(csv.DictReader(io.open('ops/.tmp_renyuan.csv', encoding='utf-8')))
c = sqlite3.connect('src/app.db')
c.row_factory = sqlite3.Row
tm = {r['name'].strip(): dict(r) for r in c.execute('SELECT id, name, emp_no FROM team_members')}

updated, skipped = [], []
for r in rows:
    name = r['姓名'].strip()
    emp_no = r['ID'].strip()
    m = tm.get(name)
    if not m:
        skipped.append((name, '平台无此成员'))
        continue
    if (m['emp_no'] or '') == emp_no:
        skipped.append((name, '已是最新，跳过'))
        continue
    c.execute('UPDATE team_members SET emp_no=? WHERE id=?', (emp_no, m['id']))
    updated.append((name, m['id'], emp_no, m['emp_no'] or '(空)'))

c.commit()
cnt = c.execute("SELECT COUNT(*) FROM team_members WHERE emp_no<>''").fetchone()[0]
c.close()

print('工号更新 %d 人，跳过 %d 人；平台已有工号成员总数=%d' % (len(updated), len(skipped), cnt))
for name, reason in skipped:
    print('  跳过: %s（%s）' % (name, reason))
for name, mid, new, old in updated[:5]:
    print('  示例: %s（成员%d：%s → %s）' % (name, mid, old, new))
