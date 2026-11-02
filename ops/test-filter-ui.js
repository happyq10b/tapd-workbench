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
// 用例 2：人员筛选独占「负责人」维度（独立负责人下拉已下线）
// ============================================================
console.log('\n【用例2】人员筛选独占负责人维度（「全部负责人」下拉已下线）');
ok(/person: Optional\[str\] = None/.test(pySrc), '后端 /api/cards 支持 person 参数');
ok(/if person:/.test(pySrc) && /r\.get\('owner'\)/.test(pySrc),
   'person 条件作用在 owner 字段（负责人维度）');
ok(/ps\.set\('person',\[...PERSON_SEL\]\.join\(','\)\)/.test(htmlSrc),
   'reload 提交 person 参数');
ok(/!captured\.includes\('owner='\)/.test(fs.readFileSync(path.join(__dirname, 'test-filter.js'), 'utf8')),
   '前端不再提交 owner 参数（下拉下线后由 person 独占）');
ok(/let PERSON_SEL=new Set\(\)/.test(htmlSrc), '人员筛选有独立状态集合 PERSON_SEL');
ok(!/<select class="filter-select" id="ownerFilter"/.test(htmlSrc), '独立的「全部负责人」下拉已从 HTML 移除');
ok(!/<option value="">全部负责人<\/option>/.test(htmlSrc), '「全部负责人」选项已移除');
ok(/const OWNER_NONE='__no_owner__'/.test(htmlSrc), '前端定义 OWNER_NONE 特殊值');
ok(/id="tp_opt_none"/.test(htmlSrc), '「无负责人」选项在树弹窗的「显示选项」区');
ok(/data-pick-person="\$\{OWNER_NONE\}"/.test(htmlSrc) === false,
   '人员下拉面板里已无「无负责人」条目（改由树弹窗承载）');
