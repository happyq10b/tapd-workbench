#!/usr/bin/env bash
# ============================================================
#  TAPD Workbench 本地 → 服务器 同步脚本（Windows Git Bash）
#
#  ★★★ 交付流程：两阶段强制分离 ★★★
#
#    阶段一「本地执行与验证」（必须先做，本脚本会强制校验）
#        cd ops && python verify.py
#        → 7 项检查全部通过才签发验证凭证 ops/.verify-stamp
#
#    阶段二「手动触发热同步」（只能由你手动执行本脚本）
#        cd ops && ./sync.sh --dev    # 推到服务器开发环境
#        cd ops && ./sync.sh --prod   # 推到生产环境
#
#    门禁规则（任一不满足即拒绝同步）：
#      · 没有验证凭证            → 拒绝
#      · 凭证指纹与当前代码不符  → 拒绝（改过代码必须重新验证）
#      · 凭证超过 2 小时未更新   → 拒绝
#    紧急绕过：SKIP_VERIFY=1 ./sync.sh --dev（打印警告，仅限故障恢复）
#
#  前置: 配置好 SSH 免密登录
#  用法:
#     ./sync.sh --dev        # 同步代码 + 切开发模式
#     ./sync.sh --prod       # 同步代码 + 切回生产模式
#     ./sync.sh --pull       # 从服务器拉回代码（只拉不推，不受门禁约束）
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
# 验证凭证（阶段一产出）
STAMP="$SCRIPT_DIR/.verify-stamp"
VERIFY_MAX_AGE="${VERIFY_MAX_AGE:-7200}"   # 凭证有效期（秒），默认 2 小时

# NO_COLOR=1（同步开关.bat 设置）→ 关闭 ANSI 颜色码（老式 conhost 不解析 VT）
if [ -n "$NO_COLOR" ]; then
  c_g=""; c_y=""; c_r=""; c_b=""; c_d=""; c_0=""
else
  c_g=$'\033[32m'; c_y=$'\033[33m'; c_r=$'\033[31m'; c_b=$'\033[36m'; c_d=$'\033[2m'; c_0=$'\033[0m'
fi

if [ ! -d "$LOCAL_DIR" ]; then
  echo "${c_r}本地源码目录不存在: $LOCAL_DIR${c_0}"
  echo "请先把项目源码放到该目录，或修改脚本顶部 LOCAL_DIR"
  exit 1
fi
if [ ! -f "$KEY" ]; then
  echo "${c_r}SSH 私钥不存在: $KEY${c_0}"
  exit 1
fi

# ============================================================
#  门禁：阶段一验证凭证校验
# ============================================================
enforce_gate() {
  # --pull 是从服务器往回拉，不涉及推送，无需门禁
  if [ "$MODE" = "--pull" ]; then
    return 0
  fi
  if [ "${SKIP_VERIFY:-0}" = "1" ]; then
    echo "${c_y}! 已跳过验证门禁（SKIP_VERIFY=1）—— 仅限紧急故障恢复${c_0}"
    echo ""
    return 0
  fi

  echo "${c_b}==> 门禁校验：本地验证凭证${c_0}"
  if [ ! -f "$STAMP" ]; then
    echo "${c_r}× 没有验证凭证，拒绝同步${c_0}"
    echo "${c_r}  阶段一（本地执行与验证）尚未完成。请先运行：${c_0}"
    echo "${c_r}    cd ops && python verify.py${c_0}"
    exit 1
  fi

  local out
  out=$("$SCRIPT_DIR/.localvenv/Scripts/python.exe" "$SCRIPT_DIR/check_stamp.py" \
        "$STAMP" "$LOCAL_DIR" "$VERIFY_MAX_AGE" 2>/dev/null || echo "BAD check_failed")

  case "$out" in
    OK*)
      echo "${c_g}  √ 验证凭证有效${c_0}  ${c_d}${out#OK }${c_0}"
      echo ""
      ;;
    STALE*)
      echo "${c_r}× 代码已变更，验证凭证失效，拒绝同步${c_0}"
      echo "${c_r}  指纹 ${out#STALE }${c_0}"
      echo "${c_r}  阶段一需重跑： cd ops && python verify.py${c_0}"
      exit 1
      ;;
    EXPIRED*)
      echo "${c_r}× 验证凭证已过期（超过 ${VERIFY_MAX_AGE} 秒），拒绝同步${c_0}"
      echo "${c_r}  凭证时间 ${out#EXPIRED }${c_0}"
      echo "${c_r}  请重跑： cd ops && python verify.py${c_0}"
      exit 1
      ;;
    *)
      echo "${c_r}× 验证凭证无效（${out}），拒绝同步${c_0}"
      echo "${c_r}  请重跑： cd ops && python verify.py${c_0}"
      exit 1
      ;;
  esac
}
enforce_gate

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
      echo "${c_y}! 警告：服务器代码比本地多 ${EXTRA} 行${c_0}"
      echo "${c_y}  如果你在服务器上改过，请先执行 ./sync.sh --pull 拉回本地${c_0}"
      echo "${c_y}  否则本次同步会用本地版本覆盖服务器改动${c_0}"
      echo ""
      read -p "  仍要继续覆盖？(yes/no) " ans || ans=""
      [ "$ans" = "yes" ] || { echo "已取消"; exit 1; }
      echo ""
    elif [ "$EXTRA" -gt 0 ]; then
      echo "${c_y}i 服务器比本地多 ${EXTRA} 行（微小差异），按本地版本同步${c_0}"
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
  # 排除 __pycache__，否则 scp 会因目录项报错
  scp "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/app/*.py" "$LOCAL_DIR/app/"
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
# 清掉服务器上遗留的 pycache，避免重启后加载旧字节码
ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "find $REMOTE_DIR/app $REMOTE_DIR/static -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; true"

# 2. 可选：覆盖数据库
if [ "$MODE" = "--db-local" ]; then
  echo "${c_y}[2/3]${c_0} 覆盖服务器数据库（本地版本）"
  read -p "    这会丢弃服务器上的新数据，确认？(yes/no) " ans || ans=""
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
    echo "${c_g}[3/3]${c_0} 切到开发模式"
    ssh "${SSH_READ_OPTS[@]}" "$SSH_USER@$SERVER_IP" "systemctl enable --now tapd-dev; sleep 1; systemctl restart tapd-dev; sleep 4; systemctl is-active tapd-dev; tail -5 /var/log/tapd-dev.log"
    echo "    跟踪日志: ssh -i $KEY $SSH_USER@$SERVER_IP 'tail -f /var/log/tapd-dev.log'"
    echo "    改代码后重跑 ./sync.sh --dev 即可生效（dev 模式不用 --reload，改为显式重启）"
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
