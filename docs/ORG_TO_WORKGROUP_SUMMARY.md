# 「组织」→「工作组」全量重构 · 完成报告

> 项目：`tapd_webapp`（TAPD 看板 Web 应用，FastAPI + SQLite）
> 部署：WSL Ubuntu-24.04 `/root/tapd_webapp`，systemd `tapd-web.service`（端口 8000）
> 状态：**已上线并端到端验证通过**

## 一、需求
将项目内「组织」概念全面重构为「工作组」，并同步修改 SQLite 字段名；历史组织数据无损迁移为工作组。

## 二、改动清单

### 1. 数据库（SQLite）— `app/init_db.py`
- 表 `groups` → `workgroups`（所有列名不变，仅表名）
- `team_members.groups`（分号分隔组织名）列 → `team_members.workgroups`
- `_migrate_schema` 幂等迁移：
  - `groups`→`workgroups`：`CREATE 新表 + INSERT SELECT + DROP 旧表`
  - `team_members.groups`→`workgroups`：`ADD COLUMN` 回填 + `RENAME 旧表 + 重建表 + 回填 + DROP`（SQLite 低版本不支持 DROP COLUMN）
- 部门层级初始化（财务中心 → 5 部门 → 核算部 6 子组）逻辑全部指向 `workgroups`

### 2. 后端 API — `app/app.py`
- 权限模型 `_leader_boards` / `_group_boards` / `user_allowed` 改用 `workgroups` 列
- `get_team`、成员增改 `TeamReq/TeamUpdateReq` 字段 `groups` → `workgroups`
- 架构管理 API 重构为 `GET/POST/PUT/DELETE /api/workgroups`
- **向后兼容**：保留别名 `GET /api/org`、`GET /api/groups`，且响应字段名仍用 `groups`（前端无需二次大改）

### 3. 前端 UI — `static/index.html`（CRLF）
- 文案「组织」→「工作组」
- 变量语义化重命名：`ORG_*`→`WG_*`、`TM_FILTER.org`→`TM_FILTER.workgroup`、`group*/Group*`→`wg*/Wg*`（保留 CSS 类 `.week-group`/`.form-group` 等无关项）
- API 调用 `/api/org`→`/api/workgroups`；成员字段 `m.groups`→`m.workgroups`
- 兼容层保留读取 `groupsRes.groups` / `gd.groups`

## 三、语法校验
- `python -m py_compile app.py init_db.py` → 通过
- 前端内嵌 JS `node --check` → 通过

## 四、部署与验证（WSL）
1. 停服释放 SQLite 锁 → 备份 `app.db`（`app.db.bak.20260821_*`）
2. 同步 E: 源三份文件至 `/root/tapd_webapp`（md5 完全一致）
3. 手动跑 `init_db` 迁移 + `systemctl restart tapd-web`
4. 验证结果：
   - 服务 `active`，启动无 `init_db()` 告警
   - `/api/workgroups`：顶层「财务中心」，12 个工作组，节点含 `children` 树形结构
   - `/api/team`：24 名成员，`workgroups` 字段保留（如「费用组」「成本组」）
   - `/api/org` 兼容别名：同结构返回，`groups` 字段存在
   - 数据**零丢失**（表更名 + 列回填均成功）

## 五、踩坑记录
- WSL 中**含中文的路径存入 shell 变量会被转义损坏**；必须内联中文字面量（如 `/mnt/e/WB缓存/...`）或用 `wslpath`，避免 `set -e`（无匹配的 `ls` glob 会令脚本静默退出）。

## 六、后续修复：tree-pick 弹窗滚轮失效

### 问题
「选择工作组」弹窗（以及架构筛选、角色多选下拉）内部树形/选项列表有滚动条，但滚轮/触摸板无法滚动。

### 根因
`modalScrollGuard` 全局 wheel 监听器仅识别 `.modal-overlay` 弹窗；`.tree-pick` 浮动面板和 `.combo-panel` 不在白名单内，滚轮事件被误判为「弹窗外」而 `preventDefault()`，导致内部滚动失效。

### 修复（`static/index.html`）
```javascript
function modalScrollGuard(e){
  const hasFloat=anyModalOpen()||document.querySelector('.tree-pick,.combo-panel');
  if(!hasFloat)return;
  const container=e.target.closest?e.target.closest('.modal-overlay,.tree-pick,.combo-panel'):null;
  if(!container){e.preventDefault();return;}
  // ...后续可滚动判断保持不变
}
```

### 验证
- `node --check` 通过
- `index.html` 同步至 `/root/tapd_webapp`（md5 一致），`systemctl restart tapd-web` 后服务 `active`

## 七、结论
「组织」概念已全量切换为「工作组」，SQLite 字段名同步更新，历史数据无损迁移，tree-pick 弹窗滚轮问题已修复，生产服务运行正常。
