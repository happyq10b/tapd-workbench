#!/usr/bin/env bash
# 每日一致性备份 + 保留 7 天
# 放置: /usr/local/bin/tapd-backup.sh
set -euo pipefail
APP_DIR=/opt/tapd-workbench
BACKUP_DIR=/var/backups/tapd-workbench
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
cat > /tmp/_bk.py <<'PYEOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PYEOF
"$APP_DIR/venv/bin/python" /tmp/_bk.py "$APP_DIR/app.db" "$BACKUP_DIR/app.db.$TS"
rm -f /tmp/_bk.py
find "$BACKUP_DIR" -name 'app.db.*' -mtime +7 -delete
