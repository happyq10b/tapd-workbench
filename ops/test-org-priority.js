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
ok(/工作组选择（架构管理未任命）/.test(htmlSrc), '回退来源有明确文案');

// ============================================================
// 用例 3：树形组件追加末级人员 + 人员筛选
// ============================================================
console.log('\n【用例3】树形组件追加末级人员与人员筛选');
ok(/def _collect_node_members\(node_id: int, nodes, appts\)/.test(pySrc),
  '后端收集节点末级人员');
ok(/node\['members'\] = _collect_node_members/.test(pySrc), '/api/org/tree 节点带 members 字段');
ok(/cc: Optional\[str\] = None/.test(pySrc), '/api/cards 增加 cc（参与人）筛选参数');
ok(/if cc:\s*\n\s*# 参与人筛选/.test(pySrc), 'cards 接口按参与人过滤');
ok(/onames = \[x\.strip\(\) for x in owner\.split\(','\)/.test(pySrc), 'owner 支持多值（逗号分隔）');
ok(/cnames = \[x\.strip\(\) for x in cc\.split\(','\)/.test(pySrc), 'cc 支持多值（逗号分隔）');
ok(/var ORG_PERSON_PREFIX='__P__'/.test(htmlSrc), '人员前缀统一为常量');
ok(/pickMode==='person'/.test(htmlSrc), '树形组件支持 person 模式');
ok(/function tpPersonClick\(name\)/.test(htmlSrc), '人员条目可勾选');
ok(/ORG_PERSON_PREFIX\+m\.name/.test(htmlSrc), '人员条目用前缀写入 selected');
ok(/x\.slice\(ORG_PERSON_PREFIX\.length\)/.test(htmlSrc), '回传时按常量长度剥离前缀');
ok(/class="tp-node tp-person"/.test(htmlSrc), '人员条目有独立样式类');
ok(/\.tp-box-na\{/.test(htmlSrc), 'person 模式下节点勾选框置灰');
ok(/function openPersonFilterPicker\(anchor\)/.test(htmlSrc), '卡片列表页提供「按人员筛选」入口');
ok(/套用为负责人/.test(htmlSrc) && /套用为参与人/.test(htmlSrc), '所选人员可套用为负责人或参与人条件');
ok(/function applyPersonFilter\(kind, persons\)/.test(htmlSrc), '套用逻辑 applyPersonFilter');
ok(/window\._ccFilter=names/.test(htmlSrc), '参与人条件写入 _ccFilter');
ok(/ps\.set\('cc',cc\)/.test(htmlSrc), 'reload 带上 cc 参数');
ok(/async function ensureOrgTree\(\)/.test(htmlSrc), '架构树按需加载（幂等）');
ok(/await ensureOrgTree\(\)/.test(htmlSrc), '独立入口先加载架构树');
ok(/function addOrgPickBtn\(containerId, kind\)/.test(htmlSrc), '编辑弹窗加「从架构选人」按钮');
ok(/function openOrgPersonPick\(containerId, kind, anchor\)/.test(htmlSrc), '编辑弹窗打开 person 模式树');
ok(/addOrgPickBtn\('e_owner','owner'\)/.test(htmlSrc) && /addOrgPickBtn\('e_cc','cc'\)/.test(htmlSrc),
  '负责人与参与人两个选择器都接入架构选人');
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

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
