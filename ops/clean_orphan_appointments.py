# -*- coding: utf-8 -*-
"""孤儿任命清理（D2/D4）：备份由外部完成；精确 NOT EXISTS 条件 + 行数守恒核对"""
import sqlite3
import sys

DB = sys.argv[1]
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

def n(sql):
    return c.execute(sql).fetchone()[0]

total = n('SELECT COUNT(*) FROM org_appointments')
orphans = n("""SELECT COUNT(*) FROM org_appointments a
               WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
               OR NOT EXISTS (SELECT 1 FROM org_nodes nd WHERE nd.id=a.node_id)""")
# 岗位任命（负责人岗位）绝不在删除范围 —— 单独核对
orphan_heads = n("""SELECT COUNT(*) FROM org_appointments a
                    WHERE a.role_key IN ('center_head','gm','dept_head','group_leader')
                    AND (NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
                    OR NOT EXISTS (SELECT 1 FROM org_nodes nd WHERE nd.id=a.node_id))""")
print('清理前: 总任命=%d, 孤儿=%d（其中负责人岗位孤儿=%d）' % (total, orphans, orphan_heads))
assert orphan_heads == 0, '存在负责人岗位孤儿任命，中止（需人工确认）'
c.execute("""DELETE FROM org_appointments
             WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=org_appointments.member_id)
             OR NOT EXISTS (SELECT 1 FROM org_nodes nd WHERE nd.id=org_appointments.node_id)""")
deleted = c.total_changes
after_total = n('SELECT COUNT(*) FROM org_appointments')
after_orphans = n("""SELECT COUNT(*) FROM org_appointments a
                     WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id)
                     OR NOT EXISTS (SELECT 1 FROM org_nodes nd WHERE nd.id=a.node_id)""")
c.commit()
print('已删除: %d | 清理后: 总任命=%d, 残余孤儿=%d' % (deleted, after_total, after_orphans))
assert after_orphans == 0, '仍有残余孤儿，异常'
assert total - deleted == after_total, '行数守恒校验失败'
print('行数守恒 ✓ 全部负责人岗位任命保留 ✓')
c.close()
