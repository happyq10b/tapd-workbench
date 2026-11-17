# -*- coding: utf-8 -*-
"""T-204p 残留清理（2026-11-17 用户报告）：
残留清单已 SELECT 核对（D2：精确主键删除，不用裸 LIKE）：
  1. boards: __t204p 测试看板（board_id=B1794895097672，T-204p 第二次 setup 失败运行残留）
  2. cards: __t116×3（deleted=0）、__rn_卡片×1（deleted=1）—— #122 清理后，
     本地库被 db-sync [6] Apply 整库替换回 11-13 快照时带回的历史夹具
同时修复 test_t204p_cardpool.py 的清理逻辑（失败路径也清理 + LIKE 全匹配）。
"""
import sqlite3

DB = 'src/app.db'
BS = chr(92)
# 转义模式：\_\_t204p%（两个下划线都转义——此前 pat_user 只转了一个，口径不严）
PAT = '%_' + BS + '_t204q%'   # 仅用于残留复查（t204p 用精确 id 删）
c = sqlite3.connect(DB)

# ① 精确 id：看板（含可能的同源板块/卡——先查该板下有没有挂东西）
bid = 'B1794895097672'
print('清理前核对:')
print('  看板:', c.execute('SELECT board_id, board_name FROM boards WHERE board_id=?', (bid,)).fetchall())
print('  其下板块:', c.execute('SELECT col_key, column_name FROM board_columns WHERE board_id=?', (bid,)).fetchall())
print('  其下卡:', c.execute('SELECT card_id, card_name FROM cards WHERE board_id=?', (bid,)).fetchall())

# ② 精确 id：__t116 / __rn_ 卡片
old_cards = [r[0] for r in c.execute(
    "SELECT card_id FROM cards WHERE card_name IN ('__t116','__rn_卡片','__rn_新名字A')")]
print('  历史夹具卡:', old_cards)

c.execute('DELETE FROM boards WHERE board_id=?', (bid,))
c.execute('DELETE FROM board_columns WHERE board_id=?', (bid,))
c.execute('DELETE FROM cards WHERE board_id=?', (bid,))
for cid in old_cards:
    c.execute('DELETE FROM cards WHERE card_id=?', (cid,))
    c.execute('DELETE FROM card_subtasks WHERE card_id=?', (cid,))
c.commit()

# ③ 复查
res = {}
for t, col in (('boards', 'board_name'), ('cards', 'card_name'), ('board_columns', 'col_key')):
    res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                       ('%' + BS + '_t204p%', BS)).fetchone()[0]
res['历史夹具卡'] = c.execute(
    "SELECT COUNT(*) FROM cards WHERE card_name IN ('__t116','__rn_卡片','__rn_新名字A')").fetchone()[0]
c.close()
print('清理后残留:', res)
print('OK' if not any(res.values()) else '仍有残留！')
