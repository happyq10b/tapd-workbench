# -*- coding: utf-8 -*-
"""修复服务器 /usr/local/bin/tapd do_snap：rm WAL → wal_checkpoint(TRUNCATE)。
（先备份 tapd.bak-20261117；修改后 sh -n 验证。）"""
import io

P = '/usr/local/bin/tapd'
t = io.open(P, encoding='utf-8').read()
old = '  rm -f "$appdir/app.db-wal" "$appdir/app.db-shm"   # 快照后清 wal，保持单文件语义'
new = (
    '  # 2026-11-17 #131 修复：运行中库严禁 rm WAL —— rm 会丢弃未 checkpoint 的写入\n'
    '  # （发布后数据回退到最近 checkpoint 时点，用户复现两次）。改为安全合并：\n'
    '  local py2; py2="$DEV_DIR/venv/bin/python"; [ -x "$py2" ] || py2="$PROD_DIR/venv/bin/python"\n'
    '  "$py2" -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute(\'PRAGMA wal_checkpoint(TRUNCATE)\'); c.close()" "$appdir/app.db" 2>/dev/null || true'
)
assert old in t, '锚点未找到'
assert t.count(old) == 1, '锚点不唯一'
t = t.replace(old, new, 1)
io.open(P, 'w', encoding='utf-8').write(t)
print('do_snap WAL 修复已写入')
