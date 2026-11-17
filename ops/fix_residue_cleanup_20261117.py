# -*- coding: utf-8 -*-
"""T-204e 修复：误删 BCP1793717004248（综合工作事项）的 boards/board_columns 行 —— 从备份精确回补；
然后用精确 ID 重新清理夹具（不再使用 LIKE 通配）。
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
BAK = os.path.join(os.path.dirname(__file__), 'backup_db_20261117_fixture.db')

# ① 合并 WAL（停服后残留 -wal），确保主文件完整
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.commit()

# ② 从备份回补被误删的真实看板行与板块行
b = sqlite3.connect(BAK)
b.row_factory = sqlite3.Row
bcp_board = b.execute("SELECT * FROM boards WHERE board_id='BCP1793717004248'").fetchall()
bcp_cols = b.execute("SELECT * FROM board_columns WHERE board_id='BCP1793717004248'").fetchall()
print('备份中 BCP：boards', len(bcp_board), '行；board_columns', len(bcp_cols), '行')

cur = c.execute("SELECT COUNT(*) FROM boards WHERE board_id='BCP1793717004248'").fetchone()[0]
cur_cols = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id='BCP1793717004248'").fetchone()[0]
print('当前库 BCP：boards', cur, '行；board_columns', cur_cols, '行')

cols_names = [r['name'] for r in c.execute('PRAGMA table_info(boards)')]
restored = 0
if cur == 0 and bcp_board:
    row = dict(bcp_board[0])
    ph = ','.join('?' * len(cols_names))
    c.execute(f"INSERT INTO boards ({','.join(cols_names)}) VALUES ({ph})",
              [row.get(n) for n in cols_names])
    restored += 1
col_names = [r['name'] for r in c.execute('PRAGMA table_info(board_columns)')]
if cur_cols < len(bcp_cols):
    have = {r[0] for r in c.execute("SELECT col_key FROM board_columns WHERE board_id='BCP1793717004248'")}
    ph = ','.join('?' * len(col_names))
    for row in bcp_cols:
        if row['col_key'] in have:
            continue
        c.execute(f"INSERT INTO board_columns ({','.join(col_names)}) VALUES ({ph})",
                  [row[n] for n in col_names])
        restored += 1
c.commit()
print('回补行数：', restored)

# ③ 精确清理夹具（硬编码精确 ID，零通配）
FIX_CARD_IDS = ['NC1794586087284',                 # __probe 甲
                'NC1794233212332', 'NC1794233481867', 'NC1794233513999',   # __t116 ×3（未删）
                'NC1794281016333', 'NC1794448978323', 'NC1794456537739',   # __rn_卡片 ×7（软删）
                'NC1794456904704', 'NC1794469537979', 'NC1794472074647', 'NC1794476328659']
ph = ','.join('?' * len(FIX_CARD_IDS))
c.execute(f'DELETE FROM card_subtasks WHERE card_id IN ({ph})', FIX_CARD_IDS)
c.execute(f'DELETE FROM comments WHERE card_id IN ({ph})', FIX_CARD_IDS)
c.execute(f'DELETE FROM actions WHERE card_id IN ({ph})', FIX_CARD_IDS)
c.execute(f'DELETE FROM cards WHERE card_id IN ({ph})', FIX_CARD_IDS)
c.execute("DELETE FROM board_columns WHERE col_key='__probe_B::__probe板块'")
c.execute("DELETE FROM boards WHERE board_id='__probe_B'")
c.execute('DELETE FROM board_config WHERE id=1741 AND board_id="__t197_bid"')
c.execute("DELETE FROM messages WHERE receiver='__probe_u1' OR sender='__probe_u1'")
c.execute("DELETE FROM team_members WHERE account='__probe_u1'")
c.execute("DELETE FROM user_prefs WHERE username='__probe_u1'")
c.execute("DELETE FROM users WHERE username='__probe_u1'")
c.commit()

# ④ 复查（全部精确条件）
chk = {
    'BCP boards': c.execute("SELECT COUNT(*) FROM boards WHERE board_id='BCP1793717004248'").fetchone()[0],
    'BCP board_columns': c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id='BCP1793717004248'").fetchone()[0],
    'probe boards': c.execute("SELECT COUNT(*) FROM boards WHERE board_id='__probe_B'").fetchone()[0],
    'probe columns': c.execute("SELECT COUNT(*) FROM board_columns WHERE col_key='__probe_B::__probe板块'").fetchone()[0],
    't197 config': c.execute("SELECT COUNT(*) FROM board_config WHERE id=1741").fetchone()[0],
    'probe user': c.execute("SELECT COUNT(*) FROM users WHERE username='__probe_u1'").fetchone()[0],
    '夹具卡残留': c.execute(f'SELECT COUNT(*) FROM cards WHERE card_id IN ({ph})', FIX_CARD_IDS).fetchone()[0],
}
print('== 复查 ==')
for k, v in chk.items():
    print(f'{k}: {v}')
ok = (chk['BCP boards'] == 1 and chk['probe boards'] == 0 and chk['probe columns'] == 0
      and chk['t197 config'] == 0 and chk['probe user'] == 0 and chk['夹具卡残留'] == 0
      and chk['BCP board_columns'] == len(bcp_cols))
print('全部符合预期' if ok else '⚠️ 存在异常，需人工核查！')
c.close()
b.close()
