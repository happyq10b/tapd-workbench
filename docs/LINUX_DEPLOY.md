# Linux 部署注意清单（TAPD 看板 · 腾讯轻量云 Ubuntu 24.04）

> 用途：生产部署（`123.207.252.195`）前的**注意点与部署后必验项**，与 `DEPLOY.md`（分步部署）配套使用。
> 更新：2026-08-21 —— 纳入 WebSocket 依赖修复，依赖清单已双端可装。

## 0. 一句话结论
本项目代码**无 Windows 绑定**（路径用 `os.path.join`、编码 UTF-8、DB 相对路径），Windows 调试（WSL）与 Linux 生产同一套代码。**依赖清单 `requirements.txt` 已含 `websockets`（纯 Python，双端可装），生产 `pip install -r` 后 WebSocket 实时协作可直接工作。**

## 1. 依赖（最重要的坑）
```bash
cd /opt/tapd-web
python3 -m venv venv
./venv/bin/pip install -r requirements.txt   # fastapi + uvicorn + websockets
```
- ✅ `requirements.txt` 已包含 `websockets>=12`。
- ⚠️ **不要把 `uvicorn` 改成 `uvicorn[standard]`**：它依赖 `uvloop`，**无 Windows wheel**——Windows 开发机上 `pip install -r` 会失败，破坏"一套清单双端可装"。要 WS 用 `websockets` 即可。
- ⚠️ 缺 `websockets` 的症状：日志报 `No supported WebSocket library detected`，前端 `/ws` 请求 404，多人实时协作（卡片锁定/变更广播）失效。

## 2. 文件与目录
| 项 | 要求 |
|---|---|
| `data/` 目录 | **必须一起部署**（首次启动 `init_db` 靠 `data/全部看板_2026年度_总宽表.csv` 导入） |
| `static/`、`app/`、`requirements.txt`、`manage_users.py`、`users.json` | 全部带上（DEPLOY.md 第五步起用） |
| `app.db` | **不要从 Windows/WSL 拷贝**——生产全新初始化，服务首次启动自动建表 + 导 CSV + 派生看板 |
| `venv/` | 生产现场新建，绝不从别处拷贝 |

## 3. 环境变量
- `APP_SECRET`：生产 systemd 单元里设为**强随机值**（调试环境 `wsl-test-secret-2026` 只是开发值，不可用于生产）。
- 生成示例：`openssl rand -hex 32`。
- 改 secret 会令已发 token 全部失效（用户需重新登录），属预期行为。

## 4. systemd 单元（参考）
```ini
[Unit]
Description=TAPD Kanban Web App
After=network.target

[Service]
WorkingDirectory=/opt/tapd-web
ExecStart=/opt/tapd-web/venv/bin/uvicorn app.app:app --host 0.0.0.0 --port 8000
Environment=APP_SECRET=<强随机值>
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
- 启停：`systemctl daemon-reload && systemctl enable --now tapd-web`；改代码后 `systemctl restart tapd-web`。
- ⚠️ `Restart=always`：代码有语法/导入错误会 crash-loop（3 秒拉起失败循环）——**改 `app.py` 前先 `python -m py_compile app/app.py`**；crash 时先 `systemctl stop tapd-web` 停住再看 `journalctl -u tapd-web -n 50`。

## 5. 其它兼容性
- `index.html` 是 CRLF 行尾：Linux 上浏览器解析无影响，直接拷贝/rsync 即可（无需转换）。
- 数据库初始化幂等：`CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE`；**仅当 cards 表为空才重导 CSV**——清库重启会重灌，清库前确认有意为之。

## 6. 部署后必验清单（一条条过）
```bash
systemctl is-active tapd-web                                              # ① active
curl -s localhost:8000/ | grep -o "2026-08-2[0-9] [0-9][0-9]:[0-9][0-9]"    # ② served 版本注释
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/login             # ③ 200
journalctl -u tapd-web -n 20 | grep -i "websocket\|error"                 # ④ 无 WS 警告/报错
```
**WS 握手实测**（生产机 python 已随 venv 装 websockets，直接用）：
```python
import asyncio, json, base64, hmac, hashlib, time, websockets
SECRET="<生产APP_SECRET>"
def b64e(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
body=b64e(json.dumps({"u":"admin","exp":int(time.time())+3600}).encode())
sig=b64e(hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).digest())
async def main():
    async with websockets.connect("ws://localhost:8000/ws?token="+body+"."+sig, open_timeout=5) as ws:
        print("WS HANDSHAKE OK (101)")
asyncio.run(main())
```
- 再用浏览器登录 `http://123.207.252.195:8000/`，开两个窗口改同一张卡，验证实时锁定/广播。
- 功能抽查：`GET /api/me`（看板数）、`GET /api/boards`（真实看板+卡片数+配置）。

## 7. 调试环境（WSL）与生产差异速查
| 项 | WSL 调试 | Linux 生产 |
|---|---|---|
| 路径 | `/root/tapd_webapp` | `/opt/tapd-web` |
| APP_SECRET | `wsl-test-secret-2026`（开发值） | 强随机（`openssl rand -hex 32`） |
| 数据 | 调试库（可随意改） | 生产库（改前备份） |
| 端口 | `0.0.0.0:8000` | `0.0.0.0:8000`（如需公网注意安全组） |
