// 子事项交互回归测试（Node + 最小 DOM stub）
// 覆盖：1) 创建失败后表单重置；2) 创建成功后表单重置；
//       3) 目录点击打开子事项弹窗（字段裁剪 + 父事项约束）
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const main = blocks.sort((a, b) => b.length - a.length)[0];

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
function mkEl(id) {  const attrs = {};
  const el = {
    id,
    value: '',
    textContent: '',
    _html: '',
    style: {},
    dataset: {},
    checked: false,
    disabled: false,
    classList: { _s: new Set(), add(...c) { c.forEach(x => this._s.add(x)); }, remove(...c) { c.forEach(x => this._s.delete(x)); }, toggle(c) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); }, contains(c) { return this._s.has(c); } },
    addEventListener() {}, removeEventListener() {}, focus() {}, click() {}, blur() {},
    querySelector() { return mkEl(id + '>q'); },
    querySelectorAll() { return []; },
    closest() { return null; },
    appendChild(child) { adopt(el, child); return child; },
    insertBefore(child, ref) { adopt(el, child); return child; },
    remove() {}, setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    removeAttribute(k) { delete attrs[k]; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
  };
  el.parentNode = null;
  el._kids = [];
  Object.defineProperty(el, 'firstChild', { get() { return el._kids[0] || null; } });
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(v) { el._html = String(v); },
  });
  return el;
}
const els = new Map();
const getEl = (id) => { if (!els.has(id)) els.set(id, mkEl(id)); return els.get(id); };

const document = {
  getElementById: getEl,
  querySelector() { return mkEl('s'); },
  querySelectorAll() { return []; },
  createElement() { return mkEl('c'); },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'), documentElement: mkEl('de'), head: mkEl('head'),
};

const sandbox = {
  console,
  setTimeout: () => 0, clearTimeout: () => 0, setInterval: () => 0, clearInterval: () => 0,
  document,
  localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
  fetch: () => Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve({}) }),
  location: { href: 'http://127.0.0.1:8100/', search: '', pathname: '/', origin: 'http://127.0.0.1:8100' },
  history: {}, navigator: { userAgent: 'node' },
  alert: () => {}, confirm: () => true,
  WebSocket: function () { return { close() {}, send() {}, readyState: 0 }; },
  addEventListener() {}, removeEventListener() {},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
sandbox.self = sandbox;

vm.createContext(sandbox);
try { vm.runInContext(main, sandbox, { filename: 'index-inline.js' }); }
catch (e) { console.error('脚本装载失败:', e.message); process.exit(1); }

// ---------- 断言工具 ----------
let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}
function eq(a, b, msg) { ok(a === b, msg + `  (实际=${JSON.stringify(a)} 期望=${JSON.stringify(b)})`); }
// 脚本里 ME / TEAM_MEMBERS 用 let 声明（词法作用域），只能在该上下文内部赋值
function setVar(name, value) { vm.runInContext(`${name}=${JSON.stringify(value)};`, sandbox); }
// let 声明的普通状态变量同样只能通过上下文赋值/读取
function setLet(name, value) { vm.runInContext(`${name}=${JSON.stringify(value)};`, sandbox); }
function getLet(name) { return vm.runInContext(name, sandbox); }
// Set 类型的状态变量（年份多选 curYears）：需要整体替换而不是逐个赋值
function setLetSet(name, arr) { vm.runInContext(`${name}=new Set(${JSON.stringify(arr)});`, sandbox); }
function getLetSet(name) { return [...vm.runInContext(name, sandbox)]; }

