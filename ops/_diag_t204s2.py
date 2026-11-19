# -*- coding: utf-8 -*-
"""诊断：t204s 式夹具（公共板+participants=u1+板块 owner=u2/participants=u1）
下 user_allowed / visible_columns 对 u1 的实际返回"""
import sys, os, sqlite3
sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import user_allowed, visible_columns, dbq, make_token, hash_pw

BID = 'B1794911445814'   # t204s 最后一次运行的夹具看板 id（日志里出现过）
c = sqlite3.connect('src/app.db')
row = c.execute('SELECT board_id, board_name, owner, participants FROM boards WHERE board_id=?',
                (BID,)).fetchone()
print('夹具看板行:', dict(zip(('board_id','board_name','owner','participants'), row)) if row else '已清理')
c.close()

# 重建同款夹具（临时）验证逻辑
c = sqlite3.connect('src/app.db')
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES ('__d_u1',?,'editor')",
          (hash_pw('Xx12345678'),))
c.execute("INSERT OR IGNORE INTO boards (board_id, board_name, owner, participants) "
          "VALUES ('__d_B','__d 看板','admin','__d_u1')")
c.execute("INSERT OR IGNORE INTO board_columns (col_key, board_id, column_id, column_name, owner, participants) "
          "VALUES ('__d_B::__d板块','__d_B','__d_COL','__d板块','','__d_u1')")
c.commit()
c.close()

boards, columns = user_allowed('__d_u1')
print('user_allowed 含 __d_B:', bid in (boards or set()) if False else ('__d_B' in (boards or set())))
print('columns[__d_B]:', (columns or {}).get('__d_B'))
vc = visible_columns('__d_u1', boards, columns, board_id='__d_B')
print('visible_columns:', [(x['col_key'], x.get('owner'), x.get('participants')) for x in vc])
c = sqlite3.connect('src/app.db')
c.execute("DELETE FROM boards WHERE board_id='__d_B'")
c.execute("DELETE FROM board_columns WHERE col_key='__d_B::__d板块'")
c.execute("DELETE FROM users WHERE username='__d_u1'")
c.commit()
c.close()
print('诊断清理完成')
