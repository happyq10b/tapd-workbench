# MEMORY.md —— FISP 项目长期纪律（管家维护 · 3000 字内）

## 🟡 选人层级链终态（2026-11-17 #139 · 改 ACL/选人相关代码前必读）
- **层级链**：看板层=归属部门池（None=不限）→ 板块层⊆看板 ACL → 事项层⊆板块 ACL（缺省回退看板 ACL）→ 子事项⊆父事项 owner+cc（姓名直比、**不豁免管理员**）。
- **部门约束=附加交集**：未配归属部门时池=上级 ACL 全量（不是不限！#139 修订，与前端 colPickPool 同口径）。
- **口径陷阱**：cards.owner/cc 存**姓名**（';' 分隔）、boards/board_columns 存**账号**（',' 分隔）——两层数据语义不同，过滤时必须映射（_account_name_map）。
- **写入=池外除名+响应 removed**（前端 toast）；读取=/api/me 与 visible_columns 下发前过滤。存量人员编辑放行（前端 origNames / 后端 cur 原值并入 allowed）。
- **管理员豁免**：板块/事项层 is_admin → allowed=None；子事项层不豁免。
- `PUT /boards/{bid}/acl` 只写 owner、**忽略请求里的 participants**（保留旧值设计）——设参与人走 `/participants` 端点。
- ⚠️ 测池过滤必须用**非管理员**夹具账号（admin token 触发豁免测不出）。

## 🔴 数据安全守则（2026-11-17 用户立规 · 所有编辑操作的基本规则 · 全文见 HANDOFF §3.4）
> 背景：#122 误删真实看板 BCP1793717004248（37 行，已从备份回补）；更早 prune 误删用户 local 快照。
- **D1 写前备份/记录**：DB 写操作前文件级备份 `ops/backup_db_<日期>_<用途>.db`；架构数据（org_nodes/workgroups/board_config/boards）与配置（bat 菜单/sync.sh/权限参数）改动前 SELECT 存档原行 + git 单一职责提交（可独立 revert）。
- **D2 最小化可回滚**：🔴 DELETE/UPDATE 禁止裸 LIKE/宽匹配（`__p%` 的 `_` 是通配符，5 次踩坑）——先 SELECT 全量核对 → 精确主键 IN 执行，行数不符=停；能加行/加字段不改旧行/删列；批量先在副本库演练。
- **D3 改后验证**：行数守恒 → `ops/audit_db_vs_backup_20261117.py` 全表 diff（零非预期差异）→ verify 7/7 + 只读 API 抽查（/api/me 看板数、/api/org/tree 节点数）→ 回读校验落盘。
- **D4 高危先申报**：快照 apply/rollback/prune/删快照/批量写/服务器库写/crontab 变更 → 说明影响范围与可逆性 → 用户明确同意 → 执行 → 当轮汇报；服务器库默认只读。
- **D5 夹具纪律**（§3.3 并行生效）：前缀 + try/finally 自清理 + 零残留自查；一次性手工实测数据测完立刻删（#122 `__probe_B` 即违反此条）。

## 🟢 协作分工规则（2026-11-19 用户立规 · 全文见 HANDOFF §3.5）
- **可留给用户实测**：浏览器人工验证（视觉确认/真实登录/强刷复现）、线上最终确认、用户主动认领的步骤 —— 留给用户时**写清操作步骤与预期结果**，等反馈再继续。
- **Agent 直接完成**：代码改动、静态检查、自动化测试脚本、本地只读查询、留痕提交。
- **每轮交付时明确列分工清单**：哪些已完成、哪些待用户实测反馈 —— 不默认全包。

## 项目固定事实
- 双仓库：顶层（docs/ops/HANDOFF）+ src 子模块；提交顺序先 src 后顶层。
- 服务 127.0.0.1:8100（ops/local-ctl.py）；venv ops/.localvenv/Scripts/python.exe；测试夹具前缀 `__tNNN_`。
- 服务器快照通道铁律：自动任务只「拍」不「应用」；apply/rollback 仅人工入口（#125 审计）。
- 服务器 crontab 仅 `30 1 * * * tapd snap prod`（dev 条目已拆，T-194）。
