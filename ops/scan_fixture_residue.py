# -*- coding: utf-8 -*-
"""扫描实体级夹具残留（看板/板块/架构/任命/人员/消息），输出清单供清理。"""
import sqlite3

c = sqlite3.connect('src/app.db')
c.row_factory = sqlite3.Row
PAT = r'\_\_%'   # 字面两个下划线开头（\ 转义 _，否则 LIKE 里 _ 是单字符通配符）

def show(t, conds, label, limit=8):
    where = ' OR '.join(f"({w})" for w in conds)
    try:
        rows = c.execute(f'SELECT rowid,* FROM [{t}] WHERE {where}').fetchall()
    except Exception as e:
        print(f'== {label} ({t}): 查询失败 {e}')
        return
    print(f'== {label} ({t}): {len(rows)} 条')
    for r in rows[:limit]:
        print('   ', dict(r))

show('boards', [f"board_id LIKE '{PAT}' ESCAPE '\\'", f"board_name LIKE '{PAT}' ESCAPE '\\'"], '看板')
show('board_config', [f"board_id LIKE '{PAT}' ESCAPE '\\'", f"dept LIKE '{PAT}' ESCAPE '\\'"], '看板配置')
show('board_columns', [f"col_key LIKE '__\\_%' ESCAPE '\\'", f"column_name LIKE '__\\_%' ESCAPE '\\'"], '板块')
show('org_nodes', [f"name LIKE '{PAT}' ESCAPE '\\'", "name LIKE '%t197%'", "name LIKE '%probe%'"], '架构节点')
show('org_appointments', [f"member_id IN (SELECT id FROM team_members WHERE account LIKE '{PAT}' ESCAPE '\\' OR name LIKE '{PAT}' ESCAPE '\\')"], '任命')
show('team_members', [f"account LIKE '{PAT}' ESCAPE '\\'", f"name LIKE '{PAT}' ESCAPE '\\'"], '成员')
show('users', [f"username LIKE '{PAT}' ESCAPE '\\'"], '账号', 12)
show('cards', [f"card_id LIKE '{PAT}' ESCAPE '\\'", f"card_name LIKE '{PAT}' ESCAPE '\\'", f"board_id LIKE '{PAT}' ESCAPE '\\'"], '事项', 12)
show('wg_groups', [f"wg_id LIKE '{PAT}' ESCAPE '\\'", f"wg_name LIKE '{PAT}' ESCAPE '\\'"], '小组')
print('== org_nodes 总数 ==', c.execute('SELECT COUNT(*) FROM org_nodes').fetchone()[0])
print('== org_nodes 全部节点 ==')
for r in c.execute('SELECT id, name, node_type, parent_id, wg_id, is_anchor FROM org_nodes ORDER BY sort, id'):
    print(tuple(r))
