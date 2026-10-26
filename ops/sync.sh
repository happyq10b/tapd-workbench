#!/usr/bin/env bash
# ============================================================
#  TAPD Workbench 本地 → 服务器 同步脚本（Windows Git Bash）
#  作用: 把本地代码改动推送到服务器并热重载
#
#  前置: 配置好 SSH 免密登录
#  用法:
#     ./sync.sh              # 同步代码 + 重启生产服务
#     ./sync.sh --dev        # 同步代码 + 切到开发模式（热重载）
#     ./sync.sh --prod       # 同步代码 + 切回生产模式
#     ./sync.sh --db-local   # 用本地 app.db 覆盖服务器（危险，会丢服务器新数据）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_IP=123.207.252.195
SSH_USER=root
KEY="$SCRIPT_DIR/secrets/tapd_deploy_key"
REMOTE_DIR=/opt/tapd-workbench
LOCAL_DIR="$SCRIPT_DIR/../src"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=20)
# ssh 会消耗 stdin，导致后续 read 拿不到用户输入。-n 把 stdin 重定向到 /dev/null 解决此问题
SSH_READ_OPTS=(-n "${SSH_OPTS[@]}")

MODE="${1:-prod}"
# 行数差异容忍阈值：差异在此范围内视为本地微调，自动继续；超过则强制确认
DIFF_TOLERANCE="${DIFF_TOLERANCE:-5}"

c_g=$'\033[32m'; c_y=$'\033[33m'; c_r=$'\033[31m'; c_b=$'\033[36m'; c_0=$'\033[0m'

if [ ! -d "$LOCAL_DIR" ]; then
  echo "${c_r}本地源码目录不存在: $LOCAL_DIR${c_0}"
  echo "请先把项目源码放到该目录，或修改脚本顶部 LOCAL_DIR"
  exit 1
fi
if [ ! -f "$KEY" ]; then
  echo "${c_r}SSH 私钥不存在: $KEY${c_0}"
  exit 1
fi

echo "${c_b}==> 本地: $LOCAL_DIR${c_0}"
echo "${c_b}==> 目标: $SSH_USER@$SERVER_IP:$REMOTE_DIR${c_0}"
echo ""

