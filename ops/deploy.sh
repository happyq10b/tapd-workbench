#!/usr/bin/env bash
# ============================================================
#  TAPD Workbench 服务器端部署脚本
#  目标: Ubuntu 24.04 / 轻量云 lhins-bjtj9sgf
#  用法: sudo bash deploy.sh <传输包路径.tar.gz>
# ============================================================
set -euo pipefail

APP_DIR=/opt/tapd-workbench
PKG="${1:?用法: deploy.sh <包路径.tar.gz>}"
SECRET_FILE=/etc/tapd-workbench.secret
BACKUP_DIR=/var/backups/tapd-workbench

echo "==> [1/8] 创建目录"
mkdir -p "$APP_DIR" "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

echo "==> [2/8] 解包到 $APP_DIR"
cd "$APP_DIR"
tar xzf "$PKG"
# 解包后目录结构为 tapd-workbench/...，上移一层
if [ -d "$APP_DIR/tapd-workbench" ]; then
    cp -a "$APP_DIR/tapd-workbench/." "$APP_DIR/"
    rm -rf "$APP_DIR/tapd-workbench"
fi
ls -la "$APP_DIR"

echo "==> [3/8] 建虚拟环境并装依赖"
cd "$APP_DIR"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt

echo "==> [4/8] 清理密码明文列（不影响登录，登录只校验 password_hash）"
cat > /tmp/clean_plain.py <<'PYEOF'
import sqlite3, sys
p = sys.argv[1]
c = sqlite3.connect(p)
n = c.execute("SELECT COUNT(*) FROM users WHERE password_plain IS NOT NULL AND password_plain!=''").fetchone()[0]
c.execute("UPDATE users SET password_plain=NULL")
c.commit()
print(f"cleared_password_plain_rows={n}")
print("integrity:", c.execute("PRAGMA integrity_check").fetchone()[0])
print("cards:", c.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
print("users:", c.execute("SELECT COUNT(*) FROM users").fetchone()[0])
c.close()
PYEOF
./venv/bin/python /tmp/clean_plain.py "$APP_DIR/app.db"
rm -f /tmp/clean_plain.py

echo "==> [5/8] 生成 APP_SECRET 并写入独立文件"
if [ ! -f "$SECRET_FILE" ]; then
    openssl rand -hex 32 > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    echo "    新生成 $SECRET_FILE"
else
    echo "    复用已有 $SECRET_FILE"
fi

echo "==> [6/8] 写入 systemd unit"
# APP_SECRET 通过 wrapper 脚本注入，避免 EnvironmentFile 不支持变量展开的问题
cat > /usr/local/bin/tapd-run <<RUNEOF
#!/bin/sh
export APP_SECRET="\$(cat /etc/tapd-workbench.secret 2>/dev/null || echo 'tapd-fallback-secret')"
export LANG=C.UTF-8
export PYTHONUNBUFFERED=1
cd /opt/tapd-workbench
exec /opt/tapd-workbench/venv/bin/uvicorn app.app:app \
  --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips='*'
RUNEOF
chmod +x /usr/local/bin/tapd-run

cat > /etc/systemd/system/tapd-web.service <<'UNITEOF'
[Unit]
Description=TAPD Kanban Workbench
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tapd-workbench
ExecStart=/usr/local/bin/tapd-run
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNITEOF
systemctl daemon-reload

echo "==> [7/8] 安装 nginx + 自签证书"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx openssl >/dev/null
if [ ! -f /etc/nginx/ssl/tapd.crt ]; then
    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/tapd.key -out /etc/nginx/ssl/tapd.crt \
        -subj "/C=CN/ST=Guangdong/L=Guangzhou/O=TestBigBang/CN=123.207.252.195" \
        -addext "subjectAltName=IP:123.207.252.195,DNS:localhost" 2>/dev/null
    chmod 600 /etc/nginx/ssl/tapd.key
    echo "    自签证书已生成（10 年有效期）"
fi

echo "==> [8/9] 安装工具箱与备份脚本"
install -m 755 /tmp/tapd-tool.sh /usr/local/bin/tapd 2>/dev/null || true
install -m 755 /tmp/tapd-backup.sh /usr/local/bin/tapd-backup 2>/dev/null || true
if [ ! -f /etc/cron.d/tapd-backup ]; then
    cat > /etc/cron.d/tapd-backup <<'CRONEOF'
17 3 * * * root /usr/local/bin/tapd-backup
CRONEOF
    chmod 644 /etc/cron.d/tapd-backup
    echo "    每日 03:17 自动备份已配置"
fi

echo "==> [9/9] 启动服务"
systemctl enable --now tapd-web
sleep 3
systemctl status tapd-web --no-pager -l | head -20
echo ""
echo "=========================================================="
echo " 部署完成"
echo "   服务状态: systemctl status tapd-web"
echo "   本机自测: curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/login"
echo "   日志:     journalctl -u tapd-web -f"
echo "=========================================================="
