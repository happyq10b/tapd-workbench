// 看板权限 · 归属部门联动 · 选中态同步 · 默认全选 专项回归测试
// 覆盖：
//   1) 选中态同步：架构管理树 / 看板管理列表的底色高亮与状态变量一致
//   2) 移除「职能说明」：表单、渲染、提交、后端模型与数据字段全部清理
//   3) 归属部门联动：看板管理的归属部门取自架构管理层级；中心=全部板块；
//      成员按归属部门过滤看板，再按工作组↔板块绑定关系收窄
//   4) 默认不选中：进入看板管理时清空选中状态；全选/取消全选合并为单个切换按钮
//   5) 删除确认：单条一次确认、批量两次确认；删除后刷新列表并清空选择
//   6) 架构管理选中态：无残留高亮 + 重复点击同一节点取消选中
// 运行：node ops/test-board-perm.js
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'app.py'), 'utf8');
const initDbSrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'init_db.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}
function eq(a, b, msg) { ok(a === b, msg + `  (实际=${JSON.stringify(a)} 期望=${JSON.stringify(b)})`); }

// ============================================================
// 用例 1：选中态同步
// ============================================================
console.log('\n【用例1】选中态与底色高亮同步');
ok(/function paintOrgSelection\(\)/.test(htmlSrc), '存在统一的选中态刷新函数 paintOrgSelection');
ok(/classList\.toggle\('sel', *Number\(el\.dataset\.orgId\)===ORG_SELECTED\)/.test(htmlSrc),
  '底色高亮由 ORG_SELECTED 单一真相驱动（data-org-id 匹配）');