# 关键提示：本脚本是"本地 -> 服务器"单向覆盖。若你直接在服务器上改过代码，
# 必须先跑 ./sync.sh --pull 把改动拉回本地，否则会被本地版本静默覆盖。
#
# 判定策略：按行数差的方向判断
#   - 服务器 <= 本地：服务器没有"本地没有的内容"，是本地更新 → 正常同步（可提示）
#   - 服务器 >  本地：服务器有额外内容，可能是直接在服务器上改的 → 强制确认
# 这样既不会漏报"服务器直改"，又不会在正常开发时频繁拦截。
if [ "$MODE" != "--pull" ]; then
  REMOTE_LINES=$(ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" \
      "wc -l < $REMOTE_DIR/app/app.py 2>/dev/null | tr -d ' '" 2>/dev/null || echo "")
  LOCAL_LINES=$(wc -l < "$LOCAL_DIR/app/app.py" 2>/dev/null | tr -d ' ' || echo "")
  if [ -n "$REMOTE_LINES" ] && [ -n "$LOCAL_LINES" ]; then
    EXTRA=$(( REMOTE_LINES - LOCAL_LINES ))
    if [ "$EXTRA" -gt "$DIFF_TOLERANCE" ]; then
      echo "${c_y}⚠ 警告：服务器代码比本地多 ${EXTRA} 行${c_0}"
      echo "${c_y}  如果你在服务器上改过，请先执行 ./sync.sh --pull 拉回本地${c_0}"
      echo "${c_y}  否则本次同步会用本地版本覆盖服务器改动${c_0}"
      echo ""
      read -p "  仍要继续覆盖？(yes/no) " ans || ans=""
      [ "$ans" = "yes" ] || { echo "已取消"; exit 1; }
      echo ""
    elif [ "$EXTRA" -gt 0 ]; then
      echo "${c_y}ℹ 服务器比本地多 ${EXTRA} 行（微小差异），按本地版本同步${c_0}"
      echo ""
    fi
  fi
fi

# 传输前把 CRLF 转成 LF：Windows 编辑器容易写入 CRLF，Linux 侧统一用 LF 更稳
normalize_lf() {
  local f="$1"
  /d/py/python.exe - "$f" <<'PYEOF' 2>/dev/null || true
import sys
p = sys.argv[1]
try:
    d = open(p, 'rb').read()
    if b'\r\n' in d:
        open(p, 'wb').write(d.replace(b'\r\n', b'\n'))
        print(f"  [LF转换] {p}")
except Exception:
    pass
PYEOF
}
for f in "$LOCAL_DIR"/app/*.py "$LOCAL_DIR"/static/*.html; do
  [ -f "$f" ] && normalize_lf "$f"
done

# ---- 分叉：--pull 只拉不推，避免把服务器改动冲掉 ----
if [ "$MODE" = "--pull" ]; then
  echo "${c_g}[1/3]${c_0} 从服务器拉取代码（不推送）"
  mkdir -p "$LOCAL_DIR/app" "$LOCAL_DIR/static"
  scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/app/*" "$LOCAL_DIR/app/"
  scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/static/*" "$LOCAL_DIR/static/"
  scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/manage_users.py" "$LOCAL_DIR/"
  scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/requirements.txt" "$LOCAL_DIR/"
  echo "[2/3] 数据库不动"
  cd "$LOCAL_DIR"
  if [ -d .git ]; then
    echo "${c_g}[3/3]${c_0} 本地 git 变更："
    git status --short
    echo ""
    read -p "    提交为一个版本？(输入提交说明，直接回车跳过) " msg || true
    if [ -n "$msg" ]; then
      git add -A
      git -c user.name="workbuddy" -c user.email="workbuddy@local" commit -m "$msg"
      git log --oneline -1
    fi
  fi
  echo ""
  echo "${c_b}完成${c_0}"
  exit 0
fi

# 1. 同步代码（不动数据库）
echo "${c_g}[1/3]${c_0} 同步代码 app/ static/ manage_users.py requirements.txt"
scp "${SSH_OPTS[@]}" -r "$LOCAL_DIR/app" "$LOCAL_DIR/static" \
    "$LOCAL_DIR/manage_users.py" "$LOCAL_DIR/requirements.txt" \
    "$SSH_USER@$SERVER_IP:$REMOTE_DIR/"
# 清掉服务器上遗留的 pycache，避免热重载异常
ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "find $REMOTE_DIR/app $REMOTE_DIR/static -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; true"

# 2. 可选：覆盖数据库
if [ "$MODE" = "--db-local" ]; then
  echo "${c_y}[2/3]${c_0} 覆盖服务器数据库（本地版本）"
  read -p "    这会丢弃服务器上的新数据，确认？(yes/no) " ans
  if [ "$ans" = "yes" ]; then
    scp "${SSH_OPTS[@]}" "$LOCAL_DIR/app.db" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/app.db"
    ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "rm -f $REMOTE_DIR/app.db-wal $REMOTE_DIR/app.db-shm; systemctl restart tapd-web"
  else
    echo "    已跳过数据库覆盖"
  fi
else
  echo "[2/3] 跳过数据库（服务器数据保留）"
fi

# 3. 切换运行模式
case "$MODE" in
  --dev)
    echo "${c_g}[3/3]${c_0} 切到开发模式（热重载）"
    ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "systemctl enable --now tapd-dev; sleep 4; systemctl is-active tapd-dev; tail -5 /var/log/tapd-dev.log"
    echo "    跟踪日志: ssh -i $KEY $SSH_USER@$SERVER_IP 'tail -f /var/log/tapd-dev.log'"
    ;;
  --prod)
    echo "${c_g}[3/3]${c_0} 切回生产模式"
    ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "systemctl stop tapd-dev; systemctl disable tapd-dev 2>/dev/null; systemctl start tapd-web; sleep 2; systemctl is-active tapd-web"
    ;;
  *)
    echo "${c_g}[3/3]${c_0} 重启生产服务"
    ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "systemctl restart tapd-web; sleep 2; systemctl is-active tapd-web"
    ;;
esac

echo ""
echo "${c_b}完成${c_0}"
