# 交接记录 · 全量索引（L2 索引层）

> **本文件是本项目交接记录的「全量目录」。**
> `HANDOFF.md` 的「六、变更记录索引」只保留**近 40 行**（主文档体量上限），
> 更早的记录行会移到这里 —— **只增不删**，永远是查历史的第一入口。
>
> 维护者：**交接管家**。执行 Agent 追加自己的记录时，在 `HANDOFF.md` §六 追加一行；
> 管家在归档时把超出部分连同**正文路径**一并登记到本表。

---

## 一、查找路径（三步，别通读）

```
① HANDOFF.md §六 变更记录索引          ← 近 40 行，日常查这里
        ↓ 没找到？
② docs/handoff/INDEX.md（本文件）        ← 全量目录，每条一行 + 正文路径
        ↓ 按「正文路径」列取文件
③ docs/handoff/records/R00NN-<标题>.md  ← 单条完整正文，一次只读一篇
```

> 🔴 **给路径，不给链接。** 本项目所有跨文档引用一律写**工作区相对路径 + 章节锚点**，
> 不写 URL、不写"见上方链接" —— 链接对 LLM 不可点击，路径才能直接 Read / Grep。

---

## 二、全量记录索引

| 序号 | 日期 | 署名 | 类型 | 摘要 | 涉及文件 | 正文路径 | 归档状态 |
|---|---|---|---|---|---|---|---|
| #1 | 2026-11-02 | UI设计师 | 流程建设 | 建立多 Agent 共用交接机制：署名制 + 开工前必读 + 并发写入守则 | `HANDOFF.md` | `docs/handoff/records/R0001-2026-11-02-建立多 Agent 共用交接机制.md` |  已归档（批次 1） 
| #2 | 2026-11-02 | UI设计师 | 流程建设 | 文档升级为多 Agent 共用：开工前必读五步、并发写入守则、跨角色禁令、附录 A | `HANDOFF.md` | `docs/handoff/records/R0002-2026-11-02-文档升级为多 Agent 共用格式.md` |  已归档（批次 1） 
| #3 | 2026-11-02 | UI设计师 | 基线校准 | 同步期间检测到并发改动 `src/static/index.html`（+91 行）→ 全量复核并修正行号基线 | `HANDOFF.md` | `docs/handoff/records/R0003-2026-11-02-并发改动检出与行号基线校准.md` |  已归档（批次 1） 
| #4 | 2026-11-02 | UI设计师 | 流程建设 | 新增「待转交事项」章节：范围外问题只登记不改动 + 处置纪律 | `HANDOFF.md` | `docs/handoff/records/R0004-2026-11-02-新增待转交事项章节.md` |  已归档（批次 1） 
| #5 | 2026-11-02 | UI设计师 | 流程建设 | 新增「Agent 台账」章节：上线/下线登记 + 署名唯一性 | `HANDOFF.md` | `docs/handoff/records/R0005-2026-11-02-新增 Agent 台账章节.md` |  已归档（批次 1） 
| #6 | 2026-11-02 | UI设计师 | 流程建设 | 新增「阅读分层」导航：必读/按需/增量三分 + 归档机制 | `HANDOFF.md`、`docs/handoff-archive.md` | `docs/handoff/records/R0006-2026-11-02-新增阅读分层导航.md` |  已归档（批次 1） 
| #7 | 2026-11-02 | 主设计师 | 流程建设 | 上线登记 + 认领并闭环 T-001（署名留痕 / 门禁 7/7 / 补跑 5 组测试 / `OWNER_NONE` 语义边界） | `HANDOFF.md` | `docs/handoff/records/R0007-2026-11-02-上线登记与闭环 T-001.md` |  已归档（批次 1） 
| #8 | 2026-11-02 | 主设计师 | 流程建设 | 新增 §0.3.1「主设计师 ↔ UI设计师 派工边界」：按活分类派工，分文件不分行 | `HANDOFF.md` | `docs/handoff/records/R0008-2026-11-02-新增主设计师与 UI设计师 派工边界.md` |  已归档（批次 1） 
| #9 | 2026-11-02 | 主设计师 | 流程建设 | **规则修订**：「下线」= 被用户开除；**派工权归用户** | `HANDOFF.md` | `docs/handoff/records/R0009-2026-11-02-规则修订-下线等于开除与派工权归用户.md` |  已归档（批次 1） 
| #10 | 2026-11-02 | UI设计师 | 界面调整 | 用户提 5 项 UI 修复全部完成：架构部门排序 / 可选板块两行+滚动 / 两带归一整体框 / 筛选 chips 折叠 / 窄屏布局锁定 | `src/static/index.html`、`docs/UI问题排查清单.md` | `docs/handoff/records/R0010-2026-11-02-5 项 UI 修复与问题排查清单.md` |  已归档（批次 1） 
| #11 | 2026-11-02 | UI设计师 | 界面调整 | 排查清单中 UI 职责范围内的问题全部修复：焦点环 / 点击目标≥24px / 对比度≥AA / 字号 / aria-label | `src/static/index.html`、`ops/ui_audit_scan.py` | `docs/handoff/records/R0011-2026-11-02-UI 职责范围内问题全部修复.md` |  已归档（批次 1） 
| #12 | 2026-11-02 | UI设计师 | 流程建设 | 固化「每次提交后同步工作日志」为硬性规矩（§0.2.1） | `HANDOFF.md`、`.workbuddy/memory/2026-11-02.md` | `docs/handoff/records/R0012-2026-11-02-固化提交后同步工作日志.md` |  已归档（批次 1） 
| #13 | 2026-11-02 | UI设计师 | 流程记录 | 检出主设计师闭环 T-002 / T-003 → 交接机制首次完整跑通，UI 侧零改动 | `HANDOFF.md` | `docs/handoff/records/R0013-2026-11-02-检出主设计师闭环 T-002 T-003.md` |  已归档（批次 1） 
| #14 | 2026-11-02 | 主设计师 | 功能逻辑+流程建设 | 闭环 T-002 / T-003 / T-004，新登记 T-005 | `src/static/index.html`、`ops/test-filter-ui.js`、`ops/ui_check_filter.py`、`src/.gitignore` | `docs/handoff/records/R0014-2026-11-02-闭环 T-002 T-003 T-004 新登记 T-005.md` |  已归档（批次 1） 
| #15 | 2026-11-02 | UI设计师 | 界面调整 | 闭环 T-005：需求5 窄屏锁定补齐 gap/padding/列数/字号/order 五项收敛 | `src/static/index.html` | `docs/handoff/records/R0015-2026-11-02-闭环 T-005 窄屏 4px 缺口.md` |  已归档（批次 1） 
| #16 | 2026-11-02 | 主设计师 | 功能逻辑 | 修复看板板块切换三处问题：切换联动 / 空状态提示 / 初始未选板块为空 | `src/static/index.html`、`src/app/app.py` | `docs/handoff/records/R0016-2026-11-02-修复看板板块切换三处问题.md` |  已归档（批次 1） 
| #17 | 2026-11-02 | 主设计师 | 后端 + 功能逻辑 | 统计带严格按个人权限：`/api/me` 的部门清单改为按权限过滤；新增 `ops/test_overview_perm.py`（23 断言）覆盖统计隔离 | `src/app/app.py`、`ops/test_overview_perm.py`、`ops/test-board-perm.js` | `docs/handoff/records/R0017-2026-11-02-统计带严格按个人权限.md` | 已归档（批次 1） |
| #18 | 2026-11-02 | **交接管家** | 流程建设 | 交接文档升级为**三层披露结构**：★ 当前状态摘要结论层 + §0.5 管家职责与写权限矩阵 + §0.6 版本/日期标注 + 开工与交接检查项；§六 加「正文路径」列；建 `docs/handoff/` 索引与归档区；§3.1 基线数字按实跑校正（80→144、44→54） | `HANDOFF.md`、`docs/交接记录文档管理方案.md`、`docs/handoff/INDEX.md` | 正文在 `HANDOFF.md` §七 #18 | 正文在 `HANDOFF.md` §七 #18 |
| #19 | 2026-11-02 | **交接管家** | 流程建设 | **交接管家上线登记**（§4.1）+ **权限边界写死**（§0.5.0：只管交接文档 + 根目录梳理，无权介入其他项目事项）；根目录盘点落 `docs/根目录梳理.md`；README 目录结构校准 | `HANDOFF.md`、`docs/根目录梳理.md`、`README.md` | 正文在 `HANDOFF.md` §七 #19 | 正文在 `HANDOFF.md` §七 #19 |
| #20 | 2026-11-02 | **交接管家** | 流程建设 | **首次归档（第 1 批）**：#1–#16 拆入 `docs/handoff/records/`（一期一文件），主文档 2408 → **1335 行**，§七 只留 #17–#19，§六 19 行全保留且路径指向归档；`工作转移手册.md` 入库；`TAPD地址.txt` 按用户指示保留原位 | `HANDOFF.md`、`docs/handoff/INDEX.md`、`docs/handoff/records/`、`工作转移手册.md` | 正文在 `HANDOFF.md` §七 #20 | 正文在 `HANDOFF.md` §七 #20 |
| #21 | 2026-11-02 | **主设计师** | 后端 + 功能逻辑 | 统一看板/板块/统计三层权限过滤：`/api/boards` 的 card_count 与 col_years 改走 `filter_rows`（此前只做看板级过滤 → 板块白名单收窄后卡片数仍显示全量，实测 6 vs 2）；`/api/boards/{id}/columns` 的 counts 一并过滤。顶栏入口按权限隐藏：新增 `applyPermissionUI()`，「看板管理」（require_admin）与「更多」里的「恢复」「导入」（require_editor）无权限即不显示 | `src/app/app.py`、`src/static/index.html`、`ops/test_board_perm_matrix.py`、`ops/ui_check_perm_entries.py` | `HANDOFF.md §七 #21` |
| #22 | 2026-11-02 | **主设计师** | 流程建设 | **立规 §3.3「测试夹具与基线纪律」**：一天内因临时数据污染导致测试假性失败三次（`__ui_`/`__pv_` 夹具没清干净 → `ui_check_tree.py` 的「仍 36 人」断言失败 → 误以为代码坏了）。三条纪律（夹具 `try/finally` 自清理 / 断言禁用绝对基线数字改相对基线 / 一次性实测数据测完立刻删）+ stash 诊断法；并把 `ui_check_tree.py` 的 `36` 改为实测基线 | `HANDOFF.md`、`ops/ui_check_tree.py` | `HANDOFF.md §七 #22` |
| #23 | 2026-11-02 | **UI设计师** | 界面调整 | 筛选明细（#filterHint）**独占一行**（原被 260px 限宽截断）+ 有选中项时**隐藏默认提示词**（:has() 检测 chip）；连带补齐需求5 遗漏的**工具栏宽度锁定**（.toolbar-left 843px / .toolbar 1172px） | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #23` |
| #24 | 2026-11-02 | **UI设计师** | 界面调整 | 已选项改为**计数徽标**（「已选 3」）—— 框内不再显示已选项文本，展示合并到**树节点勾选态**与**下方筛选明细行**；实测宽度恒定（field 85px / 徽标 49px） | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #24` |
| #25 | 2026-11-02 | **主设计师** | 后端 + 功能逻辑 + 流程建设 | **术语纠正（看板 vs 板块）**：顶部「可选板块」带实际渲染的是 `boards` 表（=看板）→ 标题与相关文案全部改为「可选看板」，并统一 `ME.boards`/`curBoard`=看板、`board_columns`/`column_id`=板块的口径；**ACL 层**：看板与板块各加 `owner`+`participants`，仅负责人/参与人可见（与既有权限链取交集，未配置 ACL 的层级不额外收窄），覆盖列表/计数/搜索/部门页/筛选候选全部入口；**数据清理**：新增 `ops/cleanup_empty.py` + 运行时 `cleanup_empty_columns_and_boards()`，无事项的板块删除、空看板一并删除 | `src/app/app.py`、`src/app/init_db.py`、`src/static/index.html`、`ops/cleanup_empty.py`、`ops/test_acl_scope.py`、`ops/test-filter-ui.js`、`ops/ui_check_board_switch.py` | `HANDOFF.md §七 #25` |
| #26 | 2026-11-02 | **UI设计师** | 界面调整 | 搜索框按实测字宽拉宽（167px，placeholder 完整可见）+ 「更多」去掉 ⋯ 前缀 + 备份/恢复/模板/导入/导出 独立成【导入导出】按钮（两菜单互斥）。连带同步工具栏锁定值 843→875 / 1172→1204 | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #26` |
| #27 | 2026-11-02 | **UI设计师** | 界面调整 | 【导入导出】按钮双 emoji（📥📤）改单 emoji **🔄**（菜单内 📥 已被「恢复/导入」占用，🔄 与 5 项全不重复）；实测宽度 99px 排布整齐 | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #27` |
| #28 | 2026-11-02 | **主设计师** | 后端 | **修复小组成员继承父部门看板**（苏春景可见全部 7 个看板的根因）：`_member_authority_nodes()` 把小组节点**向上提升**到部门祖先 → `_dept_stage_boards()` 再把 scope 里的 id 一律当部门查归属看板 → 费用组/税务组成员被当成核算部成员。修复：新增 `_member_appointed_nodes()`（原始任命节点）+ 第一层改用 `_node_bound_boards()` 按节点类型派生 + `_group_boards()` 不再沿父链收集。修复后苏春景/谭亚利 → 0 个看板，王伟娜/余河不受影响 | `src/app/app.py`、`ops/test_dept_group_scope.py`、`ops/test-board-perm.js`、`ops/ui_check_perm_entries.py` | `HANDOFF.md §七 #28` |
| #29 | 2026-11-02 | **主设计师** | 界面调整 + 文档 | **平台改名**：「财务工作事项平台」→「**财务综合事务平台**」，并加英文首字母缩写 **FISP**（*Financial Integrated Service Platform*）。中文名后挂 `.abbr` 徽标（小号浅色 inline-block，同行不折行）；登录页补英文全称行；旧名称全站清零 | `src/static/index.html`、`src/static/login.html`、`src/app/app.py`、`ops/ui_check_brand.py`、`docs/调试指南.md`、`docs/UI问题排查清单.md`、`docs/交接记录文档管理方案.md`、`工作转移手册.md` | `HANDOFF.md §七 #29` |
| #30 | 2026-11-02 | **主设计师** | 后端 + 界面调整 + 文档 | **权限来源收敛**（用户拍板）：①**看板负责人 = 管理权**（可改看板基本信息），**不再收窄可见性**；②**谁能看见看板统一由【架构管理】的看板绑定决定**；③**参与人机制整体下线**；④**板块负责人移入【板块编辑】**配置；⑤负责人选择改为**树状图单选**（复用筛选栏「👤 人员」的架构树），未开通账号的人置灰不可选 | `src/app/app.py`、`src/static/index.html`、`ops/test_owner_scope.py`、`ops/test_acl_scope.py`、`ops/ui_check_owner.py`、`docs/调试指南.md` | `HANDOFF.md §七 #30` |
| #31 | 2026-11-03 | **主设计师** | 后端 + 流程建设 | **分级权限模型**（架构 > 看板 > 板块 > 事项）：新增 `src/app/perm.py` 权限内核（角色等级序 + 继承 + 资源链 + 统一错误体）；四层资源统一记录 `owner` + 参与人集合；16 个写接口接入分级校验；写接口粗闸门 `require_editor` → `require_writer`；管理员超脱但仅超管可配置管理员权限 | `src/app/perm.py`（新增）、`src/app/app.py`、`src/app/init_db.py`、`ops/test_perm_matrix.py`（新增）、`ops/test_owner_scope.py`、`ops/test_perm_scope.py`、`ops/test_copy_week.py`、`docs/调试指南.md` | `HANDOFF.md §七 #31` |
| #32 | 2026-11-03 | **主设计师** | 前端 + 后端 | **菜单顺序与权限动态渲染**：【架构管理】入口移到【架构部门】带之后、【看板管理】入口移到【可选看板】带之后；两个管理页面按当前成员权限**动态渲染可配置范围**（入口按权限隐藏、条目按权限置灰、按钮按权限不渲染）；后端 `/api/me`、`/api/boards`、`/api/org/tree` 暴露能力位，前端只消费不推断 | `src/app/app.py`、`src/static/index.html`、`ops/test_perm_backend.py`（新增）、`ops/ui_check_perm_render.py`（新增）、`ops/test-board-perm.js`、`ops/ui_check_filter.py`、`ops/ui_check_perm_entries.py`、`docs/调试指南.md` | `HANDOFF.md §七 #32` |
| #33 | 2026-11-03 | **UI设计师** | 界面调整 | 两个管理入口**并入所属带的标题行右侧**（架构管理→架构部门带 / 看板管理→可选看板带），导航区四带收为两带、topbar 559→416px；按钮文字**去掉「打开」**。uid=197609(admin) gid=197121 groups=197121 保持不变 → 权限逻辑零改动 | `src/static/index.html`、`ops/ui_check_entry_pos.py`、`HANDOFF.md` | `HANDOFF.md §七 #33` |
| #34 | 2026-11-03 | **UI设计师** | 界面调整 | 看板管理弹窗**左列 340→410px**（名称不再两行、徽标不竖排、meta 落一行）+ 去列表身份徽标 + 筛选框 placeholder 清空 + 去「统计概览」标题 + 去 🏠 emoji + **双击可选看板取消选择**（含顺带修掉 reload 的过期响应竞态） | `src/static/index.html`、`ops/ui_check_ui_slim.py`、`HANDOFF.md` | `HANDOFF.md §七 #34` |
| #35 | 2026-11-03 | **UI设计师** | 界面调整 | **归属年份筛选**从顶栏移到【可选看板】带标题行；**导入导出**从顶栏移到下方工具栏右侧（与展开/折叠板块同组）。纯 DOM 移动，id 全保留 → 权限与年份逻辑零改动；工具栏右栏锁宽按自然宽度重算 287→400px | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #35` |
| #36 | 2026-11-03 | **UI设计师** | 界面调整 | 【管理公告】按钮移到公告栏**右上角**（伪元素标题改为真实 DOM 标题行）；三个统计方块移到**公告栏下方**（公告栏撑满右半剩余高度，宽度天然不超出）；「成员与账号管理」改名**账号管理**，与【操作日志】一起收进【更多】菜单（T-007 自然闭环） | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #36` |
| #37 | 2026-11-03 | **UI设计师** | 界面调整 | 主页按钮**靠右**（距块右缘 146→16px） + 统计卡底边与「可选看板」底边**对齐**（差 34→0px） + 公告标题字体与架构部门**一致**（13px/700） + 搜索栏**加宽**且导入导出右侧**无空白**（72→1px） | `src/static/index.html`、`ops/ui_check_layout_align.py`、`HANDOFF.md` | `HANDOFF.md §七 #37` |
| #38 | 2026-11-03 | **UI设计师** | 界面调整 | **对齐基准修正**：统计卡底由对齐「可选看板带底」改为对齐左侧**白底卡片底**（margin 抵消法 → grid stretch **天然对齐**，差值 0px）；顶部区紧凑化（`.topbar-main` 空行 gap −20px / navgroup padding-bottom −5px / wrap padding-top −4px，topbar 329→304px，统计卡下方空隙 50→12px） | `src/static/index.html`、`ops/ui_check_layout_align.py`、`HANDOFF.md` | `HANDOFF.md §七 #38` |
| #39 | 2026-11-03 | **UI设计师** | 界面调整 | 删除两个管理入口旁的**权限范围说明文字**（架构负责人 · 可配置 N 个节点… / 可配置 N 个看板）——由「仅管理员隐藏」改为**所有角色一律不显示**（代码层面移除渲染入口 + 清掉无引用 CSS）；实测管理员与架构负责人两种视角均无说明，权限逻辑不受影响 | `src/static/index.html`、`ops/ui_check_entry_pos.py`、`HANDOFF.md` | `HANDOFF.md §七 #39` |
| #40 | 2026-11-03 | **UI设计师** | 界面调整 | 看板管理：列表**恢复滚动**（`setBcListScroll` 的 `overflow:hidden`→`auto`，恰好 7 个看板时中招） + 去中心节点「（全部看板 · 对全员展示）」附注 + 归属部门筛选**按权限过滤** + **新增负责人筛选**（管理员走树弹窗选人／受限用户降级为 owner 账号下拉，因 `/api/team` 对非管理员清空 account） | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #40` |
| #41 | 2026-11-03 | **UI设计师** | 界面调整 | 看板列表：数量由「事项数」改为**板块数**（实测与数据库真值 36/32/32/33/31/33/30 完全一致；⚠️ `col_years.length` 不可用 —— 年份去重，差 36 倍）+ 去 **WS 编码** + 去 **「编辑 ›」**（点击卡片本身即进配置，功能不丢） | `src/static/index.html`、`HANDOFF.md` | `HANDOFF.md §七 #41` |

