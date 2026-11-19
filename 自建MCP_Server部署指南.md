# 自建 MCP Server 部署指南

> 场景：私有云服务器上已有网站，希望通过 MCP 接口让 Agent（豆包 / Claude / Cursor 等）安全访问网站数据。
> 规模：约 70 个用户，数据库为 SQLite。

---

## 一、背景与核心结论

### 1.1 你的场景

- 网站部署在私有云服务器上
- 数据库：SQLite（单文件）
- 用户规模：70 人以内
- 需求：让 Agent 能调用网站数据，或打包成 Skill 给豆包使用

### 1.2 核心结论

**完全可行，且 70 人 + SQLite 属于轻量场景，单进程即可承载。** 不需要 Redis、不需要多实例、不需要负载均衡，但 SQLite 有几个特定配置必须做对。

---

## 二、MCP 基础概念

### 2.1 什么是 MCP

**MCP（Model Context Protocol，模型上下文协议）** 是 Anthropic 推出的开放协议，用于让 LLM / Agent 标准化地连接外部数据源和工具。

- 本质：一个 JSON-RPC 框架，Agent 作为 Client，你的服务作为 Server
- 作用：标准化注册工具、发现资源、多轮工具调用、权限控制

### 2.2 层次关系

| 层次 | 是什么 | 谁来做 |
|---|---|---|
| MCP Server | 跑在你服务器上的进程，对外暴露工具接口 | 你写代码部署 |
| Agent 客户端 | 豆包 / Claude Desktop / Cursor 等 | 现成的 |
| Skill | 豆包生态里对"某类能力"的封装说明书 | 你可以做一层包装 |

> **MCP 和 Skill 不是二选一，是两层东西。** 推荐：网站 → 旁边跑 MCP Server → Agent 通过 MCP 调用 → 再把这个 MCP 配置打包成 Skill 给豆包用。

---

## 三、接入方式选择

### 3.1 路径一：直接开 MCP 接口（推荐）

#### 传输方式选型

| 传输方式 | 适用场景 | 你的场景能否用 |
|---|---|---|
| `stdio` | 本地子进程，Agent 和 MCP 跑在同一台机器 | ❌ 网站在私有云，Agent 在外面 |
| **Streamable HTTP**（新标准） | 远程 HTTP endpoint，单条 POST | ✅ 首选 |
| **SSE**（旧标准） | Server-Sent Events 长连接 | ✅ 兼容老客户端 |

#### 落地步骤

1. **选框架**：Python 用 FastMCP 或官方 `mcp` SDK；TypeScript 用 `@modelcontextprotocol/sdk`
2. **写工具**：把网站的数据访问逻辑包成一个个 `@tool` 函数（如 `get_order(id)`、`query_post(keyword)`）
3. **以 HTTP 模式启动**：`mcp.run(transport="http", host="0.0.0.0", port=8000)`
4. **前面套 Nginx + HTTPS**
5. **加认证**：JWT Bearer Token 或 API Key

### 3.2 路径二：打包成 Skill

Skill 和 MCP 是包装关系，有两种做法：

- **做法 A**：Skill 的 SKILL.md 里写死你的 MCP endpoint，Agent 加载 Skill 后知道怎么连
- **做法 B**：Skill 直接调网站已有的 REST API，不走 MCP

#### 什么时候走 MCP

- 工具数量多（10+），需要结构化注册和发现
- 需要多轮工具调用、有状态会话
- 想同时给豆包、Claude、Cursor 等多个客户端用
- 需要细粒度权限控制和审计

#### 什么时候直接 REST 就够

- 就是读几个数据接口，简单 GET/POST
- 只给豆包一家用

---

## 四、高并发通用注意事项（参考）

> 以下是通用生产架构要点，70 人 + SQLite 场景下大部分不需要，但了解原理有助于未来扩容。

### 4.1 协议版本分水岭

MCP 在 2026 年 7 月新规范（SEP-2567）做了关键改动：

| | 旧版（有状态） | 新版（stateless HTTP） |
|---|---|---|
| Session 管理 | 每个连接一个 `Mcp-Session-Id`，存在进程内存 | 协议层移除 session 概念 |
| 多实例部署 | 必须 sticky session | round-robin 即可 |
| 扩缩容 | 重启丢状态 | 可缩到零、serverless |