// ============================================================
// 用例 1：创建子事项的弹窗 —— 与主事项共用同一个 newModal，字段/校验一致
// ============================================================
(async () => {
  console.log('\n【用例1】创建子事项弹窗（与主事项同构）');
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  setVar('TEAM_MEMBERS', ['王伟娜', '张三', '李四']);

  const SUB = {
    card_id: 'NC1', card_name: '子事项A', parent_id: 'P1', board_id: 'B1',
    status: 'progressing', owner: '王伟娜', cc: '张三', begin: '2026-03-02', due: '2026-03-20',
    description: '子事项描述', pinned: 0, created: '2026-10-28 08:00:00', locked_by: null,
  };
  const PARENT = {
    card_id: 'P1', card_name: '父事项A', parent_id: '', board_id: 'B1', board_name: '看板1',
    column_name: '费用组', status: 'open', owner: '王伟娜', begin: '2026-03-01', due: '2026-03-31',
    description: '', pinned: 0, created: '2026-10-28 07:00:00', locked_by: null,
  };
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=NC1')) return { cards: [SUB], columns: [] };
    if (String(p).includes('card_id=P1')) return { cards: [PARENT], columns: [] };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    if (String(p).endsWith('/comments')) return { comments: [] };
    if (String(p).endsWith('/actions')) return { actions: [] };
    return { cards: [], columns: [] };
  };

  // 打开「新建子事项」：与主事项共用 newModal，只是看板/板块的取值来源不同
  await sandbox.openNewSubModal('P1');
  eq(getEl('newModal').style.display, 'flex', '新建子事项弹窗已打开');
  eq(getEl('n_title').textContent, '新建子事项', '标题为「新建子事项」');
  eq(getEl('n_board').value, 'B1', '所属看板继承父事项并锁定');
  eq(getEl('n_board').disabled, true, '所属看板为只读（子事项继承父看板）');
  eq(getEl('n_col_wrap').style.display, '', '所属板块行展示（父事项所属板块）');
  eq(getEl('n_col').value, '费用组', '所属板块显示父事项的板块');
  eq(getEl('n_begin').getAttribute('min'), '2026-03-01', '开始日期受父事项起始约束(min)');
  eq(getEl('n_due').getAttribute('max'), '2026-03-31', '截止日期受父事项截止约束(max)');
  // 字段与主事项创建弹窗完全一致（状态按钮 / 负责人 / 日期 / 描述都在）
  ok(/id="n_status_ops"/.test(html), '新建弹窗有状态按钮（与主事项同一套组件）');
  ok(/id="n_owner"/.test(html), '新建弹窗有负责人字段');
  ok(/id="n_begin"/.test(html) && /id="n_due"/.test(html), '新建弹窗有开始/截止日期字段');
  ok(/id="n_desc"/.test(html), '新建弹窗有描述字段');

  // 校验：标题为空不发请求
  let posted = null;
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'POST') { posted = JSON.parse(opt.body); return { ok: true }; }
    return { cards: [], columns: [] };
  };
  getEl('n_name').value = '';
  await sandbox.createCard();
  ok(posted === null, '标题为空时不发起创建请求');

  // 校验：起止颠倒不发请求（主事项与子事项共用同一段校验）
  getEl('n_name').value = '新子事项';
  getEl('n_begin').value = '2026-05-01';
  getEl('n_due').value = '2026-04-01';
  await sandbox.createCard();
  ok(posted === null, '开始日期晚于截止日期时不发起创建请求（与主事项口径一致）');

  // 正常创建：字段齐全且挂在父事项下
  getEl('n_begin').value = '2026-03-02';
  getEl('n_due').value = '2026-03-20';
  getEl('n_desc').value = '子事项描述';
  sandbox.pickStatus('n', 'progressing');
  await sandbox.createCard();
  ok(posted && posted.parent_id === 'P1', '创建时挂在父事项下');
  eq(posted.card_name, '新子事项', '标题正确');
  eq(posted.fields.status, 'progressing', '状态正确（由状态按钮记录）');
  eq(posted.fields.status_name, '进行中', '状态文案正确');
  eq(posted.fields.begin, '2026-03-02', '开始日期正确');
  eq(posted.fields.due, '2026-03-20', '截止日期正确');
  eq(posted.fields.description, '子事项描述', '描述正确');

  // ============================================================
  // 用例 2：创建失败 → 弹窗不关闭、输入保留（与主事项同一套失败处理）
  // ============================================================
  console.log('\n【用例2】创建失败时弹窗保持打开');
  // 先用能正常返回父事项的 stub 把弹窗打开，再把创建请求换成失败
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=P1')) return { cards: [PARENT], columns: [] };
    return { cards: [], columns: [] };
  };
  await sandbox.openNewSubModal('P1');
  eq(getEl('newModal').style.display, 'flex', '新建子事项弹窗已打开');
  getEl('n_name').value = '会失败的子事项';
  getEl('n_desc').value = '描述保留';
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'POST') throw new Error('模拟创建失败');
    return { cards: [], columns: [] };
  };
  await sandbox.createCard();
  eq(getEl('newModal').style.display, 'flex', '创建失败后弹窗仍然打开（可直接改后重试）');
  eq(getEl('n_name').value, '会失败的子事项', '失败后标题保留（不丢用户输入）');
  eq(getEl('n_desc').value, '描述保留', '失败后描述保留');

  // ============================================================
  // 用例 3：目录点击子事项 → 打开详情弹窗（与主事项同构），编辑入口独立
  // ============================================================
  console.log('\n【用例3】目录点击子事项打开详情弹窗');
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=NC1')) return { cards: [SUB], columns: [] };
    if (String(p).includes('card_id=P1')) return { cards: [PARENT], columns: [] };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    if (String(p).endsWith('/comments')) return { comments: [] };
    if (String(p).endsWith('/actions')) return { actions: [] };
    return { cards: [], columns: [] };
  };
  sandbox.lockCard = async () => true;
  getEl('editModal').style.display = 'none';
  getEl('detailModal').style.display = 'none';

  await sandbox.openSubModal('NC1');

  eq(getEl('detailModal').style.display, 'flex', '子事项打开的是详情弹窗（不再直接进编辑）');
  eq(getEl('editModal').style.display, 'none', '编辑弹窗未自动打开（编辑流程与详情分离）');
  eq(getEl('d_title').textContent, '子事项A', '详情标题为子事项名');
  const meta = String(getEl('d_meta').innerHTML);
  ok(meta.includes('父事项'), '元信息展示「父事项」而非「板块」');
  ok(meta.includes('父事项A'), '元信息含父事项名称');
  ok(!meta.includes('状态：'), '元信息不重复呈现状态（由状态按钮承载）');
  // 与主事项详情同构：状态按钮 + 评论 + 操作记录 模块都在
  const dOps = String(getEl('d_ops').innerHTML);
  ok(dOps.includes('status-btn progressing'), '子事项详情带状态按钮');
  ok(dOps.includes('✏️ 编辑'), '子事项详情带独立的编辑入口');
  ok(/id="d_comments"/.test(html) && /id="d_actions"/.test(html),
    '评论与操作记录模块与主事项详情共用同一套 DOM');

  // 从详情进入编辑 → 编辑弹窗（子事项模式：字段裁剪 + 父约束）
  await sandbox.openDetailEdit();
  eq(getEl('editModal').style.display, 'flex', '从详情点「编辑」进入编辑弹窗');
  eq(getEl('editTitle').textContent, '编辑子事项', '标题为「编辑子事项」');
  eq(getEl('e_board_wrap').style.display, 'none', '「所属看板」已隐藏（子事项继承父看板）');
  ok(getEl('e_cc_wrap').style.display !== 'none', '「参与人」在子事项模式下可见（对标主事项）');
  eq(getEl('e_parent_wrap').style.display, '', '父事项信息区已展示');
  ok(String(getEl('e_parent_info').innerHTML).includes('父事项A'), '父事项信息含父事项名称');
  eq(getEl('e_begin').getAttribute('min'), '2026-03-01', '开始日期受父事项起始约束(min)');
  eq(getEl('e_due').getAttribute('max'), '2026-03-31', '截止日期受父事项截止约束(max)');
  eq(getEl('e_name').value, '子事项A', '标题已回填');
  ok(!/id="e_status"/.test(html), '编辑弹窗不再有状态下拉（状态统一由头部状态按钮承载）');
  eq(getEl('e_begin').value, '2026-03-02', '开始日期已回填');
  eq(getEl('e_due').value, '2026-03-20', '截止日期已回填');

  // 保存子事项：不得带上「参与人」（否则会写入上一个主事项的残留值）
  let saved = null;
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'PUT') { saved = JSON.parse(opt.body); return { ok: true }; }
    return { cards: [SUB], columns: [] };
  };
  await sandbox.saveEdit();
  ok(saved && saved.fields, '保存请求已发出');
  eq(saved.fields.cc, '张三', '保存子事项时提交参与人字段（与主事项一致，已回填的值）');
  ok(saved.fields.status === undefined, '保存时不发送状态字段（状态由头部状态按钮单独设置）');
  eq(saved.fields.owner, '王伟娜', '保存的负责人正确');
  ok(saved.fields.status_name === undefined, '保存时不发送状态文案');

  // ============================================================
  // 用例 4：目录行与抽屉行只保留唯一的状态切换入口（状态标签）
  // ============================================================
  console.log('\n【用例4】子事项行的置顶与状态切换入口');
  // 置顶是个人设置：子事项行的「已置顶」取决于当前账号的置顶集合
  sandbox.setPinned('card', 'NC1', true);
  const treeHtml = sandbox.subNodeHtml({ ...SUB, pinned: 0, status: 'done' }, 0);
  ok(treeHtml.includes('toggleCardPin'), '目录行含置顶按钮');
  ok(treeHtml.includes('toggleCardDone'), '目录行状态标签可切换完成状态');
  ok(treeHtml.includes('openSubModal'), '目录行点击打开子事项弹窗');
  ok(treeHtml.includes('已置顶'), '个人置顶后显示「已置顶」文案');
  ok(treeHtml.includes('已完成'), '完成状态有标记');
  ok(!treeHtml.includes('openDetail'), '目录行不再走只读详情弹窗');
  ok(!/完成<\/button>|done-btn|doneBtn/.test(treeHtml), '目录行已移除冗余的「完成」按钮');
  sandbox.setPinned('card', 'NC1', false);

  // 右侧抽屉已整体移除：子事项管理统一到弹窗（本期需求）
  ok(typeof sandbox.drawerSubTree === 'undefined', '抽屉子事项树函数已移除');
  ok(typeof sandbox.renderDrawerList === 'undefined', '抽屉渲染函数已移除');
  ok(!/id="drawerPanel"/.test(html), '抽屉面板 DOM 已移除');
  ok(!/id="drawerMask"/.test(html), '抽屉遮罩 DOM 已移除');
  ok(!/id="e_sub_btn"/.test(html), '编辑弹窗头部的「▤ 子事项」入口已移除（截图标注处）');
  // 行内「＋ 子事项」现在直接打开新建弹窗，不再经过抽屉
  ok(sandbox.cardItem({ ...SUB, pinned: 0, status: 'open' }, 1).includes('openNewSubModal'),
     '行内「＋ 子事项」直接打开新建子事项弹窗（不再走抽屉）');
  ok(!/openDrawer\(/.test(html), '代码里不再有 openDrawer 调用点');
  // 本期不支持子事项以下更深层级：目录树不再渲染孙节点
  const deepHtml = sandbox.subNodeHtml({
    ...SUB, pinned: 0, status: 'open',
    children: [{ card_id: 'NC2', card_name: '孙事项', status: 'open', children: [] }],
  }, 0);
  ok(!deepHtml.includes('孙事项'), '子事项行不再渲染下级（本期只支持两层）');
  ok(!deepHtml.includes('toggleSubNode'), '子事项行不再有下级展开箭头');
  // 状态标签的点击必须冒泡阻断，不能连带触发所在行的「打开弹窗」
  ok(treeHtml.includes('event.stopPropagation()'), '状态标签点击不触发所在行的打开动作');

  // ============================================================
  // 用例 5：新建子事项弹窗（与主事项同构，无内联表单）
  // ============================================================
  ok(/id="n_owner"/.test(html), '新建弹窗含负责人选择器（与主事项同构）');
  ok(/id="n_begin"/.test(html) && /id="n_due"/.test(html), '新建弹窗含开始/截止日期（与主事项同构）');
  ok(!/id="drawerBody"/.test(html), '抽屉内容容器已移除（不再有独立的面板表单区）');

  // ============================================================
  // 用例 6：「负责人」在子事项模式搬到状态右侧同一行，并标注选填
  // ============================================================
  console.log('\n【用例6】负责人字段的选填与位置');
  // 先开一次子事项弹窗（用例3已建立 API stub）
  await sandbox.openSubModal('NC1');
  const ownerGroup = getEl('e_owner_group');
  const metaRow = getEl('e_meta_row');
  const ownerRow = getEl('e_owner_row');
  ok(ownerGroup.parentNode === metaRow, '负责人已搬到「所属看板」所在行（该行原本的状态控件已移除）');
  ok(ownerRow.style.display === 'none', '原来的「负责人/参与人」行已收起（不占位、不错位）');
  eq(getEl('e_owner_opt').style.display, '', '负责人已标注「（选填）」');
  ok(metaRow._kids.includes(ownerGroup), '负责人确实是该行的子节点（网格第 2 列）');

  // 切回主事项：负责人必须还原到原行，且「（选填）」标注撤掉
  const MAIN = { ...PARENT, card_name: '主事项A' };
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=P1')) return { cards: [MAIN], columns: [] };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    return { cards: [], columns: [] };
  };
  await sandbox.openEdit('P1', MAIN);
  ok(ownerGroup.parentNode === ownerRow, '主事项模式下负责人已还原到原行');
  eq(ownerRow.style.display, '', '主事项模式下原行正常显示');
  eq(getEl('e_owner_opt').style.display, 'none', '主事项模式不显示「（选填）」标注');

  // ============================================================
  // 用例 7：点击涟漪反馈已挂载
  // ============================================================
  console.log('\n【用例7】目录项点击反馈');
  ok(typeof sandbox.attachRipple === 'function', '涟漪反馈函数已提供');
  const boardContent = getEl('boardContent');
  ok(boardContent._rippleBound === true, '看板容器已绑定涟漪反馈');
  ok(!/id="drawerBody"/.test(html), '抽屉容器已随抽屉一并移除');

  // ============================================================
  // 用例 8：主事项行只保留「添加子事项」按钮
  // ============================================================
  console.log('\n【用例8】主事项行的子事项入口');
  const MAIN_ROW = {
    card_id: 'P1', card_name: '主事项A', parent_id: '', board_id: 'B1',
    status: 'open', owner: '王伟娜', begin: '', due: '', description: '',
    pinned: 0, created: '2026-10-28 07:00:00', locked_by: null, sub_count: 3,
  };
  const rowHtml = sandbox.cardItem(MAIN_ROW);
  ok(rowHtml.includes('＋ 子事项'), '行内显示「＋ 子事项」');
  ok(!/子事项\s*\d/.test(rowHtml), '行内不再显示「子事项 N」计数按钮');
  ok(rowHtml.includes('openNewSubModal'), '「＋ 子事项」直接打开新建子事项弹窗（不再经过右侧抽屉）');
  ok(!rowHtml.includes('openDrawer'), '「＋ 子事项」不再打开右侧抽屉');
  ok(rowHtml.includes('item-chev'), '已有子事项时仍保留左侧展开箭头（目录查看入口不丢）');

  // 只读账号不应看到「添加子事项」
  setVar('ME', { can_edit: false, is_admin: false, username: 'viewer', role: 'viewer', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const viewerRow = sandbox.cardItem(MAIN_ROW);
  ok(!viewerRow.includes('＋ 子事项'), '只读账号不显示「＋ 子事项」');

  // 成本看板：非管理员同样不显示（与「编辑」按钮口径一致）
  setVar('ME', { can_edit: true, is_admin: false, username: 'editor', role: 'editor', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const costRow = sandbox.cardItem({ ...MAIN_ROW, board_id: '1162069797001000241' });
  ok(!costRow.includes('＋ 子事项'), '成本看板非管理员不显示「＋ 子事项」');
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const adminCostRow = sandbox.cardItem({ ...MAIN_ROW, board_id: '1162069797001000241' });
  ok(adminCostRow.includes('＋ 子事项'), '成本看板管理员可见「＋ 子事项」');

  // ============================================================
  // 用例 9：序号展示 / 负责人位置 / 编辑入口移入详情弹窗
  // ============================================================
  console.log('\n【用例9】序号、负责人位置与编辑入口');
  const seqRow = sandbox.cardItem({ ...MAIN_ROW, owner: '王伟娜' }, 3);
  ok(seqRow.includes('item-seq'), '行首渲染顺序序号');
  ok(/class="item-seq[^"]*"[^>]*>3</.test(seqRow), '序号取渲染时传入的序号值');
  ok(seqRow.indexOf('item-seq') < seqRow.indexOf('item-title'), '序号在标题之前（列表最前方只保留序号）');
  ok(seqRow.indexOf('item-title') < seqRow.indexOf('fcol-owner'), '负责人紧跟在标题之后');
  ok(seqRow.includes('王伟娜'), '负责人姓名已显示在行内');
  ok(!seqRow.includes('owner-avatar'), '行首不再显示负责人头像');
  ok(!seqRow.includes('openEdit('), '列表行不再有直接编辑入口');
  ok(typeof sandbox.openDetailEdit === 'function', '详情弹窗提供编辑入口函数');
  ok(typeof sandbox.renderDetailOps === 'function', '详情弹窗渲染操作区（编辑/置顶/完成）');

  // ============================================================
  // 用例 10：置顶改为个人级设置
  // ============================================================
  console.log('\n【用例10】置顶的个人级属性');
  let pinEndpointCalls = 0;
  sandbox.api = async (p) => {
    if (String(p).includes('/pin')) pinEndpointCalls++;
    return { ok: true, cards: [], columns: [] };
  };
  await sandbox.toggleCardPin('NCX', true, false);
  ok(pinEndpointCalls === 0, '置顶不再调用服务端 /pin 接口（纯个人设置）');
  ok(sandbox.isPinned('card', 'NCX'), '置顶状态记录在当前账号的个人设置里');
  await sandbox.toggleCardPin('NCX', false, false);
  ok(!sandbox.isPinned('card', 'NCX'), '取消置顶同样只改个人设置');
  sandbox.setPinned('column', 'B1::X', true);
  ok(sandbox.isPinned('column', 'B1::X'), '板块置顶也是个人设置');

  // 排序只看个人置顶，服务端共享的 pinned 不再影响
  sandbox.setPinned('card', 'C2', true);
  const arr1 = [
    { card_id: 'C1', pinned: 1, created: '2026-01-02 00:00:00' },
    { card_id: 'C2', pinned: 0, created: '2026-01-01 00:00:00' },
  ];
  arr1.sort(sandbox.cmpCard);
  ok(arr1[0].card_id === 'C2', '个人置顶的事项排在最前');
  const arr2 = [
    { card_id: 'C1', pinned: 1, created: '2026-01-02 00:00:00' },
    { card_id: 'C2', pinned: 0, created: '2026-01-01 00:00:00' },
  ];
  sandbox.setPinned('card', 'C2', false);
  arr2.sort(sandbox.cmpCard);
  ok(arr2[0].card_id === 'C1', '服务端共享的 pinned 不再影响排序（按创建时间降序，新的在前）');

  // ============================================================
  // 用例 11：布局对调 / 板块编辑界面 / 归属年份 / 折叠交互
  // ============================================================
  console.log('\n【用例11】布局对调与板块编辑交互');
  const fs2 = require('fs');
  const path2 = require('path');
  const htmlSrc = fs2.readFileSync(path2.join(__dirname, '..', 'src', 'static', 'index.html'), 'utf8');
  const iProg = htmlSrc.indexOf('id="progressOverview"');
  const iTool = htmlSrc.indexOf('class="toolbar"');
  ok(iProg > 0 && iTool > 0 && iProg < iTool, '进度概览已排到工具栏之前（上下位置对调）');
  ok(/class="chev" onclick="toggleWeek\(/.test(htmlSrc), '三角图标绑定折叠切换');
  ok(/openColumnEdit\(this\)/.test(htmlSrc), '板块标题点击打开编辑弹窗');
  ok(!/class="week-header" onclick=/.test(htmlSrc), '板块标题栏本身不再绑定折叠切换');
  ok(/data-colkey=/.test(htmlSrc), '板块标题携带 data-* 用于回显');
  ok(/id="c_year"/.test(htmlSrc), '板块表单含「归属年份」字段');

  // 编辑模式：回显 + 字段裁剪
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const fakeEl = {
    dataset: { colkey: 'B1::X', bid: 'B1', cname: '测试板块', year: '2026', nature: '专项', created: '2026-08-13 10:00:00', creator: '王伟娜' },
  };
  sandbox.openColumnEdit(fakeEl);
  eq(getEl('c_name').value, '测试板块', '编辑时板块名称已回显');
  eq(getEl('c_year').value, '2026', '编辑时归属年份已回显');
  eq(getEl('c_created').value, '2026-08-13', '编辑时创建日期已回显');
  eq(getEl('c_creator').value, '王伟娜', '编辑时创建人已回显');
  eq(getEl('c_board_wrap').style.display, 'none', '编辑模式下所属看板不可改');
  eq(getEl('c_submit').textContent, '保存', '编辑模式主按钮为「保存」');

  // 保存：请求体带上归属年份与原 col_key
  let putPayload = null;
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'PUT') { putPayload = JSON.parse(opt.body); return { ok: true }; }
    if (String(p).indexOf('/api/overview') >= 0) return { total: 0, done: 0, progressing: 0, open: 0, boards: [], owners: [] };
    return { ok: true, cards: [], columns: [] };
  };
  await sandbox.saveColumn();
  ok(putPayload && putPayload.year === '2026', '保存请求带上归属年份');
  ok(putPayload && putPayload.col_key === 'B1::X', '保存请求带上原 col_key（用于定位板块）');
  ok(putPayload && putPayload.column_name === '测试板块', '保存请求带上板块名称');

  // 新建模式：字段与默认值
  sandbox.openColumnModal();
  eq(getEl('c_year').value, String(new Date().getFullYear()), '新建时归属年份默认当年');
  eq(getEl('c_submit').textContent, '创建板块', '新建模式主按钮为「创建板块」');
  eq(getEl('c_board_wrap').style.display, '', '新建模式可选择所属看板');

  // ============================================================
  // 用例 12：锁图标按权限显示 / 年份筛选器 / 归属年份默认
  // ============================================================
  console.log('\n【用例12】锁图标、归属年份默认与年份筛选');
  const COST = { board_id: '1162069797001000241', board_name: '成本工作事项（2026年度）' };
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [COST], depts: [] });
  const adminTab = sandbox.boardTabHtml(COST, '核算部');
  ok(!adminTab.includes('🔒'), '管理员看不到成本看板的锁（对其确无实际限制）');
  setVar('ME', { can_edit: true, is_admin: false, username: 'scj', role: 'editor', boards: [COST], depts: [] });
  const editorTab = sandbox.boardTabHtml(COST, '核算部');
  ok(editorTab.includes('🔒'), '非管理员仍看到锁（限制对其确实生效）');
  ok(editorTab.includes('仅管理员可编辑'), '锁带说明含义的提示文字');
  const normalTab = sandbox.boardTabHtml({ board_id: 'B1', board_name: '综合工作事项' }, '核算部');
  ok(!normalTab.includes('🔒'), '普通看板没有锁');

  // 归属年份默认 = 创建年份（新建时跟随创建日期）
  sandbox.openColumnModal();
  eq(getEl('c_year').value, getEl('c_created').value.slice(0, 4), '新建时归属年份默认取创建日期的年份');
  getEl('c_created').value = '2025-03-08';
  sandbox.syncYearFromDate();
  eq(getEl('c_year').value, '2025', '改创建日期后归属年份自动跟随');
  getEl('c_year').value = '2027';
  getEl('c_year').dispatchEvent && null;
  sandbox.YEAR_TOUCHED = true;
  getEl('c_created').value = '2026-01-01';
  sandbox.syncYearFromDate();
  eq(getEl('c_year').value, '2027', '用户手动改过归属年份后不再被创建日期覆盖');

  // 年份筛选器（多选）：chips 标签组
  const COLS = [
    { column_name: '板块A', year: '2026', col_key: 'B::板块A', board_id: 'B', card_count: 2, done_count: 1, created_at: '2026-01-01', creator: 'x', nature: '日常' },
    { column_name: '板块B', year: '2025', col_key: 'B::板块B', board_id: 'B', card_count: 1, done_count: 0, created_at: '2025-01-01', creator: 'x', nature: '日常' },
    { column_name: '板块C', year: '2026', col_key: 'B::板块C', board_id: 'B', card_count: 0, done_count: 0, created_at: '2026-02-01', creator: 'x', nature: '日常' },
  ];
  const CARDS = [
    { card_id: 'C1', card_name: '事项1', column_name: '板块A', owner: '王伟娜', status: 'open', created: '2026-01-01', due: '', pinned: 0, sub_count: 0, subtask_total: 0, subtask_done: 0, board_id: 'B', locked_by: null },
    { card_id: 'C2', card_name: '事项2', column_name: '板块B', owner: '王伟娜', status: 'open', created: '2025-01-01', due: '', pinned: 0, sub_count: 0, subtask_total: 0, subtask_done: 0, board_id: 'B', locked_by: null },
  ];
  // 多选状态：用 Set 表达已选年份集合（空 = 全部年份）
  setLetSet('curYears', []);
  sandbox.renderYearFilter(COLS);
  const opts = getEl('yearFilter').innerHTML;
  ok(opts.includes('全部年份'), '年份筛选器含「全部年份」（= 清空全部）');
  ok(opts.includes('全部年份'), '未选年份时仅显示「全部年份」入口');
  // 未选年份时：没有年份 chip，但有「＋ 年份」与「全部年份」两个入口
  ok((opts.match(/data-year=/g) || []).length === 0, '未选年份时不渲染年份 chip');
  ok(opts.includes('data-add="1"'), '未选年份时仍提供「＋ 年份」选择入口');
  ok(opts.includes('data-all="1"'), '未选年份时仍提供「全部年份」入口');

  // 选中两个年份 → 两个 chip，且都能单独移除
  setLetSet('curYears', ["2025","2026"]);
  sandbox.renderYearFilter(COLS);
  const chips = getEl('yearFilter').innerHTML;
  ok((chips.match(/class="year-chip"/g) || []).length === 2, '同时选中两个年份 → 渲染两个 chip');
  ok(chips.includes('2026') && chips.includes('2025'), '已选年份在筛选器里可见');
  ok(chips.includes('data-year="2025"') && chips.includes('data-year="2026"'), '每个 chip 带自己的年份标识');
  ok((chips.match(/class="yc-x"/g) || []).length === 2, '每个已选年份都有独立的 ✕ 移除入口');

  // 按多选年份筛选板块
  setLetSet('curYears', ["2025"]);
  sandbox.renderBoard(CARDS, COLS, '', []);
  const filtered = getEl('boardContent').innerHTML;
  ok(filtered.includes('板块B'), '筛选后显示该年份的板块');
  ok(!filtered.includes('板块A'), '筛选后隐藏其它年份的板块');
  // 多选：两个年份同时生效，两个年份的板块都显示
  setLetSet('curYears', ["2025","2026"]);
  sandbox.renderBoard(CARDS, COLS, '', []);
  const multi = getEl('boardContent').innerHTML;
  ok(multi.includes('板块A') && multi.includes('板块B'), '多选时命中任一年份的板块都显示');
  // 清空全部 → 不过滤
  setLetSet('curYears', []);
  sandbox.renderBoard(CARDS, COLS, '', []);
  ok(getEl('boardContent').innerHTML.includes('板块A'), '取消筛选后恢复全部板块');

  // 已选年份在新看板不存在 → 先回落到当前年份，当前年份也没有则退回「全部年份」
  setLetSet('curYears', ["2025"]);
  sandbox.renderYearFilter([{ column_name: '只有2026', year: '2026' }]);
  eq(getLetSet('curYears').join(','), String(new Date().getFullYear()),
     '年份在新看板不存在时回落到当前年份');
  setLetSet('curYears', ["2025"]);
  sandbox.renderYearFilter([{ column_name: '只有2027', year: '2027' }]);
  eq(getLetSet('curYears').join(','), '',
     '当前年份也不存在时重置为全部年份');

  // ============================================================
  // 用例 13：默认当前年份 / 按钮文案 / 负责人前缀 / 圆点配色 / 父事项责任人
  // ============================================================
  console.log('\n【用例13】年份默认值、按钮文案、负责人前缀与圆点配色');

  // 1) 年份默认落在当前年份
  const yNow = String(new Date().getFullYear());
  eq(getLet('YEAR_DEFAULT'), yNow, '年份默认值 = 当前年份');
  setLetSet('curYears', [yNow]);
  sandbox.renderYearFilter(COLS);
  ok(getEl('yearFilter').innerHTML.includes('data-year="' + yNow + '"'), '默认选中当前年份（渲染成 chip）');

  // 切换看板统一重置回当前年份
  setLetSet('curYears', ["2025"]);
  await sandbox.pickBoard('B1');
  eq(getLetSet('curYears').join(','), yNow, '切换看板后年份重置为当前年份');

  // 2) 行内子事项入口文案
  const subBtnRow = sandbox.cardItem({
    card_id: 'C9', card_name: '带子事项的事项', column_name: '板块A', owner: '王伟娜',
    status: 'open', created: '2026-01-01', due: '', pinned: 0, sub_count: 2,
    subtask_total: 0, subtask_done: 0, board_id: 'B1', locked_by: null,
  }, 1);
  ok(subBtnRow.includes('＋ 子事项'), '行内按钮文案为「＋ 子事项」');
  ok(!subBtnRow.includes('添加子事项'), '旧的「＋ 添加子事项」文案已移除');

  // 3) 负责人前缀（主事项行 + 子事项目录行）
  ok(subBtnRow.includes('负责人：王伟娜'), '主事项行的负责人带「负责人：」前缀');
  const subHtml = sandbox.subNodeHtml({ card_id: 'S1', card_name: '子事项', owner: '吴婷婷', status: 'open', created: '2026-10-17 16:25:00', due: '2026-10-24', children: [] }, 0);
  ok(subHtml.includes('负责人：吴婷婷'), '子事项目录行的负责人带「负责人：」前缀');
  ok(!/👤/.test(subHtml), '子事项行不再使用 👤 图标前缀');

  // 4) 圆点配色统一为品牌金 #CCB484
  ok(htmlSrc.includes('--gold:#CCB484'), '品牌金变量为 #CCB484');
  ok(/\.s-dot\{[^}]*background:var\(--gold\)/.test(htmlSrc), '子事项圆点统一用品牌金');
  ok(!subHtml.includes('avatarColor'), '子事项圆点不再按负责人姓名哈希颜色');

  // 5) 父事项负责人：独立取值，不与子事项关联
  const noOwnerRow = sandbox.cardItem({
    card_id: 'C10', card_name: '父事项', column_name: '板块A', owner: '',
    status: 'open', created: '2026-01-01', due: '', pinned: 0, sub_count: 2,
    subtask_total: 0, subtask_done: 0, board_id: 'B1', locked_by: null,
    sub_owners: ['何巧娴', '吴婷婷'],
  }, 1);
  ok(noOwnerRow.includes('负责人：—'), '父事项自身无负责人时占位为「负责人：—」');
  ok(!noOwnerRow.includes('何巧娴') && !noOwnerRow.includes('吴婷婷'),
    '父事项负责人不关联子事项负责人（不做继承/汇总）');
  const selfOwnerRow = sandbox.cardItem({
    card_id: 'C11', card_name: '父事项2', column_name: '板块A', owner: '王伟娜',
    status: 'open', created: '2026-01-01', due: '', pinned: 0, sub_count: 2,
    subtask_total: 0, subtask_done: 0, board_id: 'B1', locked_by: null,
    sub_owners: ['何巧娴'],
  }, 1);
  ok(selfOwnerRow.includes('负责人：王伟娜') && !selfOwnerRow.includes('何巧娴'), '父事项只显示自己独立设置的负责人');

  // ============================================================
  // 用例 14：字段名 / 列对齐 / 父子字段一致 / 负责人独立
  // ============================================================
  console.log('\n【用例14】创建日期、字段列对齐与父子字段一致');

  // 1) 「创建时间」→「创建日期」，只显示年月日
  eq(sandbox.fmtDate('2026-05-21 10:52:33'), '2026-05-21', '创建时间裁成创建日期（去时分秒）');
  eq(sandbox.fmtDate('2026-05-21'), '2026-05-21', '纯日期原样返回');
  eq(sandbox.fmtDate('2026-5-1'), '2026-05-01', '单位补零');
  eq(sandbox.fmtDate(''), '', '空值返回空串');

  const datedRow = sandbox.cardItem({
    card_id: 'C20', card_name: '带日期的事项', column_name: '板块A', owner: '王伟娜',
    status: 'open', created: '2026-05-21 10:52:33', due: '2026-04-30',
    pinned: 0, sub_count: 0, subtask_total: 0, subtask_done: 0, board_id: 'B1', locked_by: null,
  }, 1);
  ok(datedRow.includes('创建日期：2026-05-21'), '行内显示「创建日期：2026-05-21」');
  ok(!datedRow.includes('10:52'), '行内不再显示时分秒');
  ok(datedRow.includes('截止日期：2026-04-30'), '行内显示「截止日期：2026-04-30」');
  ok(!datedRow.includes('创建时间'), '不再出现「创建时间」字样');

  // 2) 三列等宽对齐：用 grid 定宽，空值占位与截止日期一致
  ok(/\.fcols\{[^}]*display:grid/.test(htmlSrc), '字段列使用 grid 布局（定宽对齐）');
  ok(/\.fcols\{[^}]*grid-template-columns:[^;]*\d+px[^;]*\d+px[^;]*\d+px/.test(htmlSrc), '字段列为三列定宽');
  const emptyOwnerRow = sandbox.cardItem({
    card_id: 'C21', card_name: '无负责人的事项', column_name: '板块A', owner: '',
    status: 'open', created: '2026-05-21 10:52:33', due: '', pinned: 0, sub_count: 0,
    subtask_total: 0, subtask_done: 0, board_id: 'B1', locked_by: null,
  }, 1);
  ok(emptyOwnerRow.includes('负责人：—'), '负责人为空时占位为「负责人：—」');
  ok(emptyOwnerRow.includes('截止日期：—'), '截止日期为空时占位为「截止日期：—」');
  ok(emptyOwnerRow.includes('fcol-owner fcol-empty') && emptyOwnerRow.includes('fcol-due fcol-empty'),
    '负责人与截止日期的空值用同一套 fcol-empty 占位样式');
  // 「empty」是全局占位类（.empty{padding:48px}），子元素类名必须避开，否则行高被撑爆
  ok(!/class="fcol[^"]*[^"]\bempty\b/.test(emptyOwnerRow.replace(/fcol-empty/g, '')),
    '字段列的空值类名避开全局 .empty（防止误加 padding 撑高行）');
  ok(/\.fcol-empty\{/.test(htmlSrc), '空值占位样式用 .fcol-empty 前缀');
  // 回归防护：子元素类名不得与全局单类选择器同名（如 .empty{padding:48px} 会把行高撑爆）
  // 用渲染结果里的精确类名 token 匹配（\b 边界，避免 fcol-empty 被误判）
  const fcolClassTokens = new Set();
  for (const htmlStr of [datedRow, emptyOwnerRow, subHtml]) {
    const re = /class="([^"]*)"/g; let m;
    while ((m = re.exec(htmlStr)) !== null) {
      m[1].split(/\s+/).forEach(c => { if (c.startsWith('fcol')) fcolClassTokens.add(c); });
    }
  }
  ok(![...fcolClassTokens].includes('empty'), '字段列不使用裸 .empty 类（避免误加全局 padding 撑高行）');
  ok(fcolClassTokens.has('fcol-empty'), '空值类名为 fcol-empty');
  // grid 容器必须显式给宽度，否则宽度由内容反推、窄屏下塌缩换行
  ok(/\.fcols\{[^}]*width:\d+px/.test(htmlSrc), '字段列 grid 容器显式定宽（防止窄屏塌缩换行）');
  ok(/\.fcols\{[^}]*flex:0 0/.test(htmlSrc), '字段列 flex 不压缩（flex:0 0 <width>）');

  // 6) 父子行字段列对齐：行尾槽位宽度必须与父行完全一致，
  //    且子树右边距需把子行右边界推回父行位置 → 三列起点才能相同
  const slotWidths = (cls) => {
    const m = htmlSrc.match(new RegExp('\\.' + cls + '\\{[^}]*width:(\\d+)px'));
    return m ? m[1] : null;
  };
  for (const cls of ['slot-overdue', 'slot-subtask', 'slot-status', 'slot-pin', 'slot-sub']) {
    const parent = slotWidths(cls);
    const sub = (htmlSrc.match(new RegExp('\\.sub-node \\.' + cls + '\\{[^}]*width:(\\d+)px')) || [])[1];
    ok(parent && sub && parent === sub, `${cls} 父子行宽度一致（${parent} / ${sub}）`);
  }
  // 子事项行也要渲染全部 5 个槽位（「＋子事项」那格留空）
  const subSlotRow = sandbox.subNodeHtml({
    card_id: 'S9', card_name: '槽位检查', owner: '吴婷婷', status: 'open',
    created: '2026-10-27 16:25:13', due: '', children: [],
  }, 0);
  ok(subSlotRow.includes('slot-subtask') && subSlotRow.includes('slot-sub'),
    '子事项行补齐全部固定槽位（＋子事项那格留空）');
  // 子树右边距：把缩进造成的右侧偏移推回来，使父子右边界一致
  ok(/\.sub-tree\{[^}]*margin:0 8px/.test(htmlSrc),
    '子树右边距已标定为 8px（使父子行右边界一致 → 字段列对齐）');
  ok(!/\.sub-tree\{[^}]*margin:0 -/.test(htmlSrc),
    '子树不再使用负右边距（会导致字段列整体右移）');

  // 3) 子事项字段集合与顺序与父事项一致
  const parentFields = (html) => (html.match(/fcol-(owner|created|due)/g) || []);
  const parentOrder = parentFields(datedRow);
  const childOrder = parentFields(subHtml);
  ok(parentOrder.join(',') === 'fcol-owner,fcol-created,fcol-due', '父事项字段顺序 = 负责人/创建日期/截止日期');
  ok(childOrder.join(',') === 'fcol-owner,fcol-created,fcol-due', '子事项字段顺序与父事项一致');
  ok(childOrder.join(',') === parentOrder.join(','), '父子字段集合与顺序完全一致');
  const subWithDate = sandbox.subNodeHtml({
    card_id: 'S2', card_name: '带日期的子项', owner: '吴婷婷', status: 'open',
    created: '2026-10-27 16:25:13', due: '2026-10-24', children: [],
  }, 0);
  ok(subWithDate.includes('创建日期：2026-10-27'), '子事项显示「创建日期：2026-10-27」');
  ok(!subWithDate.includes('16:25'), '子事项不再显示时分秒');

  // 4) 负责人独立：子事项不继承父事项负责人
  const childOwner = sandbox.subNodeHtml({
    card_id: 'S3', card_name: '独立负责人的子项', owner: '吴婷婷', status: 'open',
    created: '2026-10-27 16:25:13', due: '', children: [],
  }, 0);
  ok(childOwner.includes('负责人：吴婷婷'), '子事项显示自己的负责人');
  ok(!childOwner.includes('王伟娜'), '子事项不继承父事项负责人');
  ok(!htmlSrc.includes('sub_owners'), '后端/前端都不再汇总子事项负责人');

  // 5) 列对齐机制：三列定宽 + 行尾可选元素用定宽槽位 → 跨行起点一致
  ok(/\.fcols\{[^}]*display:grid/.test(htmlSrc)
    && /grid-template-columns:\d+px \d+px \d+px/.test(htmlSrc),
    '字段列为 grid 三列定宽');
  ok(/\.item-tail\{[^}]*margin-left:auto/.test(htmlSrc), '行尾区块整体右对齐（锚定行尾）');
  ok(/\.sub-tail\{[^}]*margin-left:auto/.test(htmlSrc), '子事项行尾区块整体右对齐');
  // 逾期 / 代办 / 状态 / 置顶 / 子事项 五个可选元素都要有定宽槽位
  for (const cls of ['slot-overdue', 'slot-subtask', 'slot-status', 'slot-pin', 'slot-sub']) {
    ok(new RegExp('\\.' + cls + '\\{[^}]*width:\\d+px').test(htmlSrc), `${cls} 槽位有固定宽度`);
  }
  // 每行都要渲染这几个槽位（无论内容有无）→ 行内结构恒定
  ok(datedRow.includes('slot-overdue') && datedRow.includes('slot-subtask')
    && datedRow.includes('slot-status') && datedRow.includes('slot-pin') && datedRow.includes('slot-sub'),
    '主事项行渲染全部固定槽位（有/无内容都占位）');
  ok(subWithDate.includes('slot-overdue') && subWithDate.includes('slot-status') && subWithDate.includes('slot-pin'),
    '子事项行渲染全部固定槽位');

  // ============================================================
  // 用例 7：详情弹窗的状态按钮（状态唯一呈现 + 唯一设置入口）与置顶按钮移除
  // ============================================================
  console.log('\n【用例7】详情弹窗的状态按钮与置顶按钮移除');
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });

  // 1) 弹窗内的置顶入口已移除（列表行的置顶仍保留）
  ok(!/detailTogglePin/.test(html), '弹窗内的置顶入口已移除（detailTogglePin 已删除）');
  ok(!/done-btn/.test(html), '旧的 done-btn（无样式定义、渲染成浏览器默认按钮）已移除');

  // 2) 状态按钮：当前状态的唯一呈现
  sandbox.renderDetailOps({ card_id: 'C1', status: 'progressing', locked_by: null });
  const opsHtml = getEl('d_ops').innerHTML;
  ok(opsHtml.includes('status-btn progressing'), '状态按钮按当前状态渲染（进行中）');
  ok(opsHtml.includes('status-menu'), '状态按钮带可展开的状态菜单');
  ok(opsHtml.includes('d_status_picker'), '详情弹窗的状态按钮容器 id 正确');
  ok(!opsHtml.includes('pin-btn'), '弹窗操作区不再包含置顶按钮（列表行的置顶不受影响）');
  ok(/📌 事项置顶/.test(html), '列表行的置顶按钮仍保留（未受影响）');
  ok(opsHtml.includes('✏️ 编辑'), '编辑入口仍在');
  ok(opsHtml.includes('未完成') && opsHtml.includes('进行中') && opsHtml.includes('已完成'),
    '状态菜单三项齐全（未完成 / 进行中 / 已完成）');
  ok(opsHtml.includes('cur'), '菜单里当前状态被标记');

  // 3) 菜单的展开与收起
  const dMenu = getEl('d_status_menu');
  dMenu.hidden = true;
  sandbox.toggleStatusMenu({ stopPropagation() {} }, 'd');
  eq(dMenu.hidden, false, '点击后状态菜单展开');
  sandbox.toggleStatusMenu({ stopPropagation() {} }, 'd');
  eq(dMenu.hidden, true, '再次点击后状态菜单收起');

  // 4) 设置状态：提交正确的 status + status_name
  let putBody = null;
  sandbox.api = async (p, opt) => {
    if (opt && opt.method === 'PUT') { putBody = JSON.parse(opt.body); return { ok: true }; }
    return { cards: [{ card_id: 'C1', status: 'done', card_name: 'x', board_name: 'B', column_name: 'C' }],
             columns: [], column_hits: [], subtasks: [], comments: [], actions: [] };
  };
  setLet('DETAIL_ID', 'C1');
  await sandbox.setCardStatus('d', 'done');
  ok(putBody && putBody.fields && putBody.fields.status === 'done', '设置状态提交 status=done');
  eq(putBody && putBody.fields.status_name, '已完成', '同时提交对应的状态文案');

  // 5) 状态不在元信息里重复出现；编辑弹窗的状态控件收敛到头部
  ok(!/状态：<b>/.test(html), '详情弹窗元信息不再单独渲染「状态：」字段');
  ok(/id="e_status_ops"/.test(html), '编辑弹窗头部有状态按钮容器');
  ok(!/id="e_status_group"/.test(html), '编辑弹窗表单内的状态控件已删除');
  ok(!/id="e_status_row"/.test(html), '原 e_status_row 已改名为 e_meta_row');
  ok(/id="e_meta_row"/.test(html), 'e_meta_row 承接原状态行（所属看板 + 子事项模式负责人搬移）');

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常:', e); process.exit(1); });
