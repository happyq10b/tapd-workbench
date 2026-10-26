#!/usr/bin/env bash
# ============================================================
#  TAPD Workbench 运维工具箱
#  放置: /usr/local/bin/tapd
#  用法: tapd <子命令>
# ============================================================
set -euo pipefail

APP_DIR=/opt/tapd-workbench
BACKUP_DIR=/var/backups/tapd-workbench
SVC=tapd-web

c_g=$'\033[32m'; c_y=$'\033[33m'; c_r=$'\033[31m'; c_b=$'\033[36m'; c_0=$'\033[0m'

usage() {
cat <<EOF
${c_b}TAPD Workbench 运维工具${c_0}

  ${c_g}status${c_0}            查看服务状态 + 健康检查
  ${c_g}logs${c_0} [行数]       跟踪日志（默认 100 行）
  ${c_g}restart${c_0}           重启服务
  ${c_g}reload${c_0}            重载配置（改代码后用）
  ${c_g}backup${c_0}            立即备份数据库
  ${c_g}backups${c_0}           列出历史备份
  ${c_g}restore${c_0} <文件>    从备份恢复（会停服）
  ${c_g}dev${c_0}               前台开发模式（热重载，日志直接看）
  ${c_g}stopdev${c_0}           停掉开发模式，让生产服务接管 8000
  ${c_g}shell${c_0}             进项目目录开交互 shell
  ${c_g}version${c_0}           看当前部署版本信息
EOF
}

case "${1:-}" in
  status)
    systemctl status $SVC --no-pager -l | head -15
    echo ""
    echo -n "本机 HTTP 自测: "
    curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8000/login || echo "FAIL"
    echo -n "公网 HTTPS 自测: "
    curl -sk -o /dev/null -w '%{http_code}\n' --max-time 8 https://123.207.252.195/login || echo "FAIL"
    ;;

  logs)
    journalctl -u $SVC -n "${2:-100}" -f --no-pager
    ;;

  restart)
    systemctl restart $SVC && sleep 2 && systemctl status $SVC --no-pager | head -5
    ;;

  reload)
    systemctl restart $SVC && sleep 2
    echo "已重启（代码变更后生效）"
    ;;

  backup)
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
    echo "备份完成: $BACKUP_DIR/app.db.$TS"
    ls -la "$BACKUP_DIR" | tail -5
    ;;

  backups)
    ls -la "$BACKUP_DIR" 2>/dev/null || echo "还没有备份，先跑 tapd backup"
    ;;

  restore)
    F="${2:?用法: tapd restore <备份文件路径>}"
    [ -f "$F" ] || { echo "${c_r}文件不存在: $F${c_0}"; exit 1; }
    echo "${c_y}将用 $F 覆盖当前数据库，过程中会停服${c_0}"
    read -p "确认继续？(yes/no) " ans
    [ "$ans" = "yes" ] || { echo "已取消"; exit 1; }
    systemctl stop $SVC
    cp "$F" "$APP_DIR/app.db"
    rm -f "$APP_DIR/app.db-wal" "$APP_DIR/app.db-shm"
    systemctl start $SVC
    sleep 2
    echo "恢复完成，服务已启动"
    ;;

  dev)
    echo "${c_y}切到开发模式（热重载）${c_0}"
    systemctl enable --now tapd-dev
    sleep 3
    systemctl is-active tapd-dev
    echo "日志: tail -f /var/log/tapd-dev.log"
    echo "${c_y}改完代码自动重载，无需手动重启${c_0}"
    ;;

  stopdev)
    systemctl stop tapd-dev
    systemctl disable tapd-dev 2>/dev/null || true
    systemctl start $SVC
    sleep 2
    echo "开发模式已停，生产服务已接管 8000"
    ;;

  devlog)
    tail -f /var/log/tapd-dev.log
    ;;

  shell)
    cd "$APP_DIR"
    export APP_SECRET=$(cat /etc/tapd-workbench.secret 2>/dev/null || echo dev-secret)
    echo "已进入 $APP_DIR，APP_SECRET 已注入"
    exec bash
    ;;

  version)
    cd "$APP_DIR"
    echo "部署目录: $APP_DIR"
    echo "Python:  $($APP_DIR/venv/bin/python --version 2>&1)"
    echo "代码更新: $(date -r $APP_DIR/app/app.py '+%Y-%m-%d %H:%M:%S')"
    echo "DB 更新:  $(date -r $APP_DIR/app.db '+%Y-%m-%d %H:%M:%S')"
    $APP_DIR/venv/bin/pip list 2>/dev/null | grep -Ei 'fastapi|uvicorn|websockets' || true
    ;;

  *)
    usage
    ;;
esac
