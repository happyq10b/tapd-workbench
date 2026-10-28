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

// ============================================================
// 用例 1：创建子事项失败 → 表单必须被重置（负责人等脏数据不得残留）
// ============================================================
(async () => {
  console.log('\n【用例1】创建失败后的表单重置');
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  setVar('TEAM_MEMBERS', ['王伟娜', '张三', '李四']);
  sandbox.DRAWER_STACK = [{ type: 'list', cardId: 'P1' }];
  sandbox.DRAWER_OWNER = ['王伟娜', '张三'];
  sandbox.DRAWER_NEW_UNDER = null;

  getEl('dn_name').value = '要创建的子事项';
  getEl('dn_desc').value = '描述残留';
  getEl('dn_begin').value = '2026-01-01';
  getEl('dn_due').value = '2026-02-01';
  getEl('dn_status').value = 'done';

  let called = 0;
  sandbox.api = async () => { called++; throw new Error('模拟创建失败：父事项已完成'); };

  await sandbox.createDrawerSub();

  eq(called, 1, '确实发起了创建请求');
  eq(sandbox.DRAWER_OWNER.length, 0, '负责人已清空（DRAWER_OWNER）');
  eq(getEl('dn_name').value, '', '标题已清空');
  eq(getEl('dn_desc').value, '', '描述已清空');
  eq(getEl('dn_begin').value, '', '开始日期已清空');
  eq(getEl('dn_due').value, '', '截止日期已清空');
  eq(getEl('dn_status').value, 'open', '状态已回到默认「未完成」');
  // 选择器是否重绑到空数组：PP['dn_owner'].arr 必须与 DRAWER_OWNER 一致且为空
  ok(sandbox.PP && sandbox.PP['dn_owner'], '负责人选择器已重新初始化');
  eq(sandbox.PP['dn_owner'].arr.length, 0, '选择器绑定的数组为空（界面上不会残留已选成员）');
  ok(sandbox.PP['dn_owner'].arr === sandbox.DRAWER_OWNER, '选择器与 DRAWER_OWNER 指向同一数组');

  // ============================================================
  // 用例 2：创建成功 → 字段同样正常清空
  // ============================================================
  console.log('\n【用例2】创建成功后的表单清空');
  sandbox.DRAWER_OWNER = ['李四'];
  getEl('dn_name').value = '成功创建的子事项';
  getEl('dn_desc').value = '描述';
  getEl('dn_status').value = 'progressing';
  sandbox.api = async () => ({ ok: true, card_id: 'NC999' });
  // renderDrawerList 会发起多次请求，这里统一返回空结构避免干扰
  sandbox.api = async (p) => {
    if (String(p).startsWith('/api/cards?')) return { cards: [], columns: [] };
    if (String(p).endsWith('/children')) return { children: [], total: 0 };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    return { ok: true };
  };
  await sandbox.createDrawerSub();
  eq(sandbox.DRAWER_OWNER.length, 0, '成功后负责人已清空');
  eq(getEl('dn_status').value, 'open', '成功后状态已回到默认');

  // ============================================================
  // 用例 3：目录点击子事项 → 打开子事项弹窗（字段裁剪 + 父事项约束）
  // ============================================================
  console.log('\n【用例3】目录点击打开子事项弹窗');
  const SUB = {
    card_id: 'NC1', card_name: '子事项A', parent_id: 'P1', board_id: 'B1',
    status: 'progressing', owner: '王伟娜', cc: '张三', begin: '2026-03-02', due: '2026-03-20',
    description: '子事项描述', pinned: 0, created: '2026-10-28 08:00:00', locked_by: null,
  };
  const PARENT = {
    card_id: 'P1', card_name: '父事项A', parent_id: '', board_id: 'B1',
    status: 'open', owner: '王伟娜', begin: '2026-03-01', due: '2026-03-31',
    description: '', pinned: 0, created: '2026-10-28 07:00:00', locked_by: null,
  };
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=NC1')) return { cards: [SUB], columns: [] };
    if (String(p).includes('card_id=P1')) return { cards: [PARENT], columns: [] };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    return { cards: [], columns: [] };
  };
  sandbox.lockCard = async () => true;
  getEl('editModal').style.display = 'none';

  await sandbox.openSubModal('NC1');

  eq(getEl('editModal').style.display, 'flex', '子事项弹窗已打开');
  eq(getEl('editTitle').textContent, '编辑子事项', '标题为「编辑子事项」');
  eq(getEl('e_board_wrap').style.display, 'none', '「所属看板」已隐藏（子事项继承父看板）');
  eq(getEl('e_cc_wrap').style.display, 'none', '「参与人」已隐藏（子事项无参与人）');
  eq(getEl('e_parent_wrap').style.display, '', '父事项信息区已展示');
  ok(String(getEl('e_parent_info').innerHTML).includes('父事项A'), '父事项信息含父事项名称');
  eq(getEl('e_begin').getAttribute('min'), '2026-03-01', '开始日期受父事项起始约束(min)');
  eq(getEl('e_due').getAttribute('max'), '2026-03-31', '截止日期受父事项截止约束(max)');
  eq(getEl('e_name').value, '子事项A', '标题已回填');
  eq(getEl('e_status').value, 'progressing', '状态已回填');
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
  ok(saved.fields.cc === undefined, '保存子事项时不发送参与人字段');
  eq(saved.fields.status, 'progressing', '保存的状态正确');
  eq(saved.fields.owner, '王伟娜', '保存的负责人正确');
  eq(saved.fields.status_name, '进行中', '保存的状态文案正确');

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

  const drawerHtml = sandbox.drawerSubTree([{ ...SUB, pinned: 0, status: 'open' }], 'P1', 0);
  ok(drawerHtml.includes('toggleCardPin'), '抽屉行含置顶按钮');
  ok(drawerHtml.includes('toggleCardDone'), '抽屉行状态标签可切换完成状态');
  ok(drawerHtml.includes('openSubModal'), '抽屉行编辑按钮打开子事项弹窗');
  ok(drawerHtml.includes('＋下级'), '抽屉行保留「＋下级」');
  ok(drawerHtml.includes('delDrawerSub'), '抽屉行保留「删除」');
  ok(!/done-btn|doneBtn/.test(drawerHtml), '抽屉行已移除冗余的「完成」按钮');

  // 状态标签的点击必须冒泡阻断，不能连带触发所在行的「打开弹窗」
  ok(treeHtml.includes('event.stopPropagation()'), '状态标签点击不触发所在行的打开动作');

  // ============================================================
  // 用例 5：抽屉右侧面板的完整渲染
  // ============================================================
  sandbox.api = async (p) => {
    if (String(p).includes('card_id=P1')) return { cards: [PARENT], columns: [] };
    if (String(p).endsWith('/children')) return { children: [{ ...SUB, pinned: 1, status: 'done', children: [] }], total: 1 };
    if (String(p).endsWith('/subtasks')) return { subtasks: [], flat: [], total: 0, done: 0 };
    return { cards: [], columns: [] };
  };
  sandbox.DRAWER_STACK = [{ type: 'list', cardId: 'P1' }];
  await sandbox.renderDrawerList('P1');
  const drawerHtml2 = getEl('drawerBody').innerHTML;
  ok(drawerHtml2.includes('toggleCardPin'), '抽屉主事项卡含置顶按钮');
  ok(drawerHtml2.includes('toggleCardDone'), '抽屉主事项卡的状态标签可切换完成状态');
  ok(!/done-btn|doneBtn/.test(drawerHtml2), '抽屉主事项卡也已移除冗余的「完成」按钮');
  ok(drawerHtml2.includes('openEdit'), '抽屉主事项卡含编辑入口');
  ok(drawerHtml2.includes('dn_owner'), '新建子事项表单含负责人选择器');
  ok(drawerHtml2.includes('子事项目录'), '抽屉含子事项目录区块');
  ok(drawerHtml2.includes('代办清单') === false, '无代办时不展示代办清单');

  // ============================================================
  // 用例 6：「负责人」在子事项模式搬到状态右侧同一行，并标注选填
  // ============================================================
  console.log('\n【用例6】负责人字段的选填与位置');
  // 先开一次子事项弹窗（用例3已建立 API stub）
  await sandbox.openSubModal('NC1');
  const ownerGroup = getEl('e_owner_group');
  const statusRow = getEl('e_status_row');
  const ownerRow = getEl('e_owner_row');
  ok(ownerGroup.parentNode === statusRow, '负责人已搬到「状态」所在行（与状态并列）');
  ok(ownerRow.style.display === 'none', '原来的「负责人/参与人」行已收起（不占位、不错位）');
  eq(getEl('e_owner_opt').style.display, '', '负责人已标注「（选填）」');
  ok(statusRow._kids.includes(ownerGroup), '负责人确实是状态行的子节点（网格第 2 列）');

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
  ok(getEl('drawerBody')._rippleBound === true, '抽屉容器已绑定涟漪反馈');

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
  ok(rowHtml.includes('添加子事项'), '行内显示「添加子事项」');
  ok(!/子事项\s*\d/.test(rowHtml), '行内不再显示「子事项 N」计数按钮');
  ok(rowHtml.includes('openDrawer'), '「添加子事项」仍打开右侧抽屉（新增流程不变）');
  ok(rowHtml.includes('item-chev'), '已有子事项时仍保留左侧展开箭头（目录查看入口不丢）');

  // 只读账号不应看到「添加子事项」
  setVar('ME', { can_edit: false, is_admin: false, username: 'viewer', role: 'viewer', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const viewerRow = sandbox.cardItem(MAIN_ROW);
  ok(!viewerRow.includes('添加子事项'), '只读账号不显示「添加子事项」');

  // 成本看板：非管理员同样不显示（与「编辑」按钮口径一致）
  setVar('ME', { can_edit: true, is_admin: false, username: 'editor', role: 'editor', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const costRow = sandbox.cardItem({ ...MAIN_ROW, board_id: '1162069797001000241' });
  ok(!costRow.includes('添加子事项'), '成本看板非管理员不显示「添加子事项」');
  setVar('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin', boards: [{ board_id: 'B1', board_name: '看板1' }] });
  const adminCostRow = sandbox.cardItem({ ...MAIN_ROW, board_id: '1162069797001000241' });
  ok(adminCostRow.includes('添加子事项'), '成本看板管理员可见「添加子事项」');

  // ============================================================
  // 用例 9：序号展示 / 负责人位置 / 编辑入口移入详情弹窗
  // ============================================================
  console.log('\n【用例9】序号、负责人位置与编辑入口');
  const seqRow = sandbox.cardItem({ ...MAIN_ROW, owner: '王伟娜' }, 3);
  ok(seqRow.includes('item-seq'), '行首渲染顺序序号');
  ok(/class="item-seq[^"]*"[^>]*>3</.test(seqRow), '序号取渲染时传入的序号值');
  ok(seqRow.indexOf('item-seq') < seqRow.indexOf('item-title'), '序号在标题之前（列表最前方只保留序号）');
  ok(seqRow.indexOf('item-title') < seqRow.indexOf('item-owner'), '负责人紧跟在标题之后');
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

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常:', e); process.exit(1); });
