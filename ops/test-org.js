// 组织架构模块专项回归测试
// 覆盖：
//   1) 数据模型：org_nodes / org_roles / org_appointments 三表结构与约束
//   2) 层级完整性：中心→部门→常规小组；中心/部门可设专项小组；防环；中心唯一
//   3) 角色唯一性：唯一槽位岗位（组长/部门长/中心负责人/总经理）节点内至多一人
//   4) 多重归属：一人多岗、多组织任职；成员任职视图
//   5) 接口：节点 CRUD / 移动 / 任职维护
//   6) 前端：类型徽章、岗位槽位渲染、多归属标记
// 运行：node ops/test-org.js
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'app.py'), 'utf8');
const initDbSrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'init_db.py'), 'utf8');
const blocks = [...htmlSrc.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const main = blocks.join('\n');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}
function eq(a, b, msg) { ok(a === b, msg + `  (实际=${JSON.stringify(a)} 期望=${JSON.stringify(b)})`); }

// ============================================================
// 用例 1：数据模型（表结构 / 字段 / 约束）
// ============================================================
console.log('\n【用例1】数据模型：三表结构与约束');
ok(/CREATE TABLE IF NOT EXISTS org_nodes/.test(initDbSrc), '建表 org_nodes（架构节点）');
ok(/CREATE TABLE IF NOT EXISTS org_roles/.test(initDbSrc), '建表 org_roles（岗位定义）');
ok(/CREATE TABLE IF NOT EXISTS org_appointments/.test(initDbSrc), '建表 org_appointments（任职关系）');

// org_nodes 字段
ok(/node_type\s+TEXT NOT NULL DEFAULT 'group'/.test(initDbSrc), 'org_nodes 有 node_type 字段');
ok(/CHECK \(node_type IN \('center','dept','group','special'\)\)/.test(initDbSrc),
   'node_type 受 CHECK 约束：center/dept/group/special');
ok(/parent_id\s+INTEGER NOT NULL DEFAULT 0/.test(initDbSrc), 'org_nodes 有 parent_id（自引用树）');
ok(/UNIQUE\(parent_id, name\)/.test(initDbSrc), 'org_nodes 同级同名唯一（UNIQUE(parent_id,name)）');
ok(/wg_id\s+INTEGER NOT NULL DEFAULT 0/.test(initDbSrc), 'org_nodes 有 wg_id（关联旧 workgroups 兼容视图）');
ok(/FOREIGN KEY \(node_id\) REFERENCES org_nodes\(id\) ON DELETE CASCADE/.test(initDbSrc),
   'org_appointments 对节点外键 CASCADE 删除');
ok(/FOREIGN KEY \(member_id\) REFERENCES team_members\(id\) ON DELETE CASCADE/.test(initDbSrc),
   'org_appointments 对成员外键 CASCADE 删除');
ok(/UNIQUE\(node_id, member_id, role_key\)/.test(initDbSrc),
   'org_appointments 同节点同成员同岗位唯一（可一人多岗 / 一人多组织）');

// 唯一槽位的 DB 级兜底
ok(/CREATE UNIQUE INDEX IF NOT EXISTS ux_org_unique_slot/.test(initDbSrc),
   '建 partial unique index ux_org_unique_slot（唯一槽位岗位 DB 级兜底）');
ok(/WHERE role_key IN \('center_head','gm','dept_head','group_leader'\)/.test(initDbSrc),
   '唯一槽位覆盖：中心负责人 / 总经理 / 部门长 / 组长');