**部署时务必开 stateless 模式**（FastMCP 里是 `stateless_http=True`），否则多 worker 会出问题。

### 4.2 生产级架构（大规模场景参考）

```
Agent 客户端（N 个用户）
        │
        ▼
   Nginx / 负载均衡（HTTPS + 限流 + WAF）
        │
   ┌────┴────┬────────┐
   ▼         ▼        ▼
MCP-1     MCP-2     MCP-3   ← 无状态
   │         │        │
   └────┬────┴────────┘
        ▼
      Redis  ← session / 缓存
        ▼
   数据库连接池（PgBouncer 等）
        ▼
   数据库
```

### 4.3 常见生产级瓶颈

1. **数据库连接池打满**：每个客户端开独立连接 → `max_connections` 秒爆
2. **Session 放进程内存**：多实例部署后 sticky session 配置复杂
3. **Nginx 默认配置**：SSE 需要关 buffering、加长超时
4. **慢工具阻塞事件循环**：长耗时任务要异步化（task 队列）

---

## 五、轻量场景方案（SQLite + 70 人）

### 5.1 最简架构

```
70 个用户的 Agent 客户端
        │
        ▼
   Nginx（HTTPS + 域名 + 简单鉴权）
        │
        ▼
   单进程 FastMCP（异步，systemd 托管）
        │
        ▼
   SQLite 文件（WAL 模式，磁盘持久化）
```

**一台 2核4G 小服务器绰绰有余。**

### 5.2 SQLite 必须做的 3 件事

#### ① 开启 WAL 模式（最重要）

SQLite 默认 journal 模式下，写操作会锁整个数据库文件。70 人里只要有一个人在写，其他人全都读不了，直接报 `database is locked`。

```sql
PRAGMA journal_mode = WAL;
```

开了 WAL 之后：
- 读不阻塞写，写不阻塞读
- 70 人同时查、偶尔有人写，完全不卡

> WAL 是持久化到文件里的，设置一次即可，但代码里每次连接保险起见都执行一次。

#### ② 设置 busy_timeout

遇到锁的时候不要立刻报错，等一会儿再试：

```sql
PRAGMA busy_timeout = 5000;  -- 等 5 秒
```

#### ③ 用异步驱动访问 SQLite

FastMCP 本身是异步框架，访问 SQLite 必须用异步驱动，不要用同步的 `sqlite3`：

```python
# 正确
import aiosqlite

# 错误（会阻塞整个事件循环）
import sqlite3
```

### 5.3 为什么不要开多 worker

70 人规模下**单进程异步就够了**。

- SQLite 是文件级，多进程打开同一个文件不会提升写并发
- WAL 模式下多进程读没问题，但写还是全局串行
- 多 worker 反而增加锁冲突概率

**建议：单进程异步模式跑 FastMCP，不要开 gunicorn 多 worker。**

---

## 六、多用户注意事项

### 6.1 安全红线

| 事项 | 做法 |
|---|---|
| 数据隔离 | 每个工具调用从 JWT token 解出 user_id，SQL 查询强制 `WHERE user_id = ?`，**永远不要信任客户端传的用户 ID** |
| 认证 | 必须 JWT / API Key，不能裸奔 |
| HTTPS | 必须有，Let's Encrypt 免费证书即可 |
| 最小权限 | 工具能读就别给写，能按 ID 查就别给全表扫描 |
| 暴露方式 | 不要直接把 MCP 端口暴露公网，建议走 Nginx + 鉴权层 |

### 6.2 运维要点

- **日志打全**：谁、什么时候、调了什么工具、传了什么参数、返回了什么
- **审计可溯源**：出问题能查到具体用户和调用链
- **备份**：SQLite 就是一个文件，每天定时备份
  ```bash
  sqlite3 your.db ".backup '/backup/your_$(date +%F).db'"
  ```
  > 不要直接 `cp`，WAL 模式下直接拷贝可能拷到不一致状态
- **容器持久化**：如果跑在 Docker 里，SQLite 文件一定要挂载到宿主机持久化目录

---

## 七、Nginx 关键配置

MCP 走 SSE / Streamable HTTP，Nginx 默认配置会挂：

