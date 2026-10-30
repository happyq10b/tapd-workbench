// 筛选栏改造 + 顶部栏布局专项回归测试（前端源码断言）
// 覆盖：
//   1) 人员/周数筛选改为「可输入 + 多选」表单控件
//   2) 人员筛选锚定在负责人维度：与 owner 条件同字段、取交集，互不覆盖
//   3) 人员树状展开：人员随父节点折叠、父节点级联三态、展开状态跨弹窗保持
//   4) 顶部栏左右分栏 + 左半三列多行 + 右半公告独立区 + 响应式断点
// 运行：node ops/test-filter-ui.js
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'app.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

// ============================================================
// 用例 1：人员 / 周数筛选改为可输入 + 多选
// ============================================================
console.log('\n【用例1】人员/周数筛选为可输入多选控件');
ok(/id="personFilterInput"/.test(htmlSrc), '人员筛选有文本输入框');
ok(/id="weekFilterInput"/.test(htmlSrc), '周数筛选有文本输入框');
ok(/class="cf-input"/.test(htmlSrc), '两个输入框共用 .cf-input 样式');
ok(/id="personFilterChips"/.test(htmlSrc) && /id="weekFilterChips"/.test(htmlSrc),
   '两个控件都有已选 chips 区（多选可见）');
ok(/id="personFilterDrop"/.test(htmlSrc) && /id="weekFilterDrop"/.test(htmlSrc),
   '两个控件都有候选下拉面板（勾选式多选）');
ok(/class="cf-opt"/.test(htmlSrc), '候选为勾选式（.cf-opt + checkbox）');
ok(!/id="personFilterBtn"/.test(htmlSrc), '旧的「按人员筛选」按钮已移除');
ok(!/id="weekFilterBtn"/.test(htmlSrc), '旧的「📅 周数」按钮已移除');
// 输入匹配：人员按姓名模糊匹配、周数按数字/标签匹配
ok(/PERSON_OPTIONS\.filter\(n=>!kw\|\|n\.toLowerCase\(\)\.includes\(kw\)\)/.test(htmlSrc),
   '人员候选按输入文本模糊匹配');
ok(/weekLabelOf\(w\)\.toLowerCase\(\)\.includes\(kw\)/.test(htmlSrc),
   '周数候选按输入文本匹配（支持 2026-41 形式）');
// 周数输入归一：41 / 2026-41 / 2026年第41周
ok(/function normWeekInput\(raw\)/.test(htmlSrc), '提供周数归一函数 normWeekInput');
ok(/\\d\{4\}\)\\s\*年\?\\\s\*第\\\s\*\(\\d\{1,2\}\)/.test(htmlSrc) ||
   /m=s\.match\(\/\^\(\\d\{4\}\)/.test(htmlSrc), '周数归一支持「2026年第41周」');
ok(/return new Date\(\)\.getFullYear\(\)\+'年第'\+w\+'周'/.test(htmlSrc),
   '纯数字周数按当前年补全（41 → 2026年第41周）');
ok(/onFilterComboKey\(kind,ev\)/.test(htmlSrc), '回车提交输入值（加入多选集合）');
ok(/toast\('周数格式应为 41 \/ 2026-41 \/ 2026年第41周'\)/.test(htmlSrc),
   '非法周数给出明确提示');

// ============================================================
// 用例 2：人员筛选锚定负责人维度（取交集、互不覆盖）
// ============================================================
console.log('\n【用例2】人员筛选与负责人筛选解耦（交集语义）');
ok(/person: Optional\[str\] = None/.test(pySrc), '后端 /api/cards 支持 person 参数');
ok(/if person:/.test(pySrc) && /r\.get\('owner'\)/.test(pySrc),
   'person 条件作用在 owner 字段（与负责人条件同字段）');
ok(/ps\.set\('person',\[...PERSON_SEL\]\.join\(','\)\)/.test(htmlSrc),
   'reload 提交 person 参数（与 owner 同时提交 → 服务端求交集）');
ok(/let PERSON_SEL=new Set\(\)/.test(htmlSrc), '人员筛选有独立状态集合 PERSON_SEL');
ok(!/opt\.value=names; opt\.textContent='负责人：'/.test(htmlSrc),
   '不再往负责人下拉注入自定义 option（旧实现的条件覆盖根源）');
ok(/opt=sel\.querySelector\('option\[data-multi="1"\]'\)/.test(htmlSrc) === false,
   '已移除 option[data-multi] 的注入逻辑');
