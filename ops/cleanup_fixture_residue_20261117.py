# -*- coding: utf-8 -*-
"""T-204e（2026-11-17）夹具残留清理：
  - __probe_B 看板 / 板块 / __probe_u1 账号 / __probe 甲 事项（2026-11-14 探针遗留，测完未删）
  - __t197_bid 看板配置（T-197 测试遗留，dept=__t197_部门D7 → 界面「架构/部门」多出一个）
  - __t116 / __rn_卡片 等夹具事项卡（含软删行）
纪律：先备份 → 按 rowid 精确删除 → 复查零残留。日志表（actions/comments 孤儿行）随实体清理，
audit_logs 审计流水保留不动。
"""
import shutil, sqlite3, sys, os

DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
BAK = os.path.join(os.path.dirname(__file__), 'backup_db_20261117_fixture.db')

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

# ---------- ① 精确盘点待删实体 ----------
probe_boards = [r['board_id'] for r in c.execute(
    "SELECT board_id FROM boards WHERE board_id LIKE '__p%' ESCAPE '\\' OR board_name LIKE '\\_\\_probe%' ESCAPE '\\'")]
t197_cfg = [r['id'] for r in c.execute(
    "SELECT id FROM board_config WHERE board_id LIKE '\\_\\_t197%' ESCAPE '\\' OR dept LIKE '\\_\\_t197%' ESCAPE '\\'")]
probe_users = [r['username'] for r in c.execute(
    "SELECT username FROM users WHERE username LIKE '\\_\\_p%' ESCAPE '\\'")]
fixture_cards = [r['rowid'] for r in c.execute(
    "SELECT rowid FROM cards WHERE (card_name LIKE '\\_\\_t%' ESCAPE '\\' OR card_name LIKE '\\_\\_p%' ESCAPE '\\'"
    " OR card_id LIKE '\\_\\_t%' ESCAPE '\\') OR (board_id LIKE '\\_\\_p%' ESCAPE '\\')")]

print('待删：看板', probe_boards, '| board_config 行', t197_cfg,
      '| 账号', probe_users, '| 夹具卡 rowid 数', len(fixture_cards))
if not (probe_boards or t197_cfg or probe_users or fixture_cards):
    print('无实体残留，退出'); sys.exit(0)

# ---------- ② 备份 ----------
shutil.copy2(DB, BAK)
print('已备份 →', BAK)

# ---------- ③ 删除 ----------
c.execute('PRAGMA foreign_keys=OFF')
if fixture_cards:
    ph = ','.join('?' * len(fixture_cards))
    c.execute(f'DELETE FROM comments WHERE card_id IN (SELECT card_id FROM cards WHERE rowid IN ({ph}))', fixture_cards)
    c.execute(f'DELETE FROM actions WHERE card_id IN (SELECT card_id FROM cards WHERE rowid IN ({ph}))', fixture_cards)
    c.execute(f'DELETE FROM card_subtasks WHERE card_id IN (SELECT card_id FROM cards WHERE rowid IN ({ph}))', fixture_cards)
    c.execute(f'DELETE FROM cards WHERE rowid IN ({ph})', fixture_cards)
for bid in probe_boards:
    c.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
    c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
for cid in t197_cfg:
    c.execute('DELETE FROM board_config WHERE id=?', (cid,))
for u in probe_users:
    c.execute('DELETE FROM messages WHERE receiver=? OR sender=?', (u, u))
    c.execute('DELETE FROM team_members WHERE account=?', (u,))
    c.execute('DELETE FROM user_prefs WHERE username=?', (u,))
    c.execute('DELETE FROM users WHERE username=?', (u,))
# 孤儿流水：card_id 以 '__' 开头的评论/操作记录（挂靠已删夹具实体）
c.execute("DELETE FROM comments WHERE card_id LIKE '\\_\\_%' ESCAPE '\\'")
c.execute("DELETE FROM actions WHERE card_id LIKE '\\_\\_%' ESCAPE '\\' AND card_id <> '__user__' AND card_id <> '__column__'")
c.commit()

# ---------- ④ 复查 ----------
print('== 复查 ==')
def cnt(sql, *p):
    return c.execute(sql, p).fetchone()[0]
print('boards __p:', cnt("SELECT COUNT(*) FROM boards WHERE board_id LIKE '__p%' ESCAPE '\\'"))
print('board_config __t197:', cnt("SELECT COUNT(*) FROM board_config WHERE board_id LIKE '\\_\\_t197%' ESCAPE '\\' OR dept LIKE '\\_\\_t197%' ESCAPE '\\'"))
print('board_columns __p:', cnt("SELECT COUNT(*) FROM board_columns WHERE col_key LIKE '__p%' ESCAPE '\\'"))
print('users __p:', cnt("SELECT COUNT(*) FROM users WHERE username LIKE '__p%' ESCAPE '\\'"))
print('cards 夹具名:', cnt("SELECT COUNT(*) FROM cards WHERE card_name LIKE '\\_\\_t%' ESCAPE '\\' OR card_name LIKE '\\_\\_p%' ESCAPE '\\' OR card_name LIKE '\\_\\_r%' ESCAPE '\\'"))
print('comments 孤儿:', cnt("SELECT COUNT(*) FROM comments WHERE card_id LIKE '\\_\\_%' ESCAPE '\\' AND card_id NOT IN ('__user__','__column__')"))
print('actions 孤儿:', cnt("SELECT COUNT(*) FROM actions WHERE card_id LIKE '\\_\\_%' ESCAPE '\\' AND card_id NOT IN ('__user__','__column__')"))
c.close()
