// 部门主页 + @ 提及 + 消息中心 + 多年份筛选 专项回归测试
// 覆盖：
//   1) 部门主页：左右分栏结构、核心指标同屏、次要指标折叠、标杆/模范两块与小锦旗
//   2) 部门联动：切换部门时清空旧数据（加载态）、过期响应丢弃、视图互斥
//   3) 编辑权限：仅管理员可见编辑入口；保存三态提示；图片类型与大小校验
//   4) 评论 @ 提及：输入态/已插入态分离、chip 渲染与移除、正文 @ 高亮
//   5) 消息中心：未读数、查看详情、标记已读、跳转对应事项
//   6) 多年份筛选：多选、单个移除、清空全部
// 运行：node ops/test-dept.js
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlPath = path.join(ROOT, 'src', 'static', 'index.html');
const htmlSrc = fs.readFileSync(htmlPath, 'utf8');
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

// ---------- 最小 DOM stub ----------
function adopt(parent, child) {
  if (!parent || !child) return;
  if (child.parentNode && child.parentNode._kids) {
    const i = child.parentNode._kids.indexOf(child);
    if (i >= 0) child.parentNode._kids.splice(i, 1);
  }
  child.parentNode = parent;
  if (!parent._kids) parent._kids = [];
  if (!parent._kids.includes(child)) parent._kids.push(child);
}
const ELEMS = {};
function mkEl(id) {
  const attrs = {};
  const el = {
    id, value: '', textContent: '', _html: '', style: {}, dataset: {},
    checked: false, disabled: false, hidden: false, tagName: 'DIV', options: [],
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      toggle(c, force) {
        if (force === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); }
        else { force ? this._s.add(c) : this._s.delete(c); }
      },
      contains(c) { return this._s.has(c); },
    },
    addEventListener() {}, removeEventListener() {}, focus() {}, click() {}, blur() {},
    querySelector() { return mkEl(id + '>q'); },
    querySelectorAll() { return []; },
    closest() { return null; },
    appendChild(child) {
      adopt(el, child);
      if (el.options && child.tagName === 'option') el.options.push(child);
      return child;
    },
    insertBefore(child) { adopt(el, child); return child; },
    remove() {},
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    setSelectionRange() {},
    get innerHTML() { return el._html; },
    set innerHTML(v) { el._html = String(v); },
  };
  ELEMS[id] = el;
  return el;
}
const document = {
  getElementById(id) { return ELEMS[id] || (ELEMS[id] = mkEl(id)); },
  createElement(tag) { const e = mkEl('new-' + tag); e.tagName = tag.toUpperCase(); return e; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'),
  documentElement: mkEl('html'),
  activeElement: null,
};
const localStorage = { getItem: () => '', setItem() {}, removeItem() {} };
const sandbox = {
  document, localStorage, console,
  setTimeout, clearTimeout, setInterval, clearInterval,
  location: { href: '' }, navigator: { userAgent: 'node' },
  fetch: async () => ({ status: 200, ok: true, json: async () => ({}) }),
  alert() {}, confirm: () => true,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(main, sandbox, { filename: 'index-inline.js' }); }
catch (e) { console.error('装载失败:', e); process.exit(1); }

function getEl(id) { return document.getElementById(id); }
function setLet(name, value) { vm.runInContext(`${name}=${JSON.stringify(value)};`, sandbox); }
function getLet(name) { return vm.runInContext(name, sandbox); }
function setLetSet(name, arr) { vm.runInContext(`${name}=new Set(${JSON.stringify(arr)});`, sandbox); }
function getLetSet(name) { return [...vm.runInContext(name, sandbox)]; }

// ============================================================
(async () => {
  console.log('\n【用例1】部门主页：结构、指标压缩、标杆/模范');
  // ============================================================
  setLet('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [], depts: [] });
  setLet('TEAM_MEMBERS', ['王伟娜', '吴婷婷']);

  // ---- 头部布局：按钮过多会把标题挤成竖排（用户反馈的「年份筛选按钮有问题」）----
  ok(/\.header-left\{[^}]*flex-shrink:0/.test(htmlSrc), '头部左侧禁止收缩（否则标题被压成竖排）');
  ok(/\.header-left h1\{[^}]*white-space:nowrap/.test(htmlSrc), '标题禁止换行');
  ok(/\.header-actions\{[^}]*flex-wrap:wrap/.test(htmlSrc), '右侧按钮区允许换行');
  ok(/\.year-filter\{[^}]*flex-wrap:nowrap/.test(htmlSrc), '年份筛选器不换行（换行会被固定高度裁掉）');
  ok(!/\.year-filter\{[^}]*height:\d+px/.test(htmlSrc), '年份筛选器不设固定高度（避免裁掉 chips）');
  // 低频按钮收进「更多」下拉
  ok(/id="headerMore"/.test(htmlSrc), '存在头部「更多」下拉容器');
  ok(/id="headerMoreMenu"/.test(htmlSrc), '存在「更多」菜单');
  ok(main.includes('function toggleHeaderMore'), '提供「更多」开关函数');
  ok(main.includes('function closeHeaderMore'), '提供「更多」收起函数');
  ok(/header-more-menu\[hidden\]\{display:none\}/.test(htmlSrc), '「更多」菜单默认隐藏');
  // 常驻按钮数量受控（原来 11 个平铺）
  const alwaysBtns = (htmlSrc.match(/class="header-btn[^"]*"/g) || []).length;
  ok(alwaysBtns <= 8, `常驻头部按钮不超过 8 个（实际 ${alwaysBtns}，其余收进「更多」）`);

  // 页面结构：左右分栏 + 部门页/列表页两个容器
  ok(/id="deptPageWrap"/.test(htmlSrc), '存在部门页容器 deptPageWrap');
  ok(/id="boardListWrap"/.test(htmlSrc), '存在事项列表容器 boardListWrap');
  ok(/id="deptSwitchBar"/.test(htmlSrc), '存在部门页顶部切换条');
  ok(/id="deptCultureCol"/.test(htmlSrc), '分栏一为部门文化展示区 deptCultureCol');
  ok(/id="deptWorkCol"/.test(htmlSrc), '分栏二为事项统计 deptWorkCol');
  ok(/class="dept-page"/.test(htmlSrc), '部门页用 .dept-page 网格做左右分栏');
  // 响应式：移动端折叠为上下堆叠
  ok(/@media\(max-width:1024px\)\{\s*\.dept-page\{grid-template-columns:1fr\}/.test(htmlSrc),
     '响应式：移动端 .dept-page 折叠为单列（上下堆叠）');
  // 部门节点的入口分离：整块=展开板块，独立的「主页」按钮=进部门页
  ok(/class="dept-home"/.test(htmlSrc), '部门节点有独立的「主页」入口按钮');
  ok(main.includes('event.stopPropagation();openDeptPage'), '「主页」按钮阻止冒泡（不连带触发展开/收起）');
  ok(/onclick="toggleDept\(/.test(htmlSrc), '部门块本身仍是展开/收起板块（保持原有行为）');

  const FAKE = {
    dept: '核算部',
    profile: { dept: '核算部', slogan: '精益核算 · 专业致远', intro: '核算部承担成本核算。', photo: '' },
    honors: [
      { id: 1, kind: 'dept', target_name: '总账部', remark: '零差错', photo: '', sort: 0 },
      { id: 2, kind: 'person', target_name: '王伟娜', remark: '标兵', photo: '', sort: 0 },
    ],
    stats: { total: 1136, done: 1010, progressing: 0, open: 126, overdue: 56, owner_missing: 719 },
    owner_stats: [{ owner: '吴春梅', count: 119 }, { owner: '吴婷婷', count: 101 }],
    workgroups: [{ id: 1, name: '成本组', leader: '刘自琴', function: '项目成本', description: '项目级核算', members: ['刘自琴'] }],
    boards: [],
  };
  sandbox.renderDeptCulture(FAKE);
  sandbox.renderDeptStats(FAKE);
  const culture = getEl('deptCultureBody').innerHTML;
  const stats = getEl('deptStatsBody').innerHTML;

  // 文化区：标语 + 职能介绍 + 合照占位
  ok(culture.includes('精益核算'), '文化区展示文化标语');
  ok(culture.includes('核算部承担成本核算'), '文化区展示部门职能介绍');
  ok(culture.includes('尚未上传团队合照'), '无合照时展示占位图');
  // 标杆/模范两块并列
  ok(culture.includes('标杆部门') && culture.includes('模范个人'), '同时展示【标杆部门】与【模范个人】');
  ok(culture.includes('honor-block bench'), '标杆区块带 bench 类（为小锦旗定位预留空间）');
  ok(culture.includes('honor-flag'), '标杆区块渲染小锦旗');
  ok((culture.match(/honor-flag/g) || []).length === 1, '小锦旗只有一处（挂在切块交界处）');
  ok(culture.includes('🚩'), '小锦旗用旗帜图标');

  // 统计区：核心指标同屏（4 个），次要指标折叠
  ok((stats.match(/class="dept-stats"/g) || []).length === 1, '核心指标区只有一组');
  const coreCount = (stats.match(/class="dept-stat"/g) || []).length;
  ok(coreCount >= 4, '核心指标至少 4 个同屏展示');
  ok(stats.includes('总事项') && stats.includes('已完成') && stats.includes('进行中') && stats.includes('未完成'),
     '核心指标含 总事项/已完成/进行中/未完成');
  ok(stats.includes('dept-more-toggle'), '提供「更多」展开入口');
  ok(stats.includes('已逾期'), '次要指标（已逾期）存在于「更多」区');
  ok((stats.match(/class="dept-more"[^>]*hidden/g) || []).length === 2, '「更多」区默认折叠');
  // 折叠区内含已逾期与负责人承担量
  ok(stats.includes('未分配负责人'), '次要指标含未分配负责人');
  ok(stats.includes('吴春梅'), '负责人承担量在「更多」区');

  // 「更多」可展开（toggleDeptMore 依赖 DEPT_DATA 才会重渲染）
  setLet('DEPT_DATA', FAKE);
  setLet('DEPT_MORE_OPEN', false);
  sandbox.toggleDeptMore();
  const stats2 = getEl('deptStatsBody').innerHTML;
  ok((stats2.match(/class="dept-more"[^>]*hidden/g) || []).length === 0, '点击「更多」后次要指标展开');
  // 再点一次 → 收起（toggleDeptMore 是取反，所以直接再调一次即可）
  sandbox.toggleDeptMore();
  ok((getEl('deptStatsBody').innerHTML.match(/class="dept-more"[^>]*hidden/g) || []).length === 2, '再次点击可收起');

  // ============================================================
  console.log('\n【用例2】部门联动：加载态、旧数据残留、视图互斥');
  // ============================================================
  // 切到部门页 → 列表页隐藏，部门页显示
  setLet('CUR_DEPT', '');
  sandbox.backToBoardList();
  eq(getEl('boardListWrap').style.display, '', '返回后事项列表页可见');
  eq(getEl('deptPageWrap').style.display, 'none', '返回后部门页隐藏');
  eq(getEl('boardTabs').style.display, '', '返回后顶部导航条恢复');
  eq(getEl('deptSwitchBar').style.display, 'none', '返回后部门切换条隐藏');

  // 打开部门页 → 部门页显示，列表页隐藏；切换时先渲染加载态（清空旧数据）
  let resolveFn = null;
  sandbox.api = () => new Promise(res => { resolveFn = res; });
  const p = sandbox.openDeptPage('核算部');
  eq(getEl('boardListWrap').style.display, 'none', '进入部门页后事项列表页隐藏');
  eq(getEl('deptPageWrap').style.display, '', '进入部门页后部门页可见');
  // 顶部导航条（部门节点 + 板块 tab）必须一并隐藏 —— 之前只切了两个 wrap 容器，
  // 导航条留在屏幕上与部门页内容同时出现，用户看到的"切换混乱"就是这个
  eq(getEl('boardTabs').style.display, 'none', '进入部门页后顶部导航条隐藏（不与部门页内容混排）');
  eq(getEl('deptSwitchBar').style.display, '', '进入部门页后显示部门切换条');
  ok(getEl('deptCultureBody').innerHTML.includes('加载中'), '切换部门时先渲染加载态（清空旧内容）');
  ok(getEl('deptStatsBody').innerHTML.includes('加载中'), '统计区同样先渲染加载态');
  // 过期响应：在用户切走后才返回 → 必须被丢弃
  setLet('CUR_DEPT', '总账部');
  resolveFn(FAKE);
  await p;
  ok(getEl('deptCultureBody').innerHTML.includes('加载中'), '过期的响应被丢弃，不覆盖当前部门内容');

  // 正常返回
  sandbox.api = async () => FAKE;
  await sandbox.openDeptPage('核算部');
  ok(getEl('deptCultureBody').innerHTML.includes('精益核算'), '正常响应渲染文化内容');
  ok(getEl('deptStatsBody').innerHTML.includes('1136'), '正常响应渲染统计指标');
  eq(getLet('CUR_DEPT'), '核算部', '当前部门已更新');
  eq(getEl('boardTabs').style.display, 'none', '仍在部门页时导航条保持隐藏');

  // 加载失败 → 错误态
  sandbox.api = async () => { throw new Error('网络异常'); };
  await sandbox.openDeptPage('管理部');
  ok(getEl('deptCultureBody').innerHTML.includes('加载失败'), '加载失败时展示错误提示');
  ok(getEl('deptStatsBody').innerHTML.includes('加载失败'), '统计区加载失败也有提示');

  // 返回后所有视图元素复原
  sandbox.backToBoardList();
  eq(getEl('boardTabs').style.display, '', '返回后顶部导航条恢复');
  eq(getEl('boardListWrap').style.display, '', '返回后事项列表页恢复');
  eq(getEl('deptPageWrap').style.display, 'none', '返回后部门页隐藏');
  eq(getEl('deptSwitchBar').style.display, 'none', '返回后部门切换条隐藏');

  // 部门切换条：下拉列出全部部门，当前部门选中
  sandbox.api = async () => FAKE;
  setLet('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin',
                 boards: [], depts: ['财务中心', '核算部', '总账部', '管理部', '资金部', '商务部'] });
  await sandbox.openDeptPage('核算部');
  const sw = getEl('deptSwitchSel').innerHTML;
  ok(sw.includes('财务中心') && sw.includes('商务部'), '部门切换条列出全部部门');
  ok(sw.includes('value="核算部" selected'), '部门切换条当前部门为选中态');

  // ============================================================
  console.log('\n【用例3】编辑权限、图片校验、保存三态');
  // ============================================================
  ok(/function openDeptEditModal\(\)/.test(main), '提供部门文化编辑入口');
  ok(/ME&&ME\.is_admin/.test(main), '编辑入口按管理员权限控制');
  ok(/仅管理员可编辑部门文化内容/.test(main), '非管理员点击给出明确提示');
  // 图片校验：类型与大小
  ok(/DEPT_IMG_TYPES\s*=\s*\['image\/jpeg','image\/png','image\/gif','image\/webp'\]/.test(main),
     '前端限定图片类型为 JPG/PNG/GIF/WebP');
  ok(/DEPT_MAX_IMG_BYTES\s*=\s*512\*1024/.test(main), '前端限定图片大小上限 512KB');
  ok(main.includes('仅支持 JPG / PNG / GIF / WebP 格式'), '类型不符时给出明确提示');
  ok(main.includes('请压缩到'), '大小超限时给出明确提示');
  // 失败保留占位图 + 重试
  ok(/function retryDeptPhoto\(\)/.test(main), '图片失败提供重试入口');
  ok(main.includes('upload-retry'), '失败时显示可点击的重试遮罩');
  ok(main.includes('图片读取失败，请重新选择'), '读取失败保留占位并提示重试');
  // 保存三态
  ok(/function setDeptStatus\(/.test(main), '提供保存状态提示函数');
  ok(main.includes("'saving'") && main.includes("'ok'") && main.includes("'fail'"), '保存状态含 保存中/成功/失败 三态');
  ok(main.includes('保存中…') && main.includes('保存成功') && main.includes('保存失败'), '三种状态都有明确文案');
  ok(/if\(btn\)\{btn\.disabled=true;btn\.textContent='保存中…'\}/.test(main), '保存中禁用按钮防重复提交');
  // 后端权限与校验
  ok(/@app\.put\('\/api\/dept\/\{dept\}\/profile'\)\s*\ndef update_dept_profile\(dept: str, req: DeptProfileReq, username: str = Depends\(require_admin\)/.test(pySrc),
     '后端保存部门文化要求管理员');
  ok(/@app\.post\('\/api\/dept\/\{dept\}\/honors'\)\s*\ndef create_dept_honor\(dept: str, req: DeptHonorReq, username: str = Depends\(require_admin\)/.test(pySrc),
     '后端新增标杆/模范要求管理员');
  ok(/@app\.post\('\/api\/dept\/\{dept\}\/posts'\)\s*\ndef create_dept_post\(dept: str, req: DeptPostReq, username: str = Depends\(require_admin\)/.test(pySrc),
     '后端发文要求管理员');
  ok(pySrc.includes('ALLOWED_IMAGE_TYPES'), '后端也做图片类型校验');
  ok(pySrc.includes('MAX_IMAGE_BYTES'), '后端也做图片大小校验');
  // 部门介绍页
  ok(/function openDeptIntroModal\(\)/.test(main), '提供部门介绍页入口');
  ok(main.includes('组织架构'), '介绍页展示组织架构');
  ok(main.includes('org-member'), '介绍页展示成员信息');
  ok(/function openDeptPostEditor\(\)/.test(main), '介绍页支持发文');
  ok(main.includes('pickDeptPostImages'), '发文支持发图');

  // ============================================================
  console.log('\n【用例4】评论 @ 提及：两态分离与正文高亮');
  // ============================================================
  ok(/id="d_new_comment"/.test(htmlSrc), '评论输入框存在');
  ok(/id="d_mention_bar"/.test(htmlSrc), '有独立的已插入提及区（与输入态区分）');
  ok(/id="d_mention_drop"/.test(htmlSrc), '有 @ 成员候选下拉');
  ok(main.includes('onCommentInput'), '输入时检测 @ 触发候选');
  ok(main.includes('mention-chip'), '已插入的提及以 chip 渲染');
  ok(main.includes('mc-x'), 'chip 支持单独移除');
  ok(/function removeMention\(/.test(main), '提供移除单个提及的函数');
  ok(/function pickMention\(/.test(main), '提供插入提及的函数');
  ok(main.includes('mentionCandidates'), '候选成员来自团队成员列表');
  ok(main.includes('COMMENT_MENTIONS'), '已插入提及存于独立状态');
  // 正文渲染时把 @姓名 高亮
  const rendered = sandbox.renderCommentText('请看下 @王伟娜 的意见');
  ok(rendered.includes('at-name'), '评论正文里的 @姓名 渲染为高亮标记');
  ok(rendered.includes('@王伟娜'), '高亮后文字内容保持不变');
  // 提交时把 chip 合并成正文
  setLet('COMMENT_MENTIONS', ['王伟娜']);
  setLet('DETAIL_ID', 'C1');
  let saved = null;
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'POST') { saved = JSON.parse(opt.body); return { ok: true }; }
    return { cards: [], columns: [], comments: [], actions: [] };
  };
  getEl('d_new_comment').value = '请看下';
  await sandbox.addComment();
  ok(saved && saved.mentions && saved.mentions.includes('王伟娜'), '提交时携带 mentions 列表');
  ok(saved && saved.content.includes('@王伟娜'), '提交时 chip 合并为正文里的 @姓名');

  // 后端：comments 表加 mentions 字段 + 消息投递
  ok(/mentions\s+TEXT NOT NULL DEFAULT ''/.test(initDbSrc), 'comments 表有 mentions 字段');
  ok(/CREATE TABLE IF NOT EXISTS messages/.test(initDbSrc), '存在消息中心表');
  ok(pySrc.includes('def _mention_receiver'), '有提及→收件人的映射逻辑');
  ok(pySrc.includes("INSERT INTO messages (receiver, sender, card_id, kind, content)"), '被提及时写入消息');
  ok(pySrc.includes("if not recv or recv == username"), "不给自己投递消息");
  ok(pySrc.includes("INSERT INTO comments (card_id, username, content, mentions)"), '评论落库时写入 mentions');

  // ============================================================
  console.log('\n【用例5】消息中心：未读、详情、已读、跳转');
  // ============================================================
  ok(/id="msgBtn"/.test(htmlSrc), '顶部有消息中心入口');
  ok(/id="msgBadge"/.test(htmlSrc), '有未读数徽章');
  ok(/id="msgPanel"/.test(htmlSrc), '有消息栏面板');
  ok(main.includes('refreshMessages'), '提供消息刷新函数');
  ok(main.includes('openMsgPanel'), '提供打开消息栏的函数');
  ok(main.includes('readAllMessages'), '提供全部标记已读');
  ok(main.includes('jumpToCard'), '提供跳转到对应事项的函数');
  ok(main.includes("api('/api/messages/'+id+'/read'"), '点击消息会标记已读');
  ok(main.includes("unread?'unread':'read'"), '未读消息有明确的未读标识');
  // 后端接口
  ok(/@app\.get\('\/api\/messages'\)/.test(pySrc), '有消息列表接口');
  ok(/@app\.post\('\/api\/messages\/\{mid\}\/read'\)/.test(pySrc), '有标记已读接口');
  ok(/@app\.post\('\/api\/messages\/read-all'\)/.test(pySrc), '有全部已读接口');
  ok(pySrc.includes("'unread'"), '接口返回未读数');

  // ============================================================
  console.log('\n【用例6】多年份筛选：多选、单个移除、清空全部');
  // ============================================================
  setLetSet('curYears', ['2025', '2026']);
  const COLS = [
    { column_name: '板块A', year: '2026' },
    { column_name: '板块B', year: '2025' },
  ];
  sandbox.renderYearFilter(COLS);
  const chips = getEl('yearFilter').innerHTML;
  ok((chips.match(/class="year-chip"/g) || []).length === 2, '两个已选年份 → 两个 chip');
  ok((chips.match(/class="yc-x"/g) || []).length === 2, '每个 chip 都有独立的移除入口');
  ok(chips.includes('data-all="1"'), '提供「全部年份」清空入口');
  // 单个移除
  setLetSet('curYears', ['2025', '2026']);
  vm.runInContext("curYears.delete('2025');", sandbox);
  sandbox.renderYearFilter(COLS);
  const chips2 = getEl('yearFilter').innerHTML;
  ok((chips2.match(/class="year-chip"/g) || []).length === 1, '移除单个年份后只剩一个 chip');
  // 清空全部
  setLetSet('curYears', []);
  sandbox.renderYearFilter(COLS);
  const chips3 = getEl('yearFilter').innerHTML;
  ok(!chips3.includes('data-year='), '清空全部后不再渲染年份 chip');
  ok(chips3.includes('data-all="1"'), '「全部年份」入口常驻');

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证异常:', e); process.exit(1); });
