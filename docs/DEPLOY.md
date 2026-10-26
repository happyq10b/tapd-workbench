# TAPD 看板 Web 应用 v2 - 多人协作编辑版 · 部署手册

> 版本：v2（协作编辑版）｜支持：多人在线编辑、卡片级编辑锁（WebSocket 实时）、三层权限（只读/可编辑/管理员）、卡片评论、操作日志、增删卡片
> 目标：把看板应用部署到你的腾讯轻量云（测试大爆炸 · Ubuntu 24.04 · 公网 IP 123.207.252.195）
> 全程 SSH 命令行操作，**照抄命令即可**（`#` 开头是注释说明，不用输入）

---
把看板应用部署到你的腾讯轻量云（测试大爆炸 · Ubuntu 24.04 · 公网 IP 123.207.252.195）
> 全程 SSH 命令行操作，**照抄命令即可**（`#` 开头是注释说明，不用输入）

---

## 〇、开始前确认

| 项 | 值 |
|---|---|
| 公网 IP | `123.207.252.195` |
| 系统 | Ubuntu 24.04 LTS |
| 登录方式 | 轻量云控制台 → 实例 → 重置密码（或已有的 root 密码/密钥） |
| 部署包 | `tapd_webapp.zip`（本手册同目录） |

**如果还没拿到 root 密码**：腾讯云控制台 → 轻量应用服务器 → 选「测试大爆炸」→ 更多 → 重置密码 → 设置 root 密码并记住。

---

## 第一步：SSH 连上服务器

在你自己的电脑（Windows）打开 **PowerShell 或 CMD**，输入：

```bash
ssh root@123.207.252.195
```

提示 `yes/no` 输 `yes`，然后输入你设置的 root 密码。

> 看到类似 `root@VM-xxx:~#` 就表示连上了。

---

## 第二步：上传部署包

部署包在你本机（`tapd_webapp.zip`），用 `scp` 传上去（**在本地另一个窗口执行，别关 SSH**）：

```bash
scp tapd_webapp.zip root@123.207.252.195:/root/
```

传完回到 SSH 窗口，解压并移动到 `/opt`：

```bash
cd /root
apt-get install -y unzip        # 装解压工具（提示装就装）
unzip tapd_webapp.zip -d /opt/
mv /opt/tapd_webapp /opt/tapd-web
ls /opt/tapd-web
```

> 应该看到：`app/  data/  static/  manage_users.py  requirements.txt  users.json`

---

## 第三步：安装 Python 环境

Ubuntu 24.04 自带 Python 3.12，只需补 venv 和 pip：

```bash
apt-get update
apt-get install -y python3-venv python3-pip
```

---

## 第四步：建虚拟环境 + 装依赖

```bash
cd /opt/tapd-web
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

> 会装 fastapi + uvicorn + websockets（websockets 用于 WebSocket 实时协作，缺了会报 `No supported WebSocket library detected`，前端实时功能失效）。等它跑完即可。

---

## 第五步：配置登录账号（关键！不同人不同权限）

用自带的 `manage_users.py` 添加账号：

```bash
cd /opt/tapd-web
./venv/bin/python manage_users.py list
```

先看一下现有用户（部署包里我放了测试账号，**建议删掉重建**）：

```bash
./venv/bin/python manage_users.py del admin
./venv/bin/python manage_users.py del zhangsan
./venv/bin/python manage_users.py del lisi
```

**添加管理员（能看全部 7 个看板）**：

```bash
./venv/bin/python manage_users.py add admin 你的密码 --role admin --boards '*'
```

**添加只能看费用看板的 A**（看板 ID = 1162069797001000245）：

```bash
./venv/bin/python manage_users.py add a_username a_password --role editor --boards 1162069797001000245
```

**添加只能看税务看板的 B**（看板 ID = 1162069797001000242）：

```bash
./venv/bin/python manage_users.py add b_username b_password --role editor --boards 1162069797001000242
```

> 7 个看板 ID：
> - 综合工作事项 `1162069797001000238`
> - 资产工作事项 `1162069797001000239`
> - 成本工作事项 `1162069797001000241`
> - 税务工作事项 `1162069797001000242`
> - 收入工作事项 `1162069797001000243`
> - 费用工作事项 `1162069797001000245`
> - 海南工作专项 `1162069797001000246`
>
> 想看多个看板就逗号分隔：`--boards 1162069797001000245,1162069797001000242`

**以后随时加人/改权限**，重跑上面的 add / boards 命令即可，**不用重启服务**：

```bash
./venv/bin/python manage_users.py boards a_username 1162069797001000245,1162069797001000242   # 改权限
./venv/bin/python manage_users.py list                                                          # 查看
```

---

## 第六步：配置密钥（可选但建议）

给 token 加密换一个随机密钥，防止别人伪造登录：

```bash
echo 'export APP_SECRET=随便输一串长字符比如20260818TAPDsecret' >> /etc/profile.d/tapd.sh
source /etc/profile.d/tapd.sh
```

---

## 第七步：设置开机自启（systemd 服务）

创建服务文件：

```bash
cat > /etc/systemd/system/tapd-web.service << 'EOF'
[Unit]
Description=TAPD Kanban Web App
After=network.target

[Service]
WorkingDirectory=/opt/tapd-web
EnvironmentFile=/etc/profile.d/tapd.sh
ExecStart=/opt/tapd-web/venv/bin/uvicorn app.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable tapd-web
systemctl start tapd-web
systemctl status tapd-web        # 看到 active (running) 即成功
```

> 以后重启服务器也会自动起。手动重启服务：`systemctl restart tapd-web`

---

## 第八步：防火墙放行 8000 端口

**两步都要做，缺一不可：**

**① 腾讯云控制台放行**：
轻量应用服务器 → 「测试大爆炸」→ 防火墙 → 添加规则 → 应用类型选「自定义」→ 端口 `8000` → 协议 TCP → 允许 → 确定

**② 服务器内 ufw 放行**（如果开着）：
```bash
ufw allow 8000/tcp
ufw status        # 如果不是 active 就无所谓
```

---

## 第九步：验证访问

浏览器打开：

```
http://123.207.252.195:8000
```

- 应看到登录页 → 输入刚建的账号密码
- admin 登录看到全部 7 个看板；A 登录只有费用看板；B 登录只有税务看板

---

## 常见问题

| 问题 | 处理 |
|---|---|
| 打不开页面 | 检查第八步两步防火墙都做了没；`systemctl status tapd-web` 看服务是否 running |
| 登录报错 | 重新执行第五步 add 命令，密码别用太简单的 |
| 服务挂了 | `systemctl restart tapd-web`；看日志 `journalctl -u tapd-web -n 50` |
| 想换端口 | 改第七步 `--port 8000` 为其他端口，同时第八步防火墙放行对应端口，然后 `systemctl daemon-reload && systemctl restart tapd-web` |
| 数据要更新 | 重新导出宽表 CSV，替换 `/opt/tapd-web/data/全部看板_2026年度_总宽表.csv`，然后 `systemctl restart tapd-web` |

---

## 应用结构

```
/opt/tapd-web/
├── app/app.py          # FastAPI 后端（登录/JWT/权限过滤/查询API）
├── static/             # 前端（login.html + index.html，无外部依赖）
├── data/               # 宽表数据 CSV（唯一数据源）
├── users.json          # 用户账号（密码 pbkdf2 哈希存储）
├── manage_users.py     # 用户管理命令
└── requirements.txt    # Python 依赖
```