> 「归档状态」列两种取值：
> **待归档（P2）** —— 正文仍在 `HANDOFF.md` §七，归档执行后本文件对应的 `records/R00NN-*.md` 才会生成；
> **正文在 `HANDOFF.md` §七 #N** —— 近期记录，尚未归档，直接 Read `HANDOFF.md` 定位。

---

## 三、归档批次登记

| 批次 | 归档日期 | 执行人 | 移出的序号区间 | 移出条数 | 归档后主文档保留 |
|---|---|---|---|---|---|
| 第 1 批 | 2026-11-02 | **交接管家** | #1 – #17 | 17 | — |
| 第 2 批 | 2026-11-03 | **交接管家** | #18 – #40 | 23 | 最近 3 条（#41–#43） |

> **每批归档后必须回填本表**：批次号、日期、执行人、移出区间、归档后主文档保留条数。
> **移出后 §六 仍保留指针行**（序号 + 摘要 + `→ docs/handoff/records/R00NN-*.md`），
> 保证在 `HANDOFF.md` 内也能直接跳到归档正文。

---

## 四、归档执行后的校验清单（管家必做）

```
□ 本表行数 = 全量记录数（#1 ~ #N，无跳号、无重号）
□ 每行「正文路径」列的文件真实存在（不许指空）
□ docs/handoff/records/ 下文件数 = 本表标记为「已归档」的条数
□ HANDOFF.md §七 条数 = 保留条数（阈值 3）
□ HANDOFF.md §六 行数 ≤ 40
□ 归档正文是原文搬运（未润色、未重写）
□ 归档批次已回填本表
```

