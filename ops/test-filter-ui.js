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
ok(/id="weekFilterDrop"/.test(htmlSrc),
   '周数控件有候选下拉面板（勾选式多选）');
ok(/id="personFilterDrop"/.test(htmlSrc) === false,
   '人员控件无候选下拉面板（入口已转移到架构树）');
ok(/id="personFilterTreeBtn"/.test(htmlSrc) === false,
   '人员控件右侧的 🌳 按钮已移除（点击输入框直接开树）');
ok(/id="personFilterInput"[^>]*readonly/.test(htmlSrc),
   '人员输入框为只读触发器（点击打开架构树）');
ok(/onclick="openPersonFilterPicker\(this\)"/.test(htmlSrc),
   '点击人员输入框直接打开架构树弹窗');
ok(/class="cf-opt /.test(htmlSrc), '候选为勾选式（.cf-opt + checkbox，周数面板）');
ok(!/id="personFilterBtn"/.test(htmlSrc), '旧的「按人员筛选」按钮已移除');
ok(!/id="weekFilterBtn"/.test(htmlSrc), '旧的「📅 周数」按钮已移除');
// 输入匹配：人员改为在**树内**搜索（tp_search），周数按数字/标签匹配
// ⚠️ 搜索事件用 addEventListener 绑定（不是内联属性）：顶层 let 变量不在 window 上，
//    内联处理器访问不到 script scope → IME 组合标志位设不进去 → 打不出拼音
ok(/id="tp_search"/.test(htmlSrc) && /function bindTpSearch\(\)/.test(htmlSrc),
   '树弹窗内有搜索框（按姓名过滤人员）');
ok(/inp\.addEventListener\('compositionstart'/.test(htmlSrc) &&
   /inp\.addEventListener\('compositionend'/.test(htmlSrc) &&
   /inp\.addEventListener\('input'/.test(htmlSrc),
   '搜索框绑定 compositionstart / compositionend / input（IME 兼容）');
ok(/var TP_COMPOSING=false/.test(htmlSrc),
   'IME 组合标志用 var 声明（挂到 window，内联/闭包都能访问）');
ok(/if\(TP_COMPOSING\|\|\(e&&e\.isComposing\)\)return;/.test(htmlSrc),
   '组合期间忽略 input 事件（拼音未上屏，不过滤）');
ok(/function renderTreePickBody\(\)/.test(htmlSrc),
   '提供 renderTreePickBody()（只刷内容区，不重建搜索框）');
ok(/function tpNodeMatches\(n,kw\)/.test(htmlSrc),
   '提供 tpNodeMatches()（按姓名过滤节点与人员）');
ok(/function tpSubtreeHasMatch\(n,kw\)/.test(htmlSrc),
   '提供 tpSubtreeHasMatch()（搜索时自动展开到命中项路径）');
ok(/weekLabelOf\(w\)\.toLowerCase\(\)\.includes\(kw\)/.test(htmlSrc),
   '周数候选按输入文本匹配（支持 2026-41 形式）');
// 周数排序：必须按 202601~202644 的组合整数序，不能用字符串序
ok(/function weekSortKey\(v\)/.test(htmlSrc), '提供 weekSortKey()（组合整数排序键）');
ok(/parseInt\(m\[1\],10\)\*100\+parseInt\(m\[2\],10\)/.test(htmlSrc),
   'weekSortKey 把「2026年第41周」折成 202641 这样的组合整数');
ok(/\.sort\(\(a,b\)=>weekSortKey\(a\)-weekSortKey\(b\)\)/.test(htmlSrc),
   '周数候选按组合整数序排序（非字符串序）');
ok(/def week_sort_key\(v\)/.test(pySrc), '后端提供 week_sort_key()（与前端同口径）');
ok(/sorted\(weeks, key=week_sort_key\)/.test(pySrc), '后端候选接口按组合整数序返回周数');
ok(/key=week_sort_key\)/.test(pySrc), '后端列表接口的周数选项按组合整数序排序');
// 周数输入归一：41 / 2026-41 / 2026年第41周
ok(/function normWeekInput\(raw\)/.test(htmlSrc), '提供周数归一函数 normWeekInput');
ok(/\\d\{4\}\)\\s\*年\?\\\s\*第\\\s\*\(\\d\{1,2\}\)/.test(htmlSrc) ||
   /m=s\.match\(\/\^\(\\d\{4\}\)/.test(htmlSrc), '周数归一支持「2026年第41周」');
// 2026-11-04 #53：输入格式统一为「2026-41」，移除纯数字「41」支持
ok(!/return new Date\(\)\.getFullYear\(\)\+'年第'\+w\+'周'/.test(htmlSrc),
   '纯数字周数「41」已不再支持（格式统一为年份-周数）');
ok(/onFilterComboKey\(kind,ev\)/.test(htmlSrc), '回车提交输入值（加入多选集合）');
ok(/toast\('周数格式应为 2026-41（年份-周数）'\)/.test(htmlSrc),
   '非法周数给出明确提示（2026-41 口径）');

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
ok(/此处的筛选条件按「负责人」维度生效/.test(htmlSrc) === false,
   '人员下拉面板已下线（原文案随之移除）');
ok(/负责人为空的成员/.test(htmlSrc), '树上「无负责人」节点说明其语义（负责人为空的成员）');
// 后端候选接口（权限过滤）
ok(/@app\.get\('\/api\/filter-options'\)/.test(pySrc), '提供筛选候选接口 /api/filter-options');
ok(/'people': sorted\(people\)/.test(pySrc) && /'weeks': sorted\(weeks, key=week_sort_key\)/.test(pySrc),
   '候选接口返回人员与周数名单（周数按组合整数序）');
// ⚠️ 2026-11-03：SQL 补上 board_id / column_id 两列 ——
//    perm_pass() 要用它们做两级过滤，只 SELECT owner/week_no 会抛 KeyError（非管理员 500）。
ok(/rows = filter_rows\(dbq\('SELECT owner, week_no, board_id, column_id FROM cards WHERE deleted=0'\)/.test(pySrc),
   '候选名单取自权限可见范围内的事项（越权数据不出现；board_id/column_id 必带）');

// ============================================================
// 用例 3：人员树状展开
// ============================================================
console.log('\n【用例3】人员树状展开/收起与状态同步');
ok(/node_id': cur\}/.test(pySrc), '后端成员记录带 node_id（人员归属到实际任职节点）');
ok(/m\.node_id===n\.id/.test(htmlSrc), '前端按 node_id 过滤，人员只挂在真正任职的那一层');
ok(/const hasBody=hasCh\|\|allMembers\.length>0/.test(htmlSrc),
   '有子节点或有直属人员 → 节点才可展开');
ok(/<div id="tp_children_\$\{n\.id\}" style="display:\$\{showBody\?'block':'none'\}">\$\{memberHtml\}/.test(htmlSrc),
   '人员条目渲染在可折叠容器内部（折叠时随父节点隐藏；搜索时按 showBody 自动展开）');
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
// 2026-11-04：统计带 4 张卡片（总事项/已完成/进行中/未完成）——
// 3 张可点击卡共用 card() 模板 → 按 toggleStatCard 出现次数断言（3 个 onclick + 1 定义）
// 模板只有一处 card() 助手（运行时渲染 3 张）→ 断言数据源与点击能力而非出现次数
ok(/ov\.progressing/.test(htmlSrc) && /stat-click/.test(htmlSrc) && /toggleStatCard/.test(htmlSrc),
   '统计带含 4 张卡片（新增「进行中」，3 张可点击筛选）');
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
// ⚠️ 术语纠正（2026-11-02）：这条带渲染的是 ME.boards = 后端 boards 表 = **看板**，
//    此前标题误写为「可选板块」——看板与板块被混用，已改正。
ok(/<div class="tb-band-title">可选看板<\/div>/.test(htmlSrc),
   '「可选板块」标题已纠正为「可选看板」（该带渲染的是 boards 表，不是板块）');
ok(!/<div class="tb-band-title">可选板块<\/div>/.test(htmlSrc),
   '旧标题「可选板块」已不存在（术语混用已纠正）');
ok(/<div class="tb-band-title">架构部门<\/div>/.test(htmlSrc), '「架构部门」标题保留');
// ⚠️ 2026-11-03：「统计概览」标题已按用户要求去掉（三张卡自带标签），统计带移到公告栏下方。
ok(!/<div class="tb-band-title">统计概览<\/div>/.test(htmlSrc), '「统计概览」标题已移除（卡片自带标签）');
ok(/class="tb-band tb-stat-band"/.test(htmlSrc), '统计带仍存在（已移到公告栏下方）');

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
// 需求5（2026-11-02）已废除「窄屏恢复换行」策略，改为「窄屏锁定最小宽度 + 横向滚动」。
// 旧断言要求存在 @media(max-width:1024px){.toolbar-left{flex-wrap:wrap}} —— 策略已变，断言失效（T-002）。
// → 改为断言**现行策略**：
ok(/html\{min-width:1200px;overflow-x:auto/.test(htmlSrc),
   '窄屏锁定最小宽度 1200px（文档不再被压窄）');
ok(/html\{min-width:1200px;overflow-x:auto[^}]*overflow-y:visible/.test(htmlSrc),
   '窄屏横向滚动、纵向不滚动（overflow-y 不被误设）');
ok(/@media\(max-width:1199px\)\{[\s\S]{0,400}?\.toolbar-left\{flex-wrap:nowrap\}/.test(htmlSrc),
   '窄屏兜底断点（≤1199px）内筛选区仍 nowrap（不换行，避免双重变形）');
// T-006 闭环（2026-11-02）：`.toolbar{flex-wrap:nowrap}` 已被 UI设计师 删除 ——
//    新需求「筛选明细独占一行」要求 .toolbar 保持 wrap（明细行靠 flex:1 0 100% 强制换行）。
//    旧断言与新需求**直接冲突** → 断言翻转为校验现行策略。
ok(!/@media\(max-width:1199px\)\{[\s\S]{0,400}?\.toolbar\{flex-wrap:nowrap\}/.test(htmlSrc),
   '窄屏兜底断点不再强制 .toolbar nowrap（与「筛选明细独占一行」新策略一致）');
ok(/\.filter-hint\{[^}]*flex:1 0 100%/.test(htmlSrc),
   '筛选明细行靠 flex:1 0 100% 强制独占一行（工具栏需保持 wrap）');
ok(/\.toolbar-left\{[^}]*flex-wrap:nowrap/.test(htmlSrc),
   '筛选区基础规则即 nowrap（与窄屏兜底一致）');
ok(!/@media\(max-width:1024px\)\{\s*\.toolbar-left\{flex-wrap:wrap\}/.test(htmlSrc),
   '旧策略「≤1024px 恢复换行」已被需求5 废除，不再存在');

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
ok(/tree:ORG_TREE,\s*\n?\s*showNoneOwner:true/.test(htmlSrc) || /tree:ORG_TREE, showNoneOwner:true/.test(htmlSrc),
   '架构树入口传入 showNoneOwner');
ok(/wantNone=!!\(meta&&meta\.none\)/.test(htmlSrc), '树弹窗确认时回传「无负责人」状态');
ok(/if\(wantNone\)PERSON_SEL\.add\(OWNER_NONE\)/.test(htmlSrc),
   '「无负责人」回填进 PERSON_SEL（与负责人维度同一集合）');
// 下拉面板里不应再有「无负责人」条目（避免两处重复入口）
ok(/data-pick-person="\$\{OWNER_NONE\}"/.test(htmlSrc) === false,
   '人员下拉面板不再有「无负责人」条目（只在树上呈现）');
ok(/id="ownerFilter"/.test(htmlSrc) === false, '独立的「全部负责人」下拉已移除');

// ============================================================
// 用例 7：架构部门排序改为「JS 按名排序」（T-003）
//   原实现用纯 CSS order + :nth-child 映射，映射依赖后端 DOM 序号，
//   后端顺序一变（新增部门追加到末尾）即失效 → 改为 JS 侧按部门名排序。
// ============================================================
console.log('\n【用例7】部门排序：JS 按名排序（不依赖后端 DOM 序号）');
ok(/const DEPT_VISUAL_ORDER=\[/.test(htmlSrc), '前端有部门视觉顺序名录 DEPT_VISUAL_ORDER');
ok(/function deptVisualRank\(name\)/.test(htmlSrc), '提供 deptVisualRank()（按名取位次）');
ok(/function sortDeptsByName\(list\)/.test(htmlSrc), '提供 sortDeptsByName()（按名排序）');
ok(/localeCompare\(String\(b\),'zh-Hans-CN'\)/.test(htmlSrc),
   '名录外部门用中文拼音排序兜底（localeCompare zh-Hans-CN）');
ok(/const ordered=sortDeptsByName\(depts\)/.test(htmlSrc) &&
   /depts:ordered\.map\(d=>\(\{name:d,boards:map\[d\]\}\)\)/.test(htmlSrc),
   'groupBoardsByDept() 用排序后的列表（顶部部门带 / 部门切换下拉 / 初始选中 三处同步生效）');
// 旧实现必须已被移除
ok(/tb-dept-band \.tb-grid>\*\{order/.test(htmlSrc) === false,
   '已移除 CSS order 映射（.tb-dept-band .tb-grid>*{order:0}）');
ok(/tree-dept:nth-child\(\d\)\}\{order/.test(htmlSrc) === false,
   '已移除依赖 DOM 序号的 :nth-child → order 映射');
ok(/nth-child\(6\)/.test(htmlSrc) === false, '不再有 nth-child(6) 之类的硬编码序号映射');
// 需求1 的目标顺序仍在
ok(/财务中心.*商务部.*核算部/.test(htmlSrc),
   '视觉顺序名录保持需求1 指定值（财务中心/商务部/核算部…）');

// ============================================================
// 用例 8：板块切换的联动 + 空状态 + 初始状态
//   1) 切换部门/板块时所有区域整体联动，不残留上一个板块的内容
//   2) 目标板块无数据时显示明确空状态（该板块暂无数据）
//   3) 初始进入看板、未选板块时内容区默认为空（请选择板块）
// ============================================================
console.log('\n【用例8】板块切换联动 / 空状态 / 初始状态');
// 初始状态：不再自动选中板块
ok(/function ensureInitialSelection\(\)/.test(htmlSrc), '提供 ensureInitialSelection()');
ok(/function ensureInitialSelection\(\)\{[\s\S]{0,600}?curBoard=/.test(htmlSrc) === false,
   'ensureInitialSelection 不再自动设置 curBoard（初始不选板块）');
ok(/let LAST_EMPTY_REASON=/.test(htmlSrc), '有空状态原因标记 LAST_EMPTY_REASON');
// 空状态渲染
ok(/function renderEmptyBoardState\(\)/.test(htmlSrc), '提供 renderEmptyBoardState()');
// ⚠️ 术语纠正（2026-11-02）：curBoard 存的是 board_id（**看板**），
//    空状态文案此前写成「请选择板块 / 该板块暂无数据」→ 已改为看板口径。
ok(/请选择看板/.test(htmlSrc), '空状态文案含「请选择看板」');
ok(/该看板暂无数据/.test(htmlSrc), '空状态文案含「该看板暂无数据」');
ok(!/请选择板块/.test(htmlSrc), '旧文案「请选择板块」已不存在（术语混用已纠正）');
// 切换联动
ok(/function selectDeptBoards\(name\)/.test(htmlSrc), '提供 selectDeptBoards()（按部门选板块）');
ok(/function boardBelongsToOpenDept\(\)/.test(htmlSrc),
   '提供 boardBelongsToOpenDept()（判断当前板块是否仍属展开中的部门）');
ok(/function clearBoardSelection\(reason\)/.test(htmlSrc), '提供 clearBoardSelection()（清空板块选择）');
// 2026-11-17 #141：架构选择改多选（与板块选择同款交互）——toggleDept 改为
// toggle ARCH_SEL + syncArchSelection（选架构=批量选中其自身挂载看板，
// 统计卡随多选架构累加汇总）；旧断言（selectDeptBoards/部门已收起）已过时
ok(/function toggleDept\(name\)\{[\s\S]{0,600}?ARCH_SEL\.(add|delete)\(name\)/.test(htmlSrc),
   'toggleDept 为架构多选 toggle（ARCH_SEL 增删）');
ok(/function toggleDept\(name\)\{[\s\S]{0,600}?syncArchSelection\(\)/.test(htmlSrc),
   'toggleDept 联动 syncArchSelection（架构 → 看板选择重算）');
ok(/var ARCH_SEL=new Set\(\)/.test(htmlSrc), '提供 ARCH_SEL 多选集合（架构选中态）');
ok(/ARCH_SEL\.forEach\(function\(name\)\{[\s\S]{0,400}curBoards\.add\(b\.board_id\)/.test(htmlSrc),
   'syncArchSelection 把选中架构自身挂载看板并入 curBoards（不含下级部门看板）');
// 2026-11-04：看板选择改为 curBoards 多选集合 → 守卫条件同步
ok(/if\(!curBoards\.size\)\{renderEmptyBoardState\(\)/.test(htmlSrc),
   'reload 在未选看板时直接渲染空状态（不拉全量数据）');
// 统计带按板块取数
// 2026-11-04：多看板 → 单选带 board_id、多选带 board_ids
ok(/board_id='\+encodeURIComponent\(\[...curBoards\]\[0\]\)/.test(htmlSrc) &&
   /board_ids='/.test(htmlSrc),
   '统计带按当前选择取数（单选 board_id / 多选 board_ids）');

console.log('\n结果：%d 通过 / %d 失败', pass, fail);
process.exit(fail ? 1 : 0);
