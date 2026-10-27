#!/usr/bin/env bash
# ============================================================
#  本地起一个 TAPD 工作台（完全脱离服务器）
#  用途: 改前端/后端逻辑时，本地调完再推服务器
#  数据库: 用本地 app.db（从服务器拉一份），不碰生产数据
#
#  用法:
#     ./local-dev.sh            前台运行（Ctrl+C 停止）
#     ./local-dev.sh start      后台启动（脱离终端，推荐）
#     ./local-dev.sh stop       停止
#     ./local-dev.sh restart    重启
#     ./local-dev.sh status     查看状态
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../src"
VENV_DIR="$SCRIPT_DIR/.localvenv"
PORT="${PORT:-8100}"
PY="/d/py/python.exe"

c_g=$'\033[32m'; c_y=$'\033[33m'; c_b=$'\033[36m'; c_0=$'\033[0m'

if [ ! -d "$SRC_DIR" ]; then
  echo "源码目录不存在: $SRC_DIR"; exit 1
fi

# ============================================================
#  子命令分支：交给 local-ctl.py 管理（Windows 进程管理更可靠）
# ============================================================
case "${1:-run}" in
  start|stop|restart|status)
    exec "$VENV_DIR/Scripts/python.exe" "$SCRIPT_DIR/local-ctl.py" "$1"
    ;;
  run) ;;   # 继续走下面的前台流程
  *) echo "用法: ./local-dev.sh [start|stop|restart|status|run]"; exit 2 ;;
esac

echo "${c_b}==> 本地开发环境${c_0}"
echo "    源码: $SRC_DIR"
echo "    端口: $PORT"
echo ""

# 建 venv
if [ ! -d "$VENV_DIR" ]; then
  echo "==> 创建虚拟环境"
  "$PY" -m venv "$VENV_DIR"
  # pip 25+ 拒绝用 pip.exe 自我升级，改用 python -m pip；升级本身非必需，失败不阻断
  "$VENV_DIR/Scripts/python.exe" -m pip install --upgrade pip 2>&1 | tail -1 || true
  echo "==> 安装依赖"
  "$VENV_DIR/Scripts/python.exe" -m pip install -r "$SRC_DIR/requirements.txt" 2>&1 | tail -3
  echo "    依赖已装"
fi

# 没有本地库就从服务器拉一份
if [ ! -f "$SRC_DIR/app.db" ]; then
  echo "==> 本地无 app.db，从服务器拉一份只读副本"
  scp -i "$SCRIPT_DIR/secrets/tapd_deploy_key" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
      root@123.207.252.195:/opt/tapd-workbench/app.db "$SRC_DIR/app.db" || {
      echo "    拉取失败，将用空库启动（仅 CSV 初始化）"
    }
fi

cd "$SRC_DIR"
export APP_SECRET="local-dev-secret-not-for-production"
export PYTHONUTF8=1
export PORT
echo "${c_g}==> 启动（自动重启模式，Ctrl+C 停止）${c_0}"
echo "    访问: http://127.0.0.1:${PORT}/"
echo "    改代码会自动重启服务"
echo ""
# 注意：这里不用 uvicorn --reload —— 它的 reloader 在 Windows 上第一次触发后
# 会卡死（日志停在 Reloading...，服务还在响但代码永不更新）。
# 改用 dev-watchdog.py 轮询文件指纹 + 优雅重启，行为可控。
exec "$VENV_DIR/Scripts/python.exe" "$SCRIPT_DIR/dev-watchdog.py"
