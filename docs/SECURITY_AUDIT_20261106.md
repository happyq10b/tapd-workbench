# 安全审计报告 —— 发布到服务器后的风险评估与防护方案

> 审计日期：2026-11-06 · 基于代码实证（非泛泛而谈）：对 app.py 全部 105 条路由、
> 静态服务、认证机制、SQL 构造逐项核查。结论标注：✅ 已有保障 / 🔴 高风险 / 🟡 中风险。

---

## 一、普通用户登录后，能否获取后台脚本、接口逻辑、数据库数据？

### 1.1 身份验证与权限控制

✅ **已有保障（代码实证）**
- 密码存储：PBKDF2-HMAC-SHA256 **10 万轮 + 8 字节随机盐**（`hash_pw`），无明文可逆。
- 会话令牌：HMAC-SHA256 签名 token + 过期时间；校验用 `hmac.compare_digest`（防时序攻击）；WebSocket 同样验 token。
- 登录防爆破：连续失败 **10 次 → 账号永久锁定**（login_attempts 表，需管理员重置），并有 lock-status 查询端点。
- 路由鉴权覆盖（全量扫描）：105 条路由中仅 **5 条无需登录**——登录接口本身、锁定状态查询、登录页、静态白名单资源，**其余 100% 强制 Bearer 认证**，并按 editor/writer/admin 分级。

🔴 **R1（最高优先级）：签名密钥有「出厂默认值」**
- 代码：`SECRET = os.environ.get('APP_SECRET', 'tapd-webapp-dev-secret-change-me')`。
- 若服务器 systemd 服务**未设置** `APP_SECRET` 环境变量，攻击者只要知道这个公开的默认串，即可**离线伪造任意用户（含 admin）的合法 token**——这是能拿到全库数据的唯一捷径。
- **防护措施（上线前必做）**：
  ```bash
  # 服务器上生成随机密钥并注入服务
  python3 -c "import secrets;print(secrets.token_hex(48))" > /etc/tapd/secret && chmod 600 /etc/tapd/secret
  # tapd-web.service 增加：EnvironmentFile=/etc/tapd/env  （env 内写 APP_SECRET=...）
  systemctl daemon-reload && systemctl restart tapd-web
  ```
  并核对 `Environment=` 确认非默认值（本地开发脚本里的 `local-dev-secret` 与生产无关）。

🟡 **R4：token 无服务端吊销**——登出只是前端丢弃 token，令牌到期前一直有效。防护：适当缩短 `TOKEN_TTL`；如需强制踢人，加服务端黑名单（按用户维度记录失效时间戳）。

### 1.2 接口鉴权与越权

✅ **已有保障**
- 数据层可见性：所有读接口过 `user_allowed` 架构可见性模型（看板/板块双层），写接口过 `check_board_access` / `check_card_access`，更新带乐观锁（version）。
- 上一轮越权读修复（#67 系列）已把可见性校验下沉到评论/子事项等子资源。

🟡 **R3：`/api/export`（xlsx 导出）任何登录用户可用**——只读 viewer 也能导出其可见范围的全部数据。防护建议：导出收紧为 editor 及以上，或对 viewer 关闭导出入口；该接口与 `/api/cards?size=2000` 是「批量拉数」的最大出口，见防爬章节限流。

### 1.3 后台脚本与代码本身

✅ **已有保障**
- 服务端代码（app.py / app.db）**不在任何静态路由下**：`/static/{filename}` 走硬编码白名单字典（当前仅一张默认头像图），不存在路径穿越；其余 404。
- SQL 全量参数化（`?` 占位）：f-string 动态 SQL 仅出现在**列名白名单**（`fields` 经 CARD_FIELDS 过滤）与 `IN (?,?)` 占位符展开，值一律参数绑定——无 SQL 注入入口。

🟡 **R5：部署层检查**——app.py 不暴露 ≠ nginx 不暴露。上线自检两项：
```bash
curl -I https://你的域名/app.db        # 必须非 200
grep -r "root\s*/" /etc/nginx/sites-enabled/   # 确认 root 指向静态目录而非代码目录
```

### 1.4 数据库数据

- 直连路径：数据库文件在代码目录内，应用层不对外提供文件下载 → 普通用户**无法通过 HTTP 拿到库文件**。
- 敏感字段：密码只有哈希；成员手机号/身份证等未存储（当前模型无此字段）。
- 审计：全部导入/导出/删除均有 `audit_logs` 记录（操作者/IP/结果），可追溯。

---

## 二、爬虫批量抓取风险

现状：应用层**暂无限流、验证码、UA 检测、robots.txt**——匿名者扫不到数据（需登录），但**一个合法账号脚本化拉取**是现实威胁（网站面向内部团队，账号泄露 = 数据被批量导出）。

### 风险面（按可批量拉取程度排序）
1. `/api/export/xlsx`：一次导出全部可见数据（xlsx）
2. `/api/cards?size=2000&board_ids=…`：分页全量拉取
3. `/api/boards` / `/api/filter-options`：结构枚举

### 防护方案（三层，按投入排序）

**L1 · 立即可做（部署层，零代码改动）**
- nginx 限流（对 /api 按 IP 限速，登录口更严）：
  ```nginx
  limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
  location /api/ { limit_req zone=api burst=20 nodelay; proxy_pass http://127.0.0.1:8000; }
  location = /api/login { limit_req zone=api burst=5 nodelay; ... }
  ```
- 加 `robots.txt`（Disallow: /api/ /static/），并关闭任何目录列表。
- 强制 HTTPS（Lighthouse 免费证书）——token 走明文 HTTP 等于公开。

**L2 · 短期（应用层，小改动）**
- 慢速限流中间件（slowapi）：登录 5 次/分钟/IP、普通 API 120 次/分钟/用户；超限 429。
- `/api/export/xlsx` 收紧为 editor+，并限每人每日 N 次（防「合法账号当爬虫」）。
- UA 检测：nginx `$http_user_agent` 空值/常见脚本 UA（python-requests、curl、Scrapy）直接 403——内部系统无 legit 脚本流量时收益高、误伤低。

**L3 · 可选（按需）**
- 登录验证码：已有 10 次失败锁定兜底，若上线后发现撞库尝试再加图形/行为验证码。
- 数据水印：导出 xlsx 尾行写入操作者+时间戳，泄露可溯源（audit_logs 已有记录，双保险）。

---

## 三、结论

| 问题 | 结论 |
|---|---|
| 普通用户能拿到后台脚本/代码吗？ | **不能**——代码不在任何路由下，静态服务走硬编码白名单 |
| 能通过 API 拿到越权数据吗？ | **不能**——105 条路由鉴权全覆盖 + 架构双层可见性（前提：修掉 R1 默认密钥） |
| 爬虫能批量抓吗？ | **匿名爬虫不能**（全部需登录）；**合法账号脚本化拉取可行**——按 L1/L2 加限流与导出收紧 |
| 最优先要做的三件事 | ① 服务器设置随机 APP_SECRET（R1）② nginx 限流 + HTTPS（L1）③ 导出收紧 editor+（R3） |