```nginx
location /mcp {
    proxy_pass http://mcp_upstream;
    proxy_buffering off;          # SSE 必须关，否则事件推不出来
    proxy_read_timeout 3600s;     # 默认 60s，长工具调用必断
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

> 这两个配置不改，长任务跑 60 秒就被掐断。

---

## 八、Checklist（按优先级）

### 必做

- [ ] 选择 HTTP / SSE 传输模式（不要用 stdio）
- [ ] 开启 SQLite WAL 模式：`PRAGMA journal_mode = WAL`
- [ ] 设置 busy_timeout：`PRAGMA busy_timeout = 5000`
- [ ] 使用异步驱动（aiosqlite），不要用同步 sqlite3
- [ ] Nginx 反代：关 buffering、加长超时
- [ ] HTTPS 证书
- [ ] JWT / API Key 鉴权
- [ ] user_id 强制注入查询，防越权

### 推荐

- [ ] 单进程异步跑（systemd 托管，崩溃自动重启）
- [ ] SQLite 文件挂载持久化（容器场景）
- [ ] 每日自动备份
- [ ] 全量调用日志
- [ ] 简单限流（按用户，每分钟 N 次）

### 可选（未来扩容再做）

- [ ] Redis 缓存热点查询
- [ ] 多实例 + 负载均衡
- [ ] 慢工具异步化（task 队列）
- [ ] 熔断外部 API 调用

---

## 九、踩坑清单

| 坑 | 表现 | 解法 |
|---|---|---|
| 没开 WAL | 多人写时 `database is locked` | `PRAGMA journal_mode=WAL` |
| 用同步 sqlite3 | 一个慢查询所有人都卡 | 换 aiosqlite |
| Nginx 没关 buffering | SSE 事件推不出来 | `proxy_buffering off` |
| Nginx 超时太短 | 长任务 60 秒被掐断 | `proxy_read_timeout 3600s` |
| 多 worker 跑 SQLite | 锁冲突更多 | 单进程异步 |
| 容器里 SQLite 没挂载 | 重启数据全没 | 挂载到宿主机目录 |
| 直接 cp 备份 | WAL 模式下备份不一致 | 用 `.backup` 命令 |
| 信任客户端传的 user_id | 越权查询别人数据 | user_id 从 JWT 解出 |

---

## 九、社区实战策略参考

以下是社区里真实部署 MCP Server 踩坑后总结出的成熟做法，按重要性排序。

### 9.1 安全防线：SQL 黑白名单 + 只读连接（必做）

社区最常踩的坑是 Prompt 注入导致 AI 执行删库。双层防御：

**第一层：代码里的 SQL 白名单校验**
```python
SQL_DENYLIST = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "RENAME", "GRANT", "REVOKE"]

def is_query_safe(sql: str) -> bool:
    upper_sql = sql.strip().upper()
    if not upper_sql.startswith("SELECT"):   # 只允许 SELECT 开头
        return False
    for keyword in SQL_DENYLIST:              # 黑名单二次拦截
        if keyword in upper_sql:
            return False
    return True
```

**第二层：SQLite 物理只读连接**
```python
# 用 URI 模式以只读方式打开，即使被注入也写不了
conn_uri = f"file:{DB_PATH}?mode=ro"
conn = sqlite3.connect(conn_uri, uri=True)
```

> 这两层叠起来，即使 AI 被恶意 Prompt 诱导执行 DROP TABLE，也会被物理拦截。["https://www.xbstack.com/ai/mcp-server-sqlite/"]

### 9.2 大结果集防护：强制分页 + 摘要策略

AI 很容易生成 `SELECT * FROM 大表`，一次性返回几千行，把上下文撑爆、服务器卡死。

**Server 端强制注入 LIMIT**：
```python
@mcp.tool()
def query_db(sql: str, limit: int = 50, offset: int = 0) -> str:
    # 不管 AI 传什么 SQL，尾部强行拼上 LIMIT
    final_sql = f"{sql.strip().rstrip(';')} LIMIT {limit} OFFSET {offset}"