ok(/PERSON_SEL=new Set\(persons\)/.test(htmlSrc), '架构选人结果直接写入 PERSON_SEL');
ok(/function syncFilterHint\(\)/.test(htmlSrc), '提供统一的筛选条件提示');
ok(/parts\.push\('人员：'/.test(htmlSrc), '提示中区分「负责人」与「人员」两个条件');
ok(/两者取交集/.test(htmlSrc), '界面文案说明与负责人条件取交集');
// 后端候选接口（权限过滤）
ok(/@app\.get\('\/api\/filter-options'\)/.test(pySrc), '提供筛选候选接口 /api/filter-options');
ok(/'people': sorted\(people\)/.test(pySrc) && /'weeks': sorted\(weeks\)/.test(pySrc),
   '候选接口返回人员与周数名单');
ok(/rows = filter_rows\(dbq\('SELECT owner, week_no FROM cards WHERE deleted=0'\), boards, columns\)/.test(pySrc),
   '候选名单取自权限可见范围内的事项（越权数据不出现）');

// ============================================================
// 用例 3：人员树状展开
// ============================================================
console.log('\n【用例3】人员树状展开/收起与状态同步');
ok(/node_id': cur\}/.test(pySrc), '后端成员记录带 node_id（人员归属到实际任职节点）');
ok(/m\.node_id===n\.id/.test(htmlSrc), '前端按 node_id 过滤，人员只挂在真正任职的那一层');
ok(/const hasBody=hasCh\|\|members\.length>0/.test(htmlSrc),
   '有子节点或有直属人员 → 节点才可展开');
ok(/<div id="tp_children_\$\{n\.id\}" style="display:\$\{exp\?'block':'none'\}">\$\{memberHtml\}/.test(htmlSrc),
   '人员条目渲染在可折叠容器内部（折叠时随父节点隐藏）');
ok(/var TREE_EXPANDED=new Set\(\)/.test(htmlSrc), '展开状态用全局集合保存（跨弹窗保持）');
ok(/TREE_EXPANDED\.add\(id\)/.test(htmlSrc) && /TREE_EXPANDED\.delete\(id\)/.test(htmlSrc),
   '展开/收起同步写入全局集合');
ok(/const expanded=new Set\(\);/.test(htmlSrc) && /TREE_EXPANDED\.has\(n\.id\)/.test(htmlSrc),
   '打开弹窗时从全局集合恢复展开状态');
ok(/TREE_EXPANDED\.delete\(n\.id\)/.test(htmlSrc), '收起父节点时清理后代展开标记');
ok(/function tpPersonUnder\(node\)/.test(htmlSrc), '提供节点下属人员收集（级联勾选用）');
ok(/tp-box-node/.test(htmlSrc), '节点框可点击（级联勾选下属人员）');
ok(/'half'/.test(htmlSrc) && /setBox\(box, under\.length===0\?'off':\(sel===0\?'off':\(sel===under\.length\?'on':'half'\)\)\)/.test(htmlSrc),
   '节点框显示三态（全选 / 半选 / 未选）');
ok(/if\(TREE_PICK\.pickMode==='person'\)\{[\s\S]{0,400}tpPersonUnder\(node\)/.test(htmlSrc),
   'person 模式下点击节点框 → 级联勾选其下属人员');
ok(/function tpPersonClick\(name\)\{[\s\S]{0,400}paintAll\(\)/.test(htmlSrc),
   '勾选人员后重绘整棵树（父节点三态同步）');
ok(/data-pbox="\$\{esc\(m\.name\)\}"/.test(htmlSrc), '人员框用 data 属性标记（同名人员不冲突）');
ok(/TREE_PICK\.tree=ORG_TREE;/.test(htmlSrc) && /renderTreePick\(\);/.test(htmlSrc),
   '架构数据刷新后重绘打开中的选择器');
ok(/ensureOrgTree\(true\)/.test(htmlSrc), '打开人员筛选时强制刷新架构数据');

// ============================================================
// 用例 4：顶部栏左右分栏布局
// ============================================================
console.log('\n【用例4】顶部栏左右分栏 + 三列多行');
ok(/<div class="topbar" id="topbar">/.test(htmlSrc), '存在顶部栏容器 .topbar');
ok(/<aside class="topbar-aside" id="topbarAside">/.test(htmlSrc), '右半为独立的公告区 aside');
ok(/id="tbDepts"/.test(htmlSrc) && /id="tbBoards"/.test(htmlSrc) && /id="progressOverview"/.test(htmlSrc),
   '左半三带：架构部门 / 板块 / 统计概览');
ok(/grid-template-columns:minmax\(0,1fr\) minmax\(300px,420px\)/.test(htmlSrc),
   '顶部栏两列：左自适应 + 右公告列 300~420px');
ok(/\.topbar-main\{display:grid;grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/.test(htmlSrc),
   '左半主区为三列栅格');
ok(/\.tb-grid\{display:grid;grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/.test(htmlSrc),
   '每个带内部也是三列小栅格');
ok(/\.tb-band\{grid-column:1\/-1/.test(htmlSrc), '三个带各跨满三列');
ok(/\.topbar-aside \.notice-bar\{flex:1/.test(htmlSrc), '公告区撑满右列高度（独立展示空间）');
ok(/@media\(max-width:1180px\)/.test(htmlSrc) && /@media\(max-width:900px\)/.test(htmlSrc) &&
   /@media\(max-width:640px\)/.test(htmlSrc), '提供 1180 / 900 / 640 三档响应式断点');
ok(/\.topbar\{grid-template-columns:minmax\(0,1fr\);gap:10px\}/.test(htmlSrc),
   '900px 以下：上下堆叠（公告区落到左半下方）');
ok(/if\(topbar\)topbar\.style\.display='none'/.test(htmlSrc),
   '进入部门页时隐藏整个顶部栏（含公告区）');
ok(/document\.getElementById\('tbDepts'\)/.test(htmlSrc) && /document\.getElementById\('tbBoards'\)/.test(htmlSrc),
   'renderTabs 填充部门带与板块带');
ok(/getElementById\('progressOverview'\)/.test(htmlSrc), 'renderProgress 填充统计带');
ok((htmlSrc.match(/class="stat-card"/g) || []).length >= 3, '统计带含 3 张卡片');
// 旧的 progress-overview 内嵌公告结构应已移除
ok(!/<div class="notice-bar" id="noticeBar"><\/div>`\s*;\s*await renderNoticeBar/.test(htmlSrc),
   '统计带不再内嵌公告栏（公告已独立到右半）');

console.log('\n结果：%d 通过 / %d 失败', pass, fail);
process.exit(fail ? 1 : 0);
