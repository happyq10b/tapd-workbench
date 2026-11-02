import sqlite3
c = sqlite3.connect('src/app.db')
found = False
ESC = chr(92)          # 反斜杠，用 chr 构造，避免多层转义
PAT = '__' + ESC + '_%'
for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('users', 'username'),
               ('team_members', 'account'), ('board_columns', 'board_id'),
               ('board_config', 'board_id'), ('board_columns', 'column_id'),
               ('cards', 'board_id')):
    sql = 'SELECT COUNT(*) FROM %s WHERE %s LIKE ? ESCAPE ?' % (t, col)
    n = c.execute(sql, (PAT, ESC)).fetchone()[0]
    if n:
        print('  %s.%s = %d' % (t, col, n))
        found = True
print('  （无输出 = 干净）' if not found else '  ↑ 有残留')
c.close()