ok(!/WHERE role_key IN \(\s*SELECT/.test(initDbSrc),
   'partial index 的 WHERE 不用子查询（SQLite 不支持，引用别的表）');

// org_roles 岗位定义
for (const rk of ['center_head', 'gm', 'center_backbone', 'dept_head', 'dept_backbone', 'group_leader', 'member']) {
  ok(new RegExp(`'${rk}'`).test(initDbSrc), `岗位定义含 ${rk}`);
}
ok(/unique_slot\s+INTEGER NOT NULL DEFAULT 0/.test(initDbSrc), 'org_roles 有 unique_slot（节点内唯一 / 可多人）');
ok(/UNIQUE\(node_type, role_key\)/.test(initDbSrc), 'org_roles 同类型岗位键唯一');

// ============================================================
// 用例 2：层级完整性（服务端规则）
// ============================================================
console.log('\n【用例2】层级完整性：类型规则与防环');
ok(/ORG_TYPES = \('center', 'dept', 'group', 'special'\)/.test(pySrc), '服务端定义四种节点类型');
ok(/ORG_PARENT_RULES = \{/.test(pySrc), '服务端定义父节点类型规则表');
ok(/'center':\s*set\(\)/.test(pySrc), '中心无父节点（顶级）');
ok(/'dept':\s*\{'center'\}/.test(pySrc), '部门只能挂在中心下');
ok(/'group':\s*\{'dept'\}/.test(pySrc), '常规小组只能挂在部门下');
ok(/'special':\s*\{'center', 'dept'\}/.test(pySrc), '专项小组可挂在中心或部门下');
ok(/def _check_parent_ok/.test(pySrc), '存在层级校验函数 _check_parent_ok');
ok(/上级节点不能是自己的下级/.test(pySrc), '层级校验拦截「挂到自己的后代下」（防环）');
ok(/中心节点全局只能有一个/.test(pySrc), '中心节点全局唯一');
ok(/上级节点不能是自身/.test(pySrc), '层级校验拦截「自己是自己的上级」');
// 改类型 / 移动时要检查子节点兼容性
ok(/子节点.*不允许挂在/.test(pySrc), '改类型/移动时校验子节点类型兼容性');
// 前端同步规则
ok(/var ORG_CHILD_RULES=\{/.test(htmlSrc), '前端定义同一套子类型规则');
ok(/center:\['dept','special'\]/.test(htmlSrc), '前端：中心下可建部门 / 专项小组');
ok(/dept:\['group','special'\]/.test(htmlSrc), '前端：部门下可建常规小组 / 专项小组');

// ============================================================
// 用例 3：角色唯一性
// ============================================================
console.log('\n【用例3】角色唯一性与岗位匹配');
ok(/def _check_unique_slot/.test(pySrc), '存在唯一槽位校验函数 _check_unique_slot');
ok(/在一个节点内只能有一人/.test(pySrc), '唯一槽位给出中文错误提示（DB 报错是英文）');
ok(/def _check_role_allowed/.test(pySrc), '存在岗位与节点类型匹配校验');
ok(/不可设置该岗位/.test(pySrc), '岗位不匹配时给出中文提示');
ok(/unique_slot/.test(pySrc), '服务端按 unique_slot 判定唯一 / 多人');
ok(/「唯一」/.test(htmlSrc) || /unique_slot\?'唯一'/.test(htmlSrc) || /unique_slot/.test(htmlSrc),
   '前端标注唯一槽位');

// ============================================================
// 用例 4：多重归属
// ============================================================
console.log('\n【用例4】多重归属：一人多岗 / 一人多组织');
ok(/def _org_sync_legacy/.test(pySrc), '存在新旧模型同步函数 _org_sync_legacy');
ok(/def _org_sync_member_legacy/.test(pySrc), '存在成员侧同步函数（清理旧 workgroups 串）');
ok(/@app\.get\('\/api\/org\/members\/\{member_id\}\/appointments'\)/.test(pySrc),
   '提供成员任职视图接口（横跨哪些节点、什么岗位）');
ok(/other_org_count/.test(pySrc), '树接口返回「另有几个组织任职」标记');
ok(/另有 \$\{a\.other_org_count\} 个组织任职/.test(htmlSrc) || /另有/.test(htmlSrc),
   '前端展示多归属标记');
ok(/is_primary/.test(initDbSrc), '任职关系带 is_primary（主岗标记）');

// ============================================================
// 用例 5：接口设计
// ============================================================
console.log('\n【用例5】接口设计');
const apis = [
  ["@app.get('/api/org/tree')", 'GET /api/org/tree —— 节点树 + 岗位 + 任职'],
  ["@app.post('/api/org/nodes')", 'POST /api/org/nodes —— 新增节点'],
  ["@app.put('/api/org/nodes/{nid}')", 'PUT /api/org/nodes/{id} —— 修改节点'],
  ["@app.delete('/api/org/nodes/{nid}')", 'DELETE /api/org/nodes/{id} —— 删除节点（级联）'],
  ["@app.post('/api/org/nodes/{nid}/move')", 'POST /api/org/nodes/{id}/move —— 移动节点（换上级）'],
  ["@app.post('/api/org/appointments')", 'POST /api/org/appointments —— 新增任职'],
  ["@app.delete('/api/org/appointments/{aid}')", 'DELETE /api/org/appointments/{id} —— 解除任职'],
  ["@app.post('/api/org/appointments/move')", 'POST /api/org/appointments/move —— 调整任职（换节点/换岗位）'],
];
for (const [sig, desc] of apis) {
  ok(pySrc.includes(sig), desc);
}
// 写操作必须管理员
const adminGuards = (pySrc.match(/Depends\(require_admin\)/g) || []).length;
ok(adminGuards >= 8, `写接口全部挂 require_admin（当前 ${adminGuards} 处）`);
// 删除节点要级联
ok(/removed_children/.test(pySrc), '删除节点返回级联清理的子节点数');
ok(/级联清理/.test(pySrc) || /自底向上/.test(pySrc), '删除节点级联清理子节点与任职');
ok(/中心节点不可删除/.test(pySrc), '中心节点禁止删除');
ok(/仍绑定着板块/.test(pySrc), '绑定板块的节点禁止删除（避免成员突然失权）');

// ============================================================
// 用例 6：前端交互
// ============================================================
console.log('\n【用例6】前端：节点类型 / 岗位槽位 / 多归属');
ok(/id="g_new_type"/.test(htmlSrc), '有节点类型下拉');
ok(/id="g_roles_box"/.test(htmlSrc), '有岗位与任职渲染容器');
ok(/function renderOrgRoles/.test(htmlSrc), '提供岗位槽位渲染函数');
ok(/function addOrgAppt/.test(htmlSrc), '提供任命（加人）函数');
ok(/function removeOrgAppt/.test(htmlSrc), '提供免职（移除）函数');
ok(/function selectOrgNode/.test(htmlSrc), '提供节点选中（查看其岗位）函数');
ok(/function fillOrgTypeOptions/.test(htmlSrc), '类型选项按上级过滤');
ok(/function onOrgTypeChange/.test(htmlSrc), '类型变更时重算上级与板块范围');
ok(/class="org-node-row/.test(htmlSrc), '节点行使用 .org-node-row 样式');
ok(/\.org-chip\{/.test(htmlSrc), '任职人员使用 .org-chip 标签');
ok(/ORG_TYPE_STYLE/.test(htmlSrc), '按节点类型区分图标与配色');
// 旧的单 leader 下拉已移除
ok(!/id="g_new_leader"/.test(htmlSrc), '旧的「组长/部门长」单选下拉已移除（改由岗位槽位承载）');
ok(!/function fillLeaderOptions/.test(htmlSrc), '死代码 fillLeaderOptions 已清理');
ok(!/function updateLeaderLabel/.test(htmlSrc), '死代码 updateLeaderLabel 已清理');
ok(!/g_leader_label/.test(htmlSrc), '旧标签 g_leader_label 已清理');

// 元素引用完整性（删了元素必须删引用）
const ids = new Set([...htmlSrc.matchAll(/id="([A-Za-z_][\w-]*)"/g)].map(m => m[1]));
const badRefs = [];
for (const m of htmlSrc.matchAll(/getElementById\('([A-Za-z_][\w-]*)'\)\s*\.\s*(\w+)/g)) {
  if (!ids.has(m[1])) badRefs.push(`${m[1]}.${m[2]}`);
}
ok(badRefs.length === 0, `无失效元素引用${badRefs.length ? '：' + badRefs.join(', ') : ''}`);

// ============================================================
// 用例 7：存量迁移
// ============================================================
console.log('\n【用例7】存量数据迁移（幂等）');
ok(/def _migrate_org/.test(initDbSrc), '存在组织架构迁移函数 _migrate_org');
ok(/_migrate_org\(conn\)/.test(initDbSrc), '迁移在 init_db 中被调用');
ok(/INSERT OR IGNORE INTO org_roles/.test(initDbSrc), '岗位定义用 INSERT OR IGNORE（幂等）');
ok(/INSERT OR IGNORE INTO org_appointments/.test(initDbSrc), '任职关系用 INSERT OR IGNORE（幂等）');
ok(/leader → 唯一槽位岗位/.test(initDbSrc), '旧 leader 迁移为对应岗位任职');
ok(/team_members\.workgroups（分号串）→ 组员任职/.test(initDbSrc), '旧成员分组串迁移为组员任职');
ok(/挂到「常规小组 \/ 专项小组」节点/.test(initDbSrc), '成员归属只挂小组节点（部门靠父链传导）');
// 旧表仍保留（权限逻辑零改动）
ok(/CREATE TABLE IF NOT EXISTS workgroups/.test(initDbSrc), '旧表 workgroups 保留（权限逻辑兼容）');
ok(/def _leader_boards/.test(pySrc), '旧权限函数 _leader_boards 保留');
ok(/def _group_boards/.test(pySrc), '旧权限函数 _group_boards 保留');

// ============================================================
console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
if (fail) process.exit(1);
