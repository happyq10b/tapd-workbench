# TAPD 工作台 · 工作空间

腾讯云轻量应用服务器上的 TAPD 部门看板工作台，完整的环境管理与开发部署工具箱。

---

## 目录结构

```
.
├── 同步开关.bat            ← 双击触发「验证 + 同步」的开关
├── src/                  ← 唯一的代码编辑区（git 仓库）
│   ├── app/                app.py（1569行主程序）+ init_db.py
│   ├── static/             index.html（2744行单页）+ login.html
│   ├── manage_users.py     账号管理 CLI
│   └── requirements.txt
│
├── ops/                  ← 运维工具箱
│   ├── sync.sh             同步脚本（本地 ↔ 服务器）
│   ├── local-dev.sh        本地起服务（端口 8100）
│   ├── deploy.sh           服务器端部署脚本（首次安装用）
│   ├── tapd-tool.sh        服务器端命令工具箱
│   ├── tapd-backup.sh      数据库备份
│   ├── nginx-tapd.conf     nginx 反代配置
│   ├── .localvenv/         本地 Python 虚拟环境
│   └── secrets/            SSH 配置与私钥（**不进 git**）
│
├── docs/                 ← 全部文档
│   ├── README.md            本文件
│   ├── 调试指南.md            日常开发调试手册（主入口）
│   ├── 调试链路地图.md          旧 WSL 时代链路记录 + 安全红线 + 血泪坑
│   ├── TAPD工作台迁移方案.md     2026-10-26 迁移方案
│   ├── DEPLOY.md / LINUX_DEPLOY.md / ORG_TO_WORKGROUP_SUMMARY.md
│
├── archive/              ← 归档（只读，勿改）
│   ├── packages/            部署包（tar.gz / 原始 zip）
│   ├── backup/              数据库备份
│   └── legacy/              旧 Windows 脚本、旧源码备份
│
└── .workbuddy/memory/    ← 会话记忆（工作台自动维护）
```

---

## 交付流程：两阶段强制分离

```
阶段一「本地执行与验证」          阶段二「手动触发热同步」
─────────────────────────         ─────────────────────────
改代码                            ops/sync.sh --dev / --prod
  ↓                                ↓
ops/verify.py                   门禁校验凭证（指纹+时效）
  ↓ 7 项检查全通过                 ↓ 校验通过才推送
签发 .verify-stamp  ────────→    服务器重启生效
```

**代码变更必须先在本地通过验证，才允许同步到远程。** 门禁由 `sync.sh` 强制执行——
没凭证、代码改过、凭证过期，任一情况都**拒绝同步且不推送任何内容**。

```bash
cd ops
python verify.py        # 阶段一：本地验证（必做）
./sync.sh --dev         # 阶段二：你手动触发同步
```

**最简单的方式：双击根目录的 `同步开关.bat`** —— 它会自动完成验证 + 同步，
并提供菜单让你选择开发环境 / 生产环境 / 仅验证。

完整规范见 **[docs/交付流程规范.md](docs/交付流程规范.md)**。

## 三条最常用的命令

```bash
# 1. 本地起服务改代码（端口 8100，自动重启，不碰服务器）
cd ops && ./local-dev.sh

# 2. 验证后同步到服务器
cd ops && python verify.py && ./sync.sh --dev

# 3. 登录服务器
ssh -F ops/secrets/sshcfg tapd
```

更多说明见 **[docs/调试指南.md](docs/调试指南.md)**。

---

## 线上环境

| | 地址 |
|---|---|
| 公网 HTTPS | `https://123.207.252.195` |
| 公网 HTTP | `http://123.207.252.195:8000` |
| 服务器 | 123.207.252.195（广州 ap-guangzhou-6，Ubuntu 24.04.4 LTS，2C2G） |
| 部署目录 | `/opt/tapd-workbench` |
| 登录 | `admin / At159357`（超管）、`dsy / 159357`（admin） |

---

## 修改代码的标准流程

```
1. 改 src/ 里的文件
2. git commit 记一笔
3. ops/sync.sh --dev  推到服务器热重载
4. 浏览器验证 https://123.207.252.195
5. ops/sync.sh --prod 切回生产
```

**不要直接在服务器上改代码**——`sync.sh` 会覆盖掉。万一已经改了，用 `ops/sync.sh --pull` 拉回本地。

---

## 安全红线（务必遵守）

1. **同步只碰代码**，永不覆盖服务器上的 `app.db`（真实数据）、`venv/`、`/etc/tapd-workbench.secret`
2. **禁用 `rsync --delete`**，会删掉服务器的 venv
3. **改完必须先本地语法检查**：`python -m py_compile src/app/app.py src/app/init_db.py`，不过则禁止同步
4. **重启只走 systemd**：`systemctl restart tapd-web`。`kill` 会被 3 秒拉起，`nohup` 必绑定失败
5. **验证以「特征字符串 grep」为准**，版本注释只是辅助
6. **数据库在服务器上是唯一真实库**；本地 `src/app.db` 只是副本
7. **SSH 私钥不外传**：`ops/secrets/tapd_deploy_key`

---

## 目录里的两份"历史"

- **`docs/调试链路地图.md`** —— 旧 WSL 时期的链路记录，含 6 条安全红线和血泪坑清单。虽然架构已迁到云上，那些坑依然适用（比如 `index.html` 的 CRLF、`init_db` 幂等行为、systemd 抢端口）
- **`archive/legacy/`** —— 旧 Windows 启动脚本和 `index.html.bak.*` 历史备份，留作追溯用