```

**结果摘要策略**：超过 30 行只返回首尾各 5 行 + 总行数，引导 AI 用分页或聚合查询。

### 9.3 连接稳定性：防防火墙 idle 断连（高频踩坑）

社区真实案例：服务器跑起来后，用户反馈"时好时坏"。查了半天发现是**云厂商防火墙默认 60 秒断开 idle 连接**，而 MCP 长流式传输时几秒钟没数据就被判定为 idle。

**社区验证有效的 Nginx 配置**：
```nginx
location / {
    proxy_pass http://localhost:8080;
    proxy_http_version 1.1;
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;      # 5 分钟，给大文档流式留足时间
    proxy_read_timeout 300s;
    proxy_buffering off;
    proxy_set_header Connection "";
    proxy_set_header Proxy-Connection "keep-alive";
}
```

**Node.js/Express 侧也要开 keep-alive**：
```javascript
server.keepAliveTimeout = 30 * 1000;
server.headersTimeout = 60 * 1000;
```

> 这一套配置能解决 99% 的"随机超时"问题。["https://mcp-find.org/learn/mcp-production-deployment"]

### 9.4 内存泄漏防护：有界缓存

社区另一个经典坑：为了加速做了个缓存（比如 embedding 缓存），但**没设淘汰策略**，跑两天内存涨满被 OOM killer 杀掉，凌晨服务挂了没人知道。

**正确做法：用 LRU 缓存 + 硬上限**
```python
from cachetools import LRUCache

# 最多缓存 200MB，满了自动淘汰最久没用的
cache = LRUCache(maxsize=200)

# 而不是：
# cache = {}  # 无界，迟早爆
```

> 部署前一定要跑 24 小时压测看内存曲线，本地测 50 个请求根本测不出来。["https://mcp-find.org/learn/mcp-production-deployment"]

### 9.5 上游 API 限流防护

如果你的 MCP 工具内部还会调外部 API（比如 OpenAI、Notion），多用户并发时很容易触发上游 429。

社区四件套：
1. **LRU 缓存**：相同请求不重复打上游，能减少 80-90% 的调用
2. **并发队列**：限制同时打上游的请求数（比如最多 5 个并发），其余排队
3. **指数退避重试**：遇到 429 自动等待重试，不让用户刷新
4. **多 API key 轮换**：多个 key 分担限额

### 9.6 常见报错速查表（社区高频）

| 报错 | 原因 | 解法 |
|---|---|---|
| `database is locked` | 没开 WAL，写锁阻塞读 | `PRAGMA journal_mode=WAL` |
| `JSON-RPC parse error` | 调试 print 污染了 stdout | 所有日志强制走 `sys.stderr` |
| `attempt to write a readonly database` | AI 被诱导写库，被只读连接拦截了 | 正常防御，捕获后返回友好提示 |
| `TimeoutError 30000ms` | 全表扫描 / 缺索引 | 强制 LIMIT，给高频字段加索引 |
| `spawn python ENOENT` | 虚拟环境路径配错 | command 写 venv 里 python 的绝对路径 |
| 时好时坏、随机超时 | 防火墙断 idle 连接 | Nginx keep-alive + 300s 超时 |
| 跑两天服务挂了 | 内存泄漏被 OOM 杀 | LRU 缓存 + systemd 自动重启 + 内存告警 |

### 9.7 社区参考资源

- **XBSTACK：MCP Server 实战（SQLite 5 步法）** — 最贴近你的场景，有完整代码示例["https://www.xbstack.com/ai/mcp-server-sqlite/"]
- **MCP Find：生产部署真实失败案例** — 三个真实事故的完整复盘["https://mcp-find.org/learn/mcp-production-deployment"]
- **SHAttered：安全构建 MCP Server 12 步** — 安全 checklist 很全["https://shattered.io/build-secure-mcp-server-claude-2026/"]
- **FastMCP 官方文档** — HTTP 部署、task 队列、workers 配置["https://gofastmcp.com/deployment/http"]

---

## 十、一句话总结

> **70 人 + SQLite + 单进程 FastMCP + WAL 模式 + Nginx HTTPS 反代 + JWT 鉴权**，就能跑得很稳。Redis、连接池、多实例这些是给几千几万人用的，当前规模完全不需要上。
>
> 真正要花精力的不是性能，而是**鉴权、数据隔离、日志审计**这三件事。
