# -*- coding: utf-8 -*-
"""#153 按《人员资料.xlsx》姓名匹配，填充平台 users 表基本信息（不含手机号）"""
import csv, io, re, sqlite3, datetime

SRC = 'ops/.tmp_renyuan.csv'
DB = 'src/app.db'

def to_iso(v):
    v = (v or '').strip()
    if not v:
        return ''
    m = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})$', v)
    if m:
        return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', v)
    if m:
        return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
    raise ValueError('bad date: %r' % v)

rows = list(csv.DictReader(io.open(SRC, encoding='utf-8')))
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
tm = {r['name'].strip(): dict(r) for r in c.execute('SELECT id,name,account FROM team_members')}

updated, skipped = [], []
for r in rows:
    name = r['姓名'].strip()
    m = tm.get(name)
    if not m or not (m['account'] or '').strip():
        skipped.append((name, '无成员/无账号绑定'))
        continue
    rec = {
        'gender': r['性别'].strip(),
        'hire_date': to_iso(r['入司时间']),
        'birth_date': to_iso(r['出生日期']),
        'native_province': r['籍贯省'].strip()[:20],
        'native_city': r['籍贯市'].strip()[:20],
        'political_status': r['政治面貌'].strip()[:20],
    }
    cur = c.execute('SELECT gender, hire_date, birth_date, native_province, native_city, political_status'
                    ' FROM users WHERE username=?', (m['account'],)).fetchone()
    if cur is None:
        skipped.append((name, 'users 表无行'))
        continue
    same = all((cur[k] or '') == rec[k] for k in rec)
    if same:
        skipped.append((name, '已是最新，跳过'))
        continue
    c.execute('UPDATE users SET gender=?, hire_date=?, birth_date=?, native_province=?,'
              ' native_city=?, political_status=? WHERE username=?',
              (rec['gender'], rec['hire_date'], rec['birth_date'], rec['native_province'],
               rec['native_city'], rec['political_status'], m['account']))
    updated.append((name, m['account'], rec))

c.commit()
c.close()

print('更新 %d 人，跳过 %d 人' % (len(updated), len(skipped)))
for name, reason in skipped:
    print('  跳过: %s（%s）' % (name, reason))
for name, acc, rec in updated[:5]:
    print('  示例: %s(%s) %s' % (name, acc, rec))
