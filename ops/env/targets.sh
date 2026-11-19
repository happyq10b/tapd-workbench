# ============================================================
#  环境目标定义 —— 地址 / 路径 / 服务名的唯一真源
#
#  被谁读取：
#     ops/sync.sh        —— 代码同步的目标解析
#     ops/db_sync.py     —— 生产→开发 数据同步的目标解析
#     ops/prod-cutover.sh / ops/provision-dev.sh —— 服务器端脚本
#
#  ★ 本文件不含任何密钥。
#    SSH 主机别名与私钥路径在 ops/secrets/sshcfg（已 gitignore）。
#
#  ★ 改地址只改这里，不要改脚本。
# ============================================================

# ---------- 生产环境（正式环境）----------
PROD_SSH_HOST=tapd-prod
PROD_LABEL=生产环境
PROD_URL=https://123.207.252.195/
PROD_REMOTE_DIR=/opt/tapd-workbench
PROD_SERVICE=tapd-web
PROD_APP_PORT=8000
PROD_PUBLIC_PORT=443
PROD_DB_PATH=/opt/tapd-workbench/app.db
PROD_BACKUP_DIR=/var/backups/tapd-workbench
PROD_SECRET_FILE=/etc/tapd-workbench.secret

# ---------- 开发环境 ----------
#  拓扑 A（当前）：与生产同机、独立目录 + 独立端口 + 独立库 + 独立 nginx 站点
#    → 访问地址 https://123.207.252.195:8443/  （与生产的 443 不同）
#  拓扑 B（目标）：迁移到独立服务器后，只需改下面两行：
#    DEV_SSH_HOST=tapd-dev     （ops/secrets/sshcfg 里把 HostName 指向新机器）
#    DEV_PUBLIC_PORT=443
#  其余字段（目录 / 服务名 / 端口 / 库路径）保持不变，脚本零改动。
DEV_SSH_HOST=tapd-dev
DEV_LABEL=开发环境
DEV_URL=https://123.207.252.195:8443/
DEV_REMOTE_DIR=/opt/tapd-workbench-dev
DEV_SERVICE=tapd-web-dev
DEV_APP_PORT=8001
DEV_PUBLIC_PORT=8443
DEV_DB_PATH=/opt/tapd-workbench-dev/app.db
DEV_BACKUP_DIR=/var/backups/tapd-workbench-dev
DEV_SECRET_FILE=/etc/tapd-workbench-dev.secret