> 归档是本项目**最典型的长距离编辑**。本项目历史上出现过"并行 Edit 同一文件 5 次、
> 每次都返回成功、实际 0 改动"的静默失败（见 `工作转移手册.md` §2.3）。
> **归档后回读，是防止历史被抹掉的唯一手段。**
| #42 | 2026-11-02 | **UI设计师** | 界面调整 | 登录页图标 📊 emoji → **FISP 字母标**（白字+品牌蓝底+700字重）；字体整体调商务（标题 600 字重+字距 / 英文行全大写+1.1px 字距 / 控件 font-family:inherit）；顺带移除标题旁重复的 FISP 徽标（原 #28，与主设计师 #28 撞号 → 2026-11-03 交接管家改为 #42） | `src/static/login.html`、`HANDOFF.md` | `HANDOFF.md §七 #42` |
| #43 | 2026-11-03 | **交接管家** | 流程建设 | **必读区新增铁律③「提交 git 必有记录」**（+ §0.2.2 四问自检 / 禁止整篇重写与覆盖 / 附录A⑦ / 摘要 A-16）；**修复存量损伤**（§六 #21 整行重复、#28 撞号→改 #42、§七 正文乱序重排、13 行缺「正文路径」列、全量索引断链补齐 21 行、元信息块过期）；**归档第 2 批**（#18–#40 → 归档区，主文档 3797 → 1480 行） | `HANDOFF.md`、`docs/handoff/INDEX.md`、`docs/handoff/records/` | 正文在 `HANDOFF.md` §七 #43 | 正文在 `HANDOFF.md` §七 #43 |