ok(/want_none = OWNER_NONE in pnames/.test(pySrc), '后端 person 分支支持 __no_owner__');
ok(/PERSON_SEL=new Set\(persons/.test(htmlSrc), '架构选人结果直接写入 PERSON_SEL');
ok(/function syncFilterHint\(\)/.test(htmlSrc), '提供统一的筛选条件提示');
ok(/parts\.push\('人员：'/.test(htmlSrc), '提示中展示人员条件');
ok(/此处的筛选条件按「负责人」维度生效/.test(htmlSrc), '界面文案说明按负责人维度生效');
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

// ============================================================
// 用例 5：本次 UI 调整（圆点 / 标题 / 下拉下线 / 筛选栏同行）
// ============================================================
console.log('\n【用例5】UI 调整：去掉浮空圆点 / 标题加粗 / 下拉下线 / 筛选栏同行');

// 5.1 浮空圆点：.my-status-bar 的 display:flex 覆盖了 [hidden] 的 UA 样式
ok(/\.my-status-bar\[hidden\]\{display:none\}/.test(htmlSrc),
   '个人状态栏有 [hidden] 兜底（否则状态圆点会孤零零浮在顶栏左上角）');
ok(/bar\.hidden=!st/.test(htmlSrc), '状态文字为空时整条状态栏隐藏');

// 5.2 三个标题加粗 + 放大
ok(/\.tb-band-title\{font-size:13px;font-weight:700/.test(htmlSrc),
   '带标题加粗（font-weight:700）且放大到 13px');
ok(/<div class="tb-band-title">可选板块<\/div>/.test(htmlSrc),
   '「板块」标题改为「可选板块」');
ok(/<div class="tb-band-title">架构部门<\/div>/.test(htmlSrc), '「架构部门」标题保留');
ok(/<div class="tb-band-title">统计概览<\/div>/.test(htmlSrc), '「统计概览」标题保留');

// 5.3 「全部负责人」下拉下线
ok(!/id="ownerFilter"/.test(htmlSrc), 'HTML 无 ownerFilter 元素');
ok(!/<option value="">全部负责人<\/option>/.test(htmlSrc) && !/<option value="__no_owner__">/.test(htmlSrc),
   'HTML 无「全部负责人 / 无负责人」下拉选项');
ok(!/getElementById\('ownerFilter'\)/.test(htmlSrc), 'JS 不再引用 ownerFilter');
ok(/const OWNER_NONE='__no_owner__'/.test(htmlSrc), 'OWNER_NONE 特殊值');
ok(/function personLabel\(v\)/.test(htmlSrc), 'personLabel() 显示文案转换');

// 5.4 筛选栏：缩小人员/周数输入框 + 日期区间同行
ok(/\.cf-field\{[^}]*width:104px;max-width:220px/.test(htmlSrc),
   '人员/周数输入区缩到 104px（上限 220px）');
ok(/\.cf-input\{[^}]*min-width:52px/.test(htmlSrc), '输入框最小宽度缩到 52px');
ok(/\.toolbar-left\{[^}]*flex-wrap:nowrap/.test(htmlSrc),
   '筛选区不换行（日期区间与其它控件同一行）');
ok(/\.filter-date\{[^}]*width:122px/.test(htmlSrc), '日期输入框缩到 122px');
ok(/\.date-filter\{[^}]*flex:0 0 auto/.test(htmlSrc), '日期区间容器固定宽度（不参与压缩）');
ok(/@media\(max-width:1024px\)\{\s*\.toolbar-left\{flex-wrap:wrap\}/.test(htmlSrc),
   '窄屏（≤1024px）恢复换行，避免溢出');

// ============================================================
// 用例 6：组织架构树状图的交互调整
//   6.1 顶部工具栏：一键展开/折叠全部（多级批量，折叠保留顶层可见）
//   6.2 「无负责人」从下拉面板移入树上的显示选项
// ============================================================
console.log('\n【用例6】树状图交互：展开/折叠全部 + 「无负责人」选项');
// 6.1 展开/折叠按钮
ok(/class="tp-toolbar"/.test(htmlSrc), '树弹窗有顶部工具栏 .tp-toolbar');
ok(/onclick="tpExpandAll\(\)"/.test(htmlSrc) && /onclick="tpCollapseAll\(\)"/.test(htmlSrc),
   '工具栏含「展开全部 / 折叠全部」两个按钮');
ok(/function tpExpandAll\(\)/.test(htmlSrc), '提供 tpExpandAll()（多级批量展开）');
ok(/function tpCollapseAll\(\)/.test(htmlSrc), '提供 tpCollapseAll()（多级批量折叠）');
ok(/ids\.forEach\(id=>\{TREE_EXPANDED\.add\(id\);TREE_PICK\.expanded\.add\(id\);\}\)/.test(htmlSrc),
   '展开全部递归收集所有层级节点 id 并写入展开集合');
ok(/TREE_EXPANDED\.clear\(\);\s*TREE_PICK\.expanded\.clear\(\);/.test(htmlSrc),
   '折叠全部清空展开集合（顶层节点行本身不收起 → 仍可见）');
// 展开/折叠不得影响筛选条件
ok(!/function tpExpandAll\(\)\{[\s\S]{0,400}selected/.test(htmlSrc),
   'tpExpandAll 不修改 selected（展开状态与筛选条件互不影响）');
ok(!/function tpCollapseAll\(\)\{[\s\S]{0,400}?TREE_PICK\.selected\s*[.\[]/.test(htmlSrc),
   'tpCollapseAll 不修改 selected（展开状态与筛选条件互不影响）');
// 6.2 「无负责人」选项
ok(/showNoneOwner/.test(htmlSrc), '树弹窗支持 showNoneOwner（是否提供「无负责人」选项）');
ok(/id="tp_opt_none"/.test(htmlSrc), '「显示选项」区有独立的「无负责人」复选框');
ok(/class="tp-opts"/.test(htmlSrc) && /显示选项/.test(htmlSrc),
   '「显示选项」区与现有筛选条件并列');
ok(/class="tp-none-node"/.test(htmlSrc) && /tn-tag">无负责人/.test(htmlSrc),
   '树上以「无负责人」标签/节点样式呈现（.tp-none-node + 标签）');
ok(/function tpToggleNoneOwner\(\)/.test(htmlSrc), '提供 tpToggleNoneOwner()（独立启用开关）');
ok(/showNoneOwner:true/.test(htmlSrc), '人员筛选的树弹窗启用了该选项');
ok(/tree:ORG_TREE, showNoneOwner:true/.test(htmlSrc), '架构树入口传入 showNoneOwner');
ok(/wantNone=!!\(meta&&meta\.none\)/.test(htmlSrc), '树弹窗确认时回传「无负责人」状态');
ok(/if\(wantNone\)PERSON_SEL\.add\(OWNER_NONE\)/.test(htmlSrc),
   '「无负责人」回填进 PERSON_SEL（与负责人维度同一集合）');
// 下拉面板里不应再有「无负责人」条目（避免两处重复入口）
ok(/data-pick-person="\$\{OWNER_NONE\}"/.test(htmlSrc) === false,
   '人员下拉面板不再有「无负责人」条目（只在树上呈现）');
ok(/id="ownerFilter"/.test(htmlSrc) === false, '独立的「全部负责人」下拉已移除');

console.log('\n结果：%d 通过 / %d 失败', pass, fail);
process.exit(fail ? 1 : 0);
