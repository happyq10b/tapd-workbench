// ============================================================
// 专项回归测试：成员保存校验修复 / 架构管理优先的权限覆盖 /
//                 树形组件末级人员与人员筛选
// 断言基于前端源码正则 + 后端源码正则 + DOM stub
// ============================================================
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src/static/index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src/app/app.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

// ============================================================
// 用例 1：成员保存「姓名不能为空」校验修复
// ============================================================
console.log('\n【用例1】成员保存「姓名不能为空」校验修复');
ok(/var TM_VISIBLE_IDS=new Set\(\)/.test(htmlSrc), '维护当前可见成员 id 集合 TM_VISIBLE_IDS');
ok(/TM_VISIBLE_IDS=new Set\(filtered\.map\(m=>m\.id\)\)/.test(htmlSrc),
  'renderTeamList 按筛选结果更新可见集合');
ok(/const visible=TM_ALL\.filter\(m=>TM_VISIBLE_IDS\.has\(m\.id\)\)/.test(htmlSrc),
  '保存时只提交可见行');
ok(/const hidden=TM_ALL\.length-visible\.length/.test(htmlSrc), '统计被筛选隐藏的成员数');
ok(/另有 \$\{hidden\} 位成员被筛选隐藏，未提交/.test(htmlSrc), '提示隐藏成员未被提交');
ok(!/for\(const m of TM_ALL\)\{\s*const name=\(document\.getElementById/.test(htmlSrc),
  '不再遍历全量 TM_ALL 取 DOM 值（避免取不到姓名）');
ok(/if\(!name\)\{toast\(`ID \$\{m\.id\} 的姓名不能为空`\);return\}/.test(htmlSrc),
  '仍保留可见行的姓名必填校验');
ok(/if\(!visible\.length\)\{\s*toast\('当前筛选结果为空，没有可保存的成员'\);return;/.test(htmlSrc),
  '筛选结果为空时给出明确提示');

// ============================================================
// 用例 2：架构管理优先的权限覆盖
// ============================================================
console.log('\n【用例2】架构管理优先的权限覆盖规则');
ok(/def _member_authority_nodes\(username\)/.test(pySrc), '新增权威归属推导 _member_authority_nodes');
ok(/def _member_workgroup_names\(username\)/.test(pySrc), '新增权威工作组名推导 _member_workgroup_names');
ok(/def _org_leader_nodes\(username\)/.test(pySrc), '新增架构任命中的负责人节点推导 _org_leader_nodes');
ok(/org_appointments[\s\S]{0,400}唯一权威源/.test(pySrc), '文档标注 org_appointments 为唯一权威源');
ok(/scope, _src = _member_authority_nodes\(username\)/.test(pySrc),
  '_member_dept_scope 改用权威推导（不再取并集）');
ok(/names, _src = _member_workgroup_names\(username\)/.test(pySrc),
  '_group_boards 改用权威工作组名');
ok(/org_rows = _org_leader_nodes\(username\)/.test(pySrc),
  '_leader_boards 优先采用架构管理里的负责人任命');
ok(/'org_source'/.test(pySrc) && /'org_conflict'/.test(pySrc) && /'org_nodes'/.test(pySrc),
  '/api/team 返回归属来源与冲突信息');
ok(/org_source:m\.org_source\|\|'none'/.test(htmlSrc), '前端 TM_ALL 带出归属来源字段');
ok(/架构管理任命/.test(htmlSrc), '成员表格展示「架构管理任命」标注');
ok(/忽略：/.test(htmlSrc), '冲突时提示被忽略的工作组');
ok(/历史归属（架构管理未任命）/.test(htmlSrc), '回退来源有明确文案');

// ============================================================
// 用例 3：树形组件追加末级人员 + 人员筛选
// ============================================================
console.log('\n【用例3】树形组件追加末级人员与人员筛选');
ok(/def _collect_node_members\(node_id: int, nodes, appts\)/.test(pySrc),
  '后端收集节点末级人员');
ok(/node\['members'\] = _collect_node_members/.test(pySrc), '/api/org/tree 节点带 members 字段');
ok(/cc: Optional\[str\] = None/.test(pySrc), '/api/cards 增加 cc（参与人）筛选参数');
// ⚠️ 2026-11-04：cards 的过滤逻辑已抽到共用函数 _filter_cards_for_user
//    （列表与 xlsx 导出共用同一套 → 页面筛选对导出结果生效）
ok(/def _filter_cards_for_user\(/.test(pySrc) && /if cc:/.test(pySrc),
  'cards 按参与人过滤（逻辑在共用过滤函数 _filter_cards_for_user 内）');
ok(/onames = \[x\.strip\(\) for x in owner\.split\(','\)/.test(pySrc), 'owner 支持多值（逗号分隔）');
ok(/cnames = \[x\.strip\(\) for x in cc\.split\(','\)/.test(pySrc), 'cc 支持多值（逗号分隔）');
ok(/var ORG_PERSON_PREFIX='__P__'/.test(htmlSrc), '人员前缀统一为常量');
ok(/pickMode==='person'/.test(htmlSrc), '树形组件支持 person 模式');
ok(/function tpPersonClick\(name\)/.test(htmlSrc), '人员条目可勾选');
ok(/ORG_PERSON_PREFIX\+m\.name/.test(htmlSrc), '人员条目用前缀写入 selected');
ok(/x\.slice\(ORG_PERSON_PREFIX\.length\)/.test(htmlSrc), '回传时按常量长度剥离前缀');
ok(/class="tp-node tp-person"/.test(htmlSrc), '人员条目有独立样式类');
// 人员树选择器：节点框改为**可点击级联**（不再是置灰死元素），
// 父节点勾选/取消会联动其下属人员；人员条目位于可折叠容器内（折叠随父节点隐藏）。
ok(/\.tp-box-node\{/.test(htmlSrc), 'person 模式下节点勾选框可点击（级联勾选）');
ok(/function tpPersonUnder\(node\)/.test(htmlSrc), '提供节点下属人员收集函数 tpPersonUnder');
ok(/function openPersonFilterPicker\(anchor\)/.test(htmlSrc), '卡片列表页提供「按人员筛选」入口');
ok(/id="personFilterInput"/.test(htmlSrc) && /id="personFilterChips"/.test(htmlSrc),
   '人员筛选是可输入 + 多选控件（输入框 + chips）');
ok(/PERSON_SEL=new Set\(persons/.test(htmlSrc), '架构选人结果写入独立的 PERSON_SEL 集合');
ok(/function applyPersonFilter\(kind, persons\)/.test(htmlSrc), '套用逻辑 applyPersonFilter');
// 人员筛选锚定在**负责人维度**：与 owner 条件同字段、两者取交集，不再改写负责人下拉
ok(/ps\.set\('person'/.test(htmlSrc), 'reload 提交独立的 person 参数（与 owner 并存 → 交集）');
ok(!/opt\.value=names; opt\.textContent='负责人：'/.test(htmlSrc),
   '不再往负责人下拉注入自定义 option（旧实现的条件覆盖根源）');
ok(/ps\.set\('cc',cc\)/.test(htmlSrc), 'reload 带上 cc 参数');
ok(/async function ensureOrgTree\(force\)/.test(htmlSrc), '架构树按需加载（支持强制刷新）');
// 2026-11-04 #54 层级约束：事项的负责人/参与人从**所属板块**的负责人与参与人中选
// → 「从架构选人」按钮整体移除，选人池由 cardPickPool 从板块元数据计算。
ok(!/addOrgPickBtn/.test(htmlSrc) && !/openOrgPersonPick/.test(htmlSrc),
  '「从架构选人」按钮及其入口已移除（事项选人收口到板块池）');
ok(/async function cardPickPool\(boardId,columnName\)/.test(htmlSrc),
  '事项选人池 = 所属板块的负责人与参与人（cardPickPool，缺失时回退看板池）');
// 2026-11-05 取消互斥：配对参数保留（历史签名），但 ppToggle/ppAddTyped 已不再互剔
ok(/initPersonPicker\('e_owner',[^\n]*'e_cc',true\)/.test(htmlSrc),
  '负责人/参与人选择器配对参数保留（互斥逻辑已取消，签名兼容）');
ok(/orgTreeForNode\(nodeId\)/.test(htmlSrc) && !/orgTreeWithoutNames\(/.test(htmlSrc),
  '看板层选人范围 = 归属架构子树（互斥剔除函数已随取消互斥移除）');
ok(/class="pp-in"/.test(htmlSrc), '人员选择器仍保留手动输入（与架构选人并存）');
ok(/ORG_PERSON_NAMES=new Set\(\)/.test(htmlSrc), '汇总架构人员名以区分手动输入项');

// ============================================================
// 用例 4：成员表格角色筛选默认「全部角色」
// ============================================================
console.log('\n【用例4】角色筛选默认全部角色');
ok(/var TM_FILTER=\{name:'',workgroup:\[\],role:\[\]\}/.test(htmlSrc),
  'TM_FILTER 声明的默认角色为空数组（全部角色）');
ok(/TM_FILTER=\{name:'',workgroup:\[\],role:\[\]\};   \/\/ 默认全部角色/.test(htmlSrc),
  'openTeamModal 初始化为全部角色');
ok(/TM_FILTER=\{name:'',workgroup:\[\],role:\[\]\};   \/\/ 重置回全部角色/.test(htmlSrc),
  'resetTmFilter 重置回全部角色');
ok(/const roleList=Array\.isArray\(TM_FILTER\.role\)\?TM_FILTER\.role:\[\]/.test(htmlSrc),
  'renderTeamList 的兜底值也是空数组');
ok(!/role:\['noaccount'\]/.test(htmlSrc), '已无任何 role:[\'noaccount\'] 的默认写法');
ok(/const isAllRoles=roleList\.length>=ALL_ROLES\.length/.test(htmlSrc),
  '勾选满 4 类角色时视同全部（不漏掉有账号但无角色记录的成员）');
ok(/不勾选任何角色 = 显示全部角色/.test(htmlSrc), '角色弹窗有语义提示');
ok(/:'全部角色'/.test(htmlSrc), '筛选按钮文案为「全部角色」');

// ============================================================
// 用例 5：成员页面工作组控件下线 + 只读层级树 + 表头冻结
// ============================================================
console.log('\n【用例5】成员页面工作组控件下线与只读层级树');
// —— 控件整体下线 ——
ok(!/t_new_wg_btn/.test(htmlSrc), '新增成员的「工作组」选择控件已删除');
ok(!/t_new_wg_tags/.test(htmlSrc), '新增成员的工作组标签容器已删除');
ok(!/ADD_WG_SEL/.test(htmlSrc), 'ADD_WG_SEL 状态已清理');
ok(!/renderAddWgTags/.test(htmlSrc), 'renderAddWgTags 已清理');
ok(!/removeAddWg/.test(htmlSrc), 'removeAddWg 已清理');
ok(!/flattenWgToLeaves/.test(htmlSrc), 'flattenWgToLeaves 已清理');
ok(!/🌳 选择工作组/.test(htmlSrc), '表格内的「选择工作组」按钮已删除');
ok(!/tm-grp-cell/.test(htmlSrc), '工作组列的样式类已清理');
ok(!/已选工作组（最细颗粒）/.test(htmlSrc), '表头冗余括号注释已删除');
ok(/text-align:left;width:230px">已选工作组</.test(htmlSrc), '表头为「已选工作组」');
// —— 只读层级树 ——
ok(/function renderMemberWgTree\(m\)/.test(htmlSrc), '提供只读层级树渲染 renderMemberWgTree');
ok(/function memberWgTreeNodes\(m\)/.test(htmlSrc), '裁剪成员相关子树 memberWgTreeNodes');
ok(/function toggleWgTree\(el, key\)/.test(htmlSrc), '支持逐级展开/收起 toggleWgTree');
ok(/closest\(':scope > \.wgt-children'\)/.test(htmlSrc) || /:scope > \.wgt-children/.test(htmlSrc),
  '展开用局部 DOM 操作（不重绘表格）');
ok(!/function toggleWgTree\(el, key\)\{[\s\S]{0,200}renderTeamList\(\);/.test(htmlSrc),
  '展开不重绘表格（否则会丢失未保存的编辑内容）');
ok(/var WG_TREE_EXPANDED=new Set\(\)/.test(htmlSrc), '展开状态独立维护');
ok(/默认收起/.test(htmlSrc) || /display:\$\{exp\?'block':'none'\}/.test(htmlSrc),
  '节点默认收起、点击展开');
ok(!/class="tp-box"/.test(htmlSrc.slice(htmlSrc.indexOf('function renderWgTreeLevel'), htmlSrc.indexOf('function renderMemberWgTree'))),
  '只读树内无勾选框（无编辑入口）');
ok(/m\.org_source==='org' && \(m\.org_nodes\|\|\[\]\)\.length/.test(htmlSrc),
  '树的权威源是架构管理的任命');
ok(/WG_TREE_EXPANDED\.has\(key\)/.test(htmlSrc), '展开状态按节点 key 记忆');
// —— 表头冻结 ——
ok(/\.tm-table-scroll\{border:1px solid var\(--border\);border-radius:8px;overflow:visible/.test(htmlSrc),
  '表格容器不独立滚动（避免与弹窗主体形成双滚轮）');
ok(/\.tm-table-scroll thead th\{position:sticky;top:var\(--tm-sticky-top,0px\);z-index:2/.test(htmlSrc),
  '表头首行冻结（相对弹窗主体滚动，top 避开常驻筛选栏）');
ok(/function syncTmStickyTop\(\)/.test(htmlSrc), '测量筛选栏高度以确定表头 sticky 偏移');
ok(/document\.addEventListener\('resize'/.test(htmlSrc), '视口变化时重算表头偏移');
// —— 后端：归属收敛到架构管理 ——
ok(/class TeamReq\(BaseModel\):\s*name: str\s*\n\s*# workgroups 已下线/.test(pySrc),
  'TeamReq 不再接受 workgroups');
ok(/class TeamUpdateReq\(BaseModel\):\s*name: str\s*\n\s*account:/.test(pySrc),
  'TeamUpdateReq 不再接受 workgroups');
ok(!/UPDATE team_members SET name=\?, workgroups=\?/.test(pySrc),
  'PUT 不再写 workgroups（否则会清空架构管理同步的数据）');
ok(/dbe\('DELETE FROM org_appointments WHERE member_id=\?', \(mid,\)\)/.test(pySrc),
  '删除成员时显式清理架构管理的任职记录');

// ============================================================
// 用例 6：成本看板硬编码特例移除 + 架构管理弹窗修复 + 双滚轮
// ============================================================
console.log('\n【用例6】成本看板特例移除与弹窗修复');
ok(!/COST_BOARD_ID/.test(htmlSrc), '前端已无 COST_BOARD_ID 常量');
ok(!/isCostCard/.test(htmlSrc), '前端已无 isCostCard()');
ok(!/成本卡仅管理员/.test(htmlSrc), '前端已无「成本卡仅管理员」文案');
ok(!/tab-lock/.test(htmlSrc), '前端已无 tab-lock 锁样式');
ok(/function canEditCard\(c\)\{return !!\(ME&&ME\.can_edit\)\}/.test(htmlSrc),
  'canEditCard 统一看角色');
ok(/function canEditColumn\(boardId\)\{return !!\(ME&&ME\.can_edit\)\}/.test(htmlSrc),
  'canEditColumn 统一看角色');
ok(!/COST_BOARD_IDS/.test(pySrc), '后端已无 COST_BOARD_IDS');
ok(!/check_cost_permission/.test(pySrc), '后端已无 check_cost_permission');
ok(!/成本卡仅管理员可操作/.test(pySrc), '后端已无「成本卡仅管理员可操作」');
// 架构管理弹窗：ensureOrgTree 后不得再引用已移走的局部变量 od
ok(/await ensureOrgTree\(true\);\s*\n\s*ORG_TYPE_NAMES=ORG_TYPE_NAMES\|\|\{\};/.test(htmlSrc),
  'openWgModal 不再引用已移走的 od（否则 ReferenceError → 弹窗打不开）');
ok(/ORG_ROLES_BY_TYPE=od\.roles_by_type\|\|ORG_ROLES_BY_TYPE;/.test(htmlSrc),
  'ORG_ROLES_BY_TYPE 的赋值已移入 ensureOrgTree');
// —— 移除成本看板特例后必须补上板块可见性校验（否则越权）——
ok(/def check_board_access\(board_id: str, username: str\)/.test(pySrc),
  '新增看板准入校验 check_board_access');
ok(/无权访问该看板/.test(pySrc), '看板不可见时拒绝写操作');
ok(/def check_column_access\(board_id: str, column_id: str, username: str\)/.test(pySrc),
  '新增板块准入校验 check_column_access（板块不可见时拒绝写入）');
ok(/def check_card_access\(card_id: str, username: str, need_edit: bool = False\)/.test(pySrc),
  '新增按卡片定位看板的可见性校验 check_card_access（读接口用）');
ok((pySrc.match(/check_board_access\(/g)||[]).length>=9,
  '写接口均接入 check_board_access（'+(pySrc.match(/check_board_access\(/g)||[]).length+' 处）');
ok(/\.tm-table-scroll\{[^}]*flex-shrink:0/.test(htmlSrc),
  '表格容器 flex-shrink:0（否则被 flex 压扁且无法滚动）');
ok(/#teamModal \.modal-body>\*\{flex-shrink:0\}/.test(htmlSrc),
  '成员弹窗主体子项一律不参与 flex 压缩');

// —— 架构管理任命后刷新 ——
ok(/async function ensureOrgTree\(force\)/.test(htmlSrc),
  'ensureOrgTree 支持强制刷新参数');
ok(/await ensureOrgTree\(true\);/.test(htmlSrc),
  'openWgModal 用强制模式重新拉取架构树（任命后必须拿最新数据）');
ok(/if\(!force && ORG_TREE&&ORG_TREE\.length\) return ORG_TREE;/.test(htmlSrc),
  '独立入口（按人员筛选等）仍走缓存，不重复打接口');
ok(/const keepSel=ORG_SELECTED;/.test(htmlSrc) && /selectOrgNode\(keepSel\)/.test(htmlSrc),
  '任命刷新后保持当前选中节点（不重置表单）');
ok(/await openWgModal\(\);/.test(htmlSrc),
  '任命 / 免职成功后重新加载弹窗');

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