ok(/data-org-id="\$\{n\.id\}"/.test(htmlSrc), '架构管理树行带 data-org-id，便于定点刷新高亮');
// 场景：初始化 / 点击切换 / 列表刷新 / 重新加载
ok(/function selectOrgNode\(nid\)\{[\s\S]*?paintOrgSelection\(\);/.test(htmlSrc),
  '场景「点击切换」：选中节点后刷新底色');
ok(/function editWg\(gid\)\{[\s\S]*?paintOrgSelection\(\);/.test(htmlSrc),
  '场景「点击编辑」：进入编辑态后刷新底色');
ok(/function renderWgList\(\)\{[\s\S]*?paintOrgSelection\(\);/.test(htmlSrc) ||
   /box\.innerHTML=ORG_TREE[\s\S]*?paintOrgSelection\(\);/.test(htmlSrc),
  '场景「列表刷新/重新加载」：重绘树后刷新底色');
ok(!/background:\$\{sel\?'#f0f7ff'/.test(htmlSrc),
  '不再用行内 style 写死选中底色（避免与 CSS .sel 规则互相覆盖）');
ok(/\.org-node-row\.sel\{background:#f0f7ff!important/.test(htmlSrc),
  'CSS 中 .sel 规则统一控制选中底色');
ok(/\.org-node-row\.root\{background:#fafafa\}/.test(htmlSrc),
  '顶层节点底色改由 .root 类控制（与 .sel 优先级不冲突）');
// 看板管理列表：active 态与 BC_SELECTED 一致
ok(/const sel = \(BC_SELECTED && BC_SELECTED\.board_id===b\.board_id\) \? ' active':'';/.test(htmlSrc),
  '看板管理列表的 active 底色由 BC_SELECTED 决定');
ok(/function bcSelect\(bid\)\{[\s\S]*?renderBoardList\(\);[\s\S]*?renderEditArea\(\);/.test(htmlSrc),
  '场景「点击切换」：看板管理选中后同时刷新列表与编辑区');
ok(/function configBoard\(\)\{[\s\S]*?renderBoardList\(\);[\s\S]*?renderEditArea\(\);/.test(htmlSrc),
  '场景「列表刷新」：configBoard 后同步列表高亮');
ok(/function bcChangeBoard\(bid\)\{[\s\S]*?renderBoardList\(\);/.test(htmlSrc),
  '场景「切换编辑对象」：bcChangeBoard 后同步列表高亮');
ok(/function resetBoardConfigForm\(\)\{[\s\S]*?renderBoardList\(\);/.test(htmlSrc),
  '场景「重新加载/取消」：resetBoardConfigForm 后同步列表高亮');
ok(/async function saveBoardAll\(\)\{[\s\S]*?renderBoardList\(\);/.test(htmlSrc),
  '场景「保存后重载」：提交后同步列表高亮');

// ============================================================
// 用例 2：移除「职能说明」
// ============================================================
console.log('\n【用例2】移除架构管理的「职能说明」');
ok(!/职能说明/.test(htmlSrc), '前端不再出现「职能说明」文案');
ok(!/id="g_new_desc"/.test(htmlSrc), '删除职能说明输入框 g_new_desc');
ok(!/g_new_desc/.test(htmlSrc), '删除所有 g_new_desc 引用（不留死代码）');
ok(!/const desc=document\.getElementById\('g_new_desc'\)/.test(htmlSrc), '提交逻辑不再读取职能说明');
ok(!/description:desc/.test(htmlSrc), '提交体不再携带 description');
ok(!/class OrgNodeReq\(BaseModel\):[\s\S]*?description: str = ''/.test(pySrc),
  '后端 OrgNodeReq 移除 description 字段');
ok(!/INSERT INTO org_nodes \(name, node_type, parent_id, function, description\)/.test(pySrc),
  '后端建节点不再写入 description');
ok(!/UPDATE org_nodes SET name=\?, node_type=\?, parent_id=\?, function=\?, description=\?/.test(pySrc),
  '后端改节点不再写入 description');
ok(!/SELECT id, name, node_type, parent_id, wg_id, is_anchor, function, description'\s*\n?\s*' FROM org_nodes/.test(pySrc),
  '组织架构树接口不再返回 description');
ok(!/CREATE TABLE IF NOT EXISTS org_nodes \([\s\S]*?description TEXT/.test(initDbSrc),
  'org_nodes 建表语句不再定义 description 列');
ok(!/CREATE TABLE IF NOT EXISTS workgroups \([\s\S]*?description TEXT/.test(initDbSrc),
  'workgroups 建表语句不再定义 description 列');
ok(/def _drop_description_columns\(conn\)/.test(initDbSrc) &&
   /ALTER TABLE \{table\} DROP COLUMN description/.test(initDbSrc),
  '存量库的 description 遗留列由迁移清理（DROP COLUMN）');
ok(!/description: str = ''/.test(pySrc) || !/class WgNodeReq[\s\S]*?description/.test(pySrc),
  '旧版 WgNodeReq 也不再有 description 字段');
ok(!/req\.description/.test(pySrc), '后端不再读写任何工作组 description');
ok(!/w\.description/.test(htmlSrc), '前端不再渲染工作组 description');
ok(!/description/.test(htmlSrc.split('var WG_ALL=[]')[1].split('\n')[0]),
  'WG_ALL 数据结构注释已去掉 description');

// ============================================================
// 用例 3：归属部门联动 + 权限过滤
// ============================================================
console.log('\n【用例3】归属部门联动【架构管理】的部门层级');
ok(/def _dept_nodes\(\)/.test(pySrc), '后端提供架构部门层级节点读取 _dept_nodes');
ok(/node_type IN \('center','dept'\)/.test(pySrc), '部门层级 = 中心(center) + 部门(dept)');
ok(/def _dept_options\(\)/.test(pySrc), '提供归属部门下拉选项 _dept_options');
ok(/return \{'boards': out, 'depts': _dept_options\(\)\}/.test(pySrc),
  '/api/boards 同时返回看板与可选归属部门（前端下拉的数据源）');
ok(/def _resolve_dept_node\(dept, dept_node_id=0\)/.test(pySrc), '归属部门可按架构节点 id 解析');
ok(/dept_node_id INTEGER NOT NULL DEFAULT 0/.test(initDbSrc), 'board_config 新增 dept_node_id 关联架构节点');
ok(/dept_node_id = COALESCE\(\(/.test(initDbSrc), '迁移：按部门名回填 dept_node_id');
ok(/def _dept_owned_boards\(\)/.test(pySrc), '按归属部门归集板块 _dept_owned_boards');
ok(/def _member_dept_scope\(username\)/.test(pySrc), '计算成员归属部门范围 _member_dept_scope');
ok(/def _dept_stage_boards\(username\)/.test(pySrc), '归属部门层过滤 _dept_stage_boards（第一层）');
ok(/def _group_boards\(username: str\)/.test(pySrc), '工作组↔板块绑定过滤 _group_boards（第二层）');
ok(/dept_boards = _dept_stage_boards\(username\)/.test(pySrc),
  'user_allowed 中先按归属部门过滤、再由账号/工作组权限收窄');
ok(/def _arch_scope_boards\(username: str, dept_boards: set\)/.test(pySrc),
  '架构授权集汇总三层（归属部门 + 负责范围 + 工作组绑定）');
ok(/boards = _arch_scope_boards\(username, dept_boards\)/.test(pySrc),
  'user_allowed 用架构授权集作为可见范围基线');
ok(/boards &= set\(x for x in raw_b\.split\(','\) if x\)/.test(pySrc),
  '归属部门层与账号权限取交集（账号白名单只能收窄，不能越权授予）');
ok(/if is_admin\(username\) and not arch_only:\s*\n\s*return None, None/.test(pySrc),
  'admin 超级管理员豁免架构权限过滤（arch_only=False 默认路径不变；#77 起评论 @ 候选池走 arch_only=True 只算架构内路径）');
ok(/def _node_bound_boards\(node: dict/.test(pySrc),
  '节点绑定的看板按节点类型派生（中心=全部 / 部门=归属看板 / 小组=手工绑定）');
ok(/return merged if bound else None/.test(pySrc),
  '工作组绑定层只取显式白名单（不再把部门自有看板并入，否则永远收窄不了）');
// 2026-11-05 新规则：中心归属看板不再全员可见（走任命链），_center_node_ids 已随之移除
ok(/node_type'\)\s*==\s*'center'|node_type"\)\s*==\s*'center'|node_type==='center'/.test(pySrc),
  '中心级节点按 node_type 识别（挂靠中心 = 管理层全范围）');
ok(!/nid in centers/.test(pySrc) && /if not owner\.get\(bid, 0\)/.test(pySrc),
  '公共看板 = 未归属；中心归属看板走任命链（2026-11-05 新规则）');
// ⚠️ 2026-11-02 修复：中心判定改用「原始任命节点的类型」而非「向上提升后的 scope」
//    （小组成员不应因父部门是中心就获得管理层全范围）。
ok(/get\('node_type'\)\s*==\s*'center'/.test(pySrc),
   '挂靠中心的成员按管理层全范围处理（按原始任命节点类型判定）');ok(/_member_appointed_nodes\(username\)/.test(pySrc),
   '权限判定使用「原始任命节点」（小组不被提升到父部门）');
ok(/return merged if bound else None/.test(pySrc),
   '工作组绑定层仍只取显式白名单（收窄语义不变）');
// （2026-11-05 旧断言移除：中心归属的板块已不再对全员展示，走任命链）
ok(/def _dept_order\(\)/.test(pySrc), '目录树部门顺序随架构层级动态变化');
// ⚠️ 2026-11-02：/api/me 的部门清单改为**按权限过滤** —— 只含有可见看板的部门。
//    原为 `'depts': _dept_order()`（架构里的全部部门）→ 普通用户目录树会列出
//    自己无权访问的部门（既暴露组织信息，又让用户以为那里有事却点进去是空的）。
ok(/'depts': dept_list/.test(pySrc), '/api/me 的部门清单按权限过滤（dept_list）');
ok(/seen = \{item\.get\('dept'\) for item in boards_out if item\.get\('dept'\)\}/.test(pySrc),
   '部门清单取自「有可见看板的部门」集合');
ok(/if boards is None:\s*\n\s*dept_list = _dept_order\(\)/.test(pySrc),
   '管理员（boards=None=全部）仍看到全部部门');
ok(/if dept not in _dept_names\(\)/.test(pySrc), '部门校验改为按架构层级');
ok(/ALLOWED_DEPTS/.test(pySrc) === false || /DEPT_ORDER = \[/.test(pySrc),
  '固定部门枚举退化为历史回退清单');
// 前端联动
ok(/var BC_DEPTS=\[\];/.test(htmlSrc), '前端归属部门选项改为动态加载');
ok(/BC_DEPTS=\(res\.depts\|\|\[\]\)\.slice\(\);/.test(htmlSrc), '看板管理从接口拉取归属部门选项');
ok(/function bcDeptLabel\(d\)/.test(htmlSrc), '归属部门下拉标注中心级（全部板块 · 对全员展示）');
ok(/function bcSetDept\(name\)/.test(htmlSrc), '切换归属部门时同步 dept_node_id');
ok(/function bcDeptHint\(name\)/.test(htmlSrc), '归属部门提供可见范围说明');
ok(/dept_node_id:BC_FORM\.dept_node_id\|\|bcDeptNodeId\(BC_FORM\.dept\)/.test(htmlSrc),
  '提交时携带 dept_node_id');
ok(/function nodeBoardScope\(node\)/.test(htmlSrc), '架构管理按节点类型派生板块范围');
ok(/node\.node_type==='dept'\)[\s\S]*?node\.owned_boards/.test(htmlSrc),
  '部门级节点的板块由「归属部门」派生（owned_boards）');
ok(/owned_boards/.test(pySrc) || /'owned_boards': sorted\(owned\.get/.test(pySrc),
  '组织架构树接口返回节点拥有的板块 owned_boards');
// ⚠️ 2026-11-04：批量应用功能已下线（用户：「应用到已选 N 个看板」这个功能没什么用，去掉）
ok(!/@app\.post\('\/api\/board-config\/bulk'\)/.test(pySrc), '批量配置接口已下线');

// ============================================================
// 用例 4：默认不选中（全选 / 取消全选合并为单个切换按钮）
// ============================================================
console.log('\n【用例4】进入看板管理默认不选中，全选按钮可切换');
ok(/var BC_SEL=new Set\(\);/.test(htmlSrc), '维护看板多选集合 BC_SEL');
ok(/function bcVisibleBoards\(\)/.test(htmlSrc), '可见板块集合计算 bcVisibleBoards');
ok(/async function openBoardConfigModal\(\)\{[\s\S]*?BC_SEL=new Set\(\);/.test(htmlSrc),
  '进入看板管理时默认【不选中】（清空选中状态）');
ok(/function bcFilterChange\(dim,val\)\{[\s\S]*?BC_SEL=new Set\(\);/.test(htmlSrc),
  '筛选变化后清空勾选（保持默认不选中语义）');
ok(!/BC_SEL=new Set\(bcVisibleBoards\(\)/.test(htmlSrc), '不再有「默认全选可见板块」的逻辑');
ok(/function bcTogglePickAll\(\)/.test(htmlSrc), '全选与取消全选合并为单个切换函数 bcTogglePickAll');
ok(!/function bcPickAll\(/.test(htmlSrc), '旧的 bcPickAll(checked) 双按钮函数已移除');
ok(/id="bcPickAllBtn"/.test(htmlSrc) && /onclick="bcTogglePickAll\(\)"/.test(htmlSrc),
  '界面上只有一个全选切换按钮（不再并排两个按钮）');
ok(!/onclick="bcPickAll\(true\)"/.test(htmlSrc) && !/onclick="bcPickAll\(false\)"/.test(htmlSrc),
  '界面不再同时显示「全选」和「取消全选」两个按钮');
ok(/pb\.textContent=allOn\?'取消全选':'全选'/.test(htmlSrc), '按钮文案随当前状态切换');
ok(/id="bcPickCount"/.test(htmlSrc), '展示已勾选板块数量');
ok(/class="bc-pick"/.test(htmlSrc), '列表项带勾选框');
ok(/function bcPaintPick\(\)/.test(htmlSrc), '勾选状态回写 DOM（选中态与勾选态分离）');

// ============================================================
// 用例 5：删除确认（单条两次 / 批量两次）+ 删除后刷新清空
// ⚠️ 2026-11-04：删除语义从「删看板配置」改为「**删看板本身**」→ 不可逆 → 单条也升为两次确认
// ============================================================
console.log('\n【用例5】删除确认与删除后刷新');
ok(/function bcDeleteOne\(bid\)/.test(htmlSrc), '提供单条删除 bcDeleteOne');
ok(!/function deleteBoardConfig\(/.test(htmlSrc), '旧的 deleteBoardConfig 已移除（统一走 bcDeleteOne）');
ok(/function bcDeleteSelected\(\)/.test(htmlSrc), '提供批量删除 bcDeleteSelected');
{
  // 单条删除：两次确认（删看板本身不可逆）
  const m1 = htmlSrc.match(/async function bcDeleteOne\(bid\)\{[\s\S]*?\n\}/);
  ok(!!m1, '单条删除函数体可解析');
  const body1 = m1 ? m1[0] : '';
  const confirms1 = (body1.match(/bcConfirm\(/g) || []).length;
  ok(confirms1 === 2, '单条删除弹两次确认（实际 ' + confirms1 + ' 次）');
  ok(/if\(!bcConfirm\([\s\S]*?\)\)return;[\s\S]*?if\(!bcConfirm\([\s\S]*?\)\)return;/.test(body1),
    '单条删除两次确认逐级拦截，任一次取消都不执行删除');
}
{
  // 批量删除：两次确认，且第一次取消后不得继续到第二次
  const m = htmlSrc.match(/async function bcDeleteSelected\(\)\{[\s\S]*?\n\}/);
  ok(!!m, '批量删除函数体可解析');
  const body = m ? m[0] : '';
  const confirms = (body.match(/bcConfirm\(/g) || []).length;
  ok(confirms === 2, '批量删除弹两次确认（实际 ' + confirms + ' 次）');
  ok(/if\(!bcConfirm\([\s\S]*?\)\)return;[\s\S]*?if\(!bcConfirm\([\s\S]*?\)\)return;/.test(body),
    '两次确认逐级拦截，任一次取消/关闭都不执行删除');
}
ok(/function bcAfterDelete\(deletedIds\)/.test(htmlSrc), '删除后统一走 bcAfterDelete');
ok(/async function bcAfterDelete\(deletedIds\)\{[\s\S]*?BC_SEL=new Set\(\);/.test(htmlSrc),
  '删除后清空选择状态');
ok(/async function bcAfterDelete\(deletedIds\)\{[\s\S]*?await loadBoardConfig\(\);/.test(htmlSrc),
  '删除后刷新看板列表');
ok(/async function bcAfterDelete\(deletedIds\)\{[\s\S]*?renderBoardList\(\);[\s\S]*?renderEditArea\(\);/.test(htmlSrc),
  '删除后重绘列表与编辑区');
ok(!/class="bc-item-del"/.test(htmlSrc), '列表行内不再有删除按钮（已移入编辑区）');
// 删除按钮受**后端能力位**控制（2026-11-03）：can_delete 为真才显示。
// ⚠️ 2026-11-04 语义变更：删除从「删看板配置」改成「**删看板本身**」，
//    故不再要求 isEdit（未配置的看板同样可删），且按钮文案改为「删除看板」。
ok(/if\(canDelete\)footer\+='<button class="btn-secondary bc-del-single"/.test(htmlSrc),
  '编辑区页脚提供单个看板的删除按钮（按 can_delete 权限渲染）');
ok(/title="删除该看板本身（连同其下的板块与事项，不可撤销）">删除看板<\/button>/.test(htmlSrc),
  '单条删除按钮语义为「删除看板本身」');
ok(/const canEdit=!!b\.can_edit, canDelete=!!b\.can_delete, canAssign=!!b\.can_assign_owner;/.test(htmlSrc),
  '编辑区按后端能力位（can_edit/can_delete/can_assign_owner）控制可配置范围');
// ⚠️ 2026-11-04：「保存负责人」+「保存配置」合并为单一【保存看板】按钮
ok(/if\(canEdit\|\|canAssign\)footer\+='<button class="btn-primary" onclick="saveBoardAll\(\)"/.test(htmlSrc),
  '「保存看板」按钮按 can_edit/can_assign_owner 任一能力位渲染');
ok(!/onclick="saveBoardAcl\(\)"/.test(htmlSrc) && !/onclick="submitBoardConfigForm\(\)"/.test(htmlSrc),
  '旧的「保存负责人」「保存配置」两个按钮已合并为【保存看板】');
ok(/async function saveBoardAll\(\)/.test(htmlSrc), '提供统一保存函数 saveBoardAll');
ok(/if\(canAssign\)\{[\s\S]*?\/acl/.test(htmlSrc), 'saveBoardAll 按 can_assign_owner 保存负责人');
ok(/if\(canEdit\)\{[\s\S]*?\/board-config/.test(htmlSrc), 'saveBoardAll 按 can_edit 保存基本信息');
ok(/id="bcDelBtn"/.test(htmlSrc) && /onclick="bcDeleteSelected\(\)"/.test(htmlSrc),
  '批量删除按钮与全选按钮同排');
// 删除按钮不带个数：个数统一由右侧「已选 N 个」显示，避免同一信息重复两处
ok(/id="bcDelBtn"[^>]*>删除所选</.test(htmlSrc), '删除按钮初始文案为「删除所选」（不带个数）');
ok(/db\.textContent='删除所选';/.test(htmlSrc), '删除按钮文案固定，不随勾选数变化');
ok(!/删除所选 '?\+?BC_SEL\.size/.test(htmlSrc), '删除按钮不再拼接选中个数');
ok(/已选 <b id="bcPickCount">0<\/b> 个/.test(htmlSrc), '选中个数只在工具条右侧「已选 N 个」处显示');
ok(/\.bc-opbar\{display:flex;flex-direction:row;align-items:center;gap:8px;flex-wrap:nowrap/.test(htmlSrc),
  '操作条强制横向一行（flex-direction:row，避免竖排）');
ok(/\.bc-opbar-btns\{display:flex;align-items:center;gap:8px;flex-shrink:0\}/.test(htmlSrc),
  '全选与删除按钮同组（不换行）');
ok(/<div class="bc-opbar-btns">/.test(htmlSrc), '工具条按钮包裹在同一按钮组内');
ok(/\.bc-opbar-count\{[^}]*margin-left:auto/.test(htmlSrc), '勾选计数靠右对齐');
ok(/\.bc-del-btn\{/.test(htmlSrc), '批量删除按钮有独立统一样式');
ok(/db\.disabled=BC_SEL\.size===0/.test(htmlSrc), '未勾选时批量删除按钮禁用');
// ⚠️ 2026-11-04：批量删除从「删配置」改成「删看板本身」，接口换为 /api/boards/bulk-delete
ok(/@app\.post\('\/api\/boards\/bulk-delete'\)/.test(pySrc), '提供批量删除看板接口');
ok(/class BoardBulkDeleteReq\(BaseModel\)/.test(pySrc), '批量删除看板请求模型定义');
ok(/DELETE FROM boards WHERE board_id=\?/.test(pySrc), '批量删除会真正删掉看板本体');
ok(!/@app\.post\('\/api\/board-config\/bulk-delete'\)/.test(pySrc),
  '旧的「批量删除看板配置」接口已下线');
ok(!/@app\.post\('\/api\/board-config\/bulk'\)/.test(pySrc),
  '旧的「批量应用看板配置」接口已下线（应用到已选 N 个看板功能移除）');
ok(!/function applyBulkConfig\(\)/.test(htmlSrc), '前端不再有 applyBulkConfig（应用到已选 N 个看板已移除）');
ok(!/应用到已选/.test(htmlSrc), '界面上不再出现「应用到已选 N 个看板」按钮');
// ⚠️ 2026-11-04：单条删除语义改为「删看板本身」→ 两次确认（高危不可逆）
ok(/function bcDeleteOne\(bid\)\{[\s\S]*?if\(!bcConfirm\([\s\S]*?\)\)return;[\s\S]*?if\(!bcConfirm\([\s\S]*?\)\)return;/.test(htmlSrc),
  '单条删除弹两次确认（删看板本体不可逆）');

// ============================================================
// 用例 6：架构管理选中态（无残留 + 重复点击取消）
// ============================================================
console.log('\n【用例6】架构管理选中态与重复点击切换');
ok(/function clearOrgSelection\(\)/.test(htmlSrc), '提供取消选中逻辑 clearOrgSelection');
ok(/function selectOrgNode\(nid\)\{\s*if\(ORG_SELECTED===nid\)\{clearOrgSelection\(\);return;\}/.test(htmlSrc),
  '重复点击同一节点即取消选中（切换）');
ok(/function renderOrgIdle\(\)/.test(htmlSrc), '未选中时右侧面板回到初始态');
ok(/async function openWgModal\(\)\{[\s\S]*?ORG_SELECTED=0;/.test(htmlSrc),
  '打开架构管理弹窗时清空选中（默认未选中）');
ok(!/class="org-node-row\$\{sel\?' sel':''\}/.test(htmlSrc),
  '树行不再内联生成 .sel（消除双来源）');
ok(/function renderWgList\(\)\{[\s\S]*?paintOrgSelection\(\);/.test(htmlSrc),
  'renderWgList 渲染后统一回写选中态');
ok(/function paintOrgSelection\(\)\{[\s\S]*?classList\.toggle\('sel'/.test(htmlSrc),
  '高亮由 paintOrgSelection 单一来源回写');
ok(/function resetWgForm\(\)\{[\s\S]*?ORG_SELECTED=0;/.test(htmlSrc),
  '重置表单时同步清空选中态');
ok(/function resetWgForm\(\)\{[\s\S]*?renderOrgIdle\(\);/.test(htmlSrc),
  '重置表单时右侧回到未选中面板');

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
