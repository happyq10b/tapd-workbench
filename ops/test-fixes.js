// 本轮 5 项改动的功能回归测试（node vm 沙箱）
// 覆盖：① 年份「＋年份」下拉可新增选择 ② 统计区压缩为 2 张卡 + 公告栏
//       ③ 详情弹窗加宽 ④ 子事项支持参与人 ⑤ 编辑弹窗能正常打开
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const blocks = [...htmlSrc.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const main = blocks.join('\n');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}
function eq(a, b, msg) { ok(a === b, msg + `  (实际=${JSON.stringify(a)} 期望=${JSON.stringify(b)})`); }

// ---------- DOM stub ----------
const ELEMS = {};
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
    querySelector(sel) { return mkEl(id + '>' + sel); },
    querySelectorAll() { return []; },
    closest() { return null; },
    appendChild(child) { adopt(el, child); return child; },
    insertBefore(child) { adopt(el, child); return child; },
    remove() {},
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    removeAttribute(k) { delete attrs[k]; },
    setSelectionRange() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 10, height: 10, right: 10, bottom: 10 }; },
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
  addEventListener(type, fn) { (this._h = this._h || {})[type] = (this._h[type] || []).concat(fn); },
  removeEventListener() {},
  body: mkEl('body'), documentElement: mkEl('html'), activeElement: null,
};
const sandbox = {
  document, localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  location: { href: '' }, navigator: { userAgent: 'node' },
  fetch: async () => ({ status: 200, ok: true, json: async () => ({}) }),
  alert() {}, confirm: () => true,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(main, sandbox, { filename: 'index-inline.js' }); }
catch (e) { console.error('装载失败:', e); process.exit(1); }

const getEl = (id) => document.getElementById(id);
const setLet = (n, v) => vm.runInContext(`${n}=${JSON.stringify(v)};`, sandbox);
const getLet = (n) => vm.runInContext(n, sandbox);

(async () => {
  console.log('\n【用例1】年份筛选：新增选择的入口');
  setLet('ME', { can_edit: true, is_admin: true, username: 'admin', role: 'admin',
                 boards: [], depts: ['财务中心', '核算部'] });
  setLet('TEAM_MEMBERS', ['王伟娜', '吴婷婷']);

  const COLS = [{ column_name: 'A', year: '2026' }, { column_name: 'B', year: '2025' }, { column_name: 'C', year: '2024' }];
  vm.runInContext("curYears=new Set(['2026']);", sandbox);
  sandbox.renderYearFilter(COLS);
  let h = getEl('yearFilter').innerHTML;
  ok(h.includes('data-add="1"'), '提供「＋ 年份」新增选择入口');
  ok(h.includes('＋ 年份'), '「＋ 年份」按钮有可见文案');
  ok(h.includes('data-all="1"'), '保留「全部年份」清空入口');
  ok((h.match(/class="yc-x"/g) || []).length === 1, '已选年份各自带 ✕ 移除入口');

  // 展开下拉
  sandbox.toggleYearDrop();
  const drop = getEl('yearDrop');
  ok(drop.hidden === false, '点「＋ 年份」后下拉展开');
  ok(drop.innerHTML.includes('2025') && drop.innerHTML.includes('2024'), '下拉列出可选年份');
  ok(drop.innerHTML.includes('2026'), '下拉也列出已选年份（可取消）');
  ok((drop.innerHTML.match(/class="year-opt/g) || []).length === 3, '下拉列出全部 3 个可选年份');

  // 在下拉里选一个年份
  vm.runInContext("curYears=new Set(['2026']);", sandbox);
  sandbox.renderYearFilter(COLS);
  sandbox.toggleYearDrop();
  sandbox.toggleYearPick('2025');
  const years = [...vm.runInContext('curYears', sandbox)].sort();
  eq(years.join(','), '2025,2026', '在下拉里勾选可新增年份（保留原有选择）');
  ok(getEl('yearFilter').innerHTML.includes('data-year="2025"'), '新增的年份立即渲染成 chip');

  // 取消选择
  sandbox.toggleYearPick('2025');
  eq([...vm.runInContext('curYears', sandbox)].join(','), '2026', '再次点击可取消该年份');

  console.log('\n【用例2】顶部栏左右分栏（看板/板块/统计 ←→ 公告）');
  ok(/id="progressOverview"/.test(htmlSrc), '有统计容器 progressOverview');
  ok(/id="noticeBar"/.test(htmlSrc), '有公告栏容器 noticeBar');
  ok(/class="notice-bar"/.test(htmlSrc), '公告栏使用 .notice-bar 样式');
  ok(/class="topbar"/.test(htmlSrc) && /id="topbarAside"/.test(htmlSrc),
     '顶部栏为左右分栏（左=topbar-main，右=topbar-aside 公告区）');
  ok(/grid-template-columns:minmax\(0,1fr\) minmax\(300px,420px\)/.test(htmlSrc),
     '顶部栏两列：左自适应 + 右公告列固定 300~420px');
  ok(/\.topbar-main\{display:grid;grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/.test(htmlSrc),
     '左半主区为三列栅格（部门/板块/统计各占一行）');
  ok(/id="tbDepts"/.test(htmlSrc) && /id="tbBoards"/.test(htmlSrc),
     '左半拆分为「架构部门」「板块」两个带');
  ok(/function renderNoticeBar\(\)/.test(main), '提供公告栏渲染函数');
  ok(/function openNoticeModal\(\)/.test(main), '提供公告管理弹窗');
  ok(/id="noticeModal"/.test(htmlSrc), '有公告管理弹窗容器');
  ok(main.includes("api('/api/notices')"), '公告通过 /api/notices 接口读写');
  // 统计带：4 张卡片（总事项 / 已完成 / 进行中 / 未完成）—— 2026-11-04 增「进行中」
  const renderSrc = main.match(/async function renderProgress\(\)\{[\s\S]*?\n\}/)[0];
  ok(/ov\.progressing/.test(renderSrc) && /stat-click/.test(renderSrc),
     '统计带为 4 张卡片（总事项/已完成/进行中/未完成，3 张可点击）');
  // 紧凑样式
  ok(/\.stat-value\{font-size:20px/.test(htmlSrc), '统计数字字号已压缩（26px → 20px）');
  ok(/\.stat-card\{[^}]*padding:8px 14px/.test(htmlSrc), '统计卡片内边距已压缩');

  console.log('\n【用例3】详情弹窗加宽');
  ok(/id="detailModal"[^>]*>\s*<div class="modal modal-wide">/.test(htmlSrc), '详情弹窗使用宽版 modal-wide');
  ok(/\.modal-wide\{width:900px/.test(htmlSrc), '宽版弹窗宽度 900px（原 640px）');
  ok(htmlSrc.includes('id="noticeModal"') && /id="noticeModal"[\s\S]{0,200}modal-wide/.test(htmlSrc),
     '公告管理弹窗也用宽版');

  console.log('\n【用例4】子事项参与人（对标主事项）');
  // 编辑弹窗：子事项模式不再隐藏参与人
  ok(!/e_cc_wrap'\)\.style\.display=EDIT_IS_SUB\?'none':''/.test(main),
     '子事项模式不再隐藏「参与人」');
  ok(/window\._editCc=\(c\.cc\|\|''\)\.split\(';'\)\.filter\(Boolean\);/.test(main),
     '子事项也回填参与人（读取 cc 字段）');
  // 2026-11-04 #54：选择器带选人池与互斥配对（pool / pair）
  ok(/initPersonPicker\('e_cc',window\._editCc=window\._editCc\|\|\[\],pool,'e_owner',false\);/.test(main),
     '子事项也初始化参与人选择器（带板块选人池与互斥配对）');
  ok(/fields\.cc=\(window\._editCc\|\|\[\]\)\.join\(';'\);/.test(main),
     '保存时子事项也提交 cc 字段');
  // 新建弹窗：主/子事项都有参与人
  ok(/id="n_cc"/.test(htmlSrc), '新建弹窗有参与人选择器 n_cc');
  ok(/let NEW_CARD_CC=\[\]/.test(main), '新建弹窗有参与人状态 NEW_CARD_CC');
  ok(/cc:NEW_CARD_CC\.join\(';'\)/.test(main), '新建时提交参与人（主/子事项各一处）');
  ok((main.match(/cc:NEW_CARD_CC\.join\(';'\)/g) || []).length === 2, '主事项与子事项的创建都提交参与人');

  console.log('\n【用例5】编辑弹窗能正常打开');
  // 🔴 回归防护：删了按钮忘了删引用 → openEdit 抛错 → 弹窗永远打不开
  ok(!/getElementById\('e_sub_btn'\)/.test(main), '不再引用已删除的 e_sub_btn（曾导致 openEdit 崩溃）');
  // 扫描所有 getElementById(...).xxx 引用，确保 id 都存在
  const ids = new Set([...htmlSrc.matchAll(/id="([A-Za-z_][\w-]*)"/g)].map(m => m[1]));
  const missing = [];
  for (const m of main.matchAll(/getElementById\('([A-Za-z_][\w-]*)'\)\s*\.\s*(\w+)/g)) {
    if (!ids.has(m[1])) missing.push(m[1] + '.' + m[2]);
  }
  ok(missing.length === 0, `没有引用不存在的元素（${missing.length ? missing.join(', ') : '全部有效'}）`);

  // 实际调用 openEdit，验证弹窗真的能显示
  const SUB = {
    card_id: 'NC1', card_name: '子事项A', parent_id: 'P1', board_id: 'B1',
    board_name: '综合工作事项', column_name: '板块A', status: 'progressing',
    owner: '王伟娜', cc: '吴婷婷;李梦子', begin: '', due: '', description: '',
    created: '2026-08-13', locked_by: null, created_at: '2026-08-13 09:00:00',
  };
  sandbox.api = async (u) => {
    if (String(u).includes('card_id=NC1')) return { cards: [SUB], columns: [] };
    if (String(u).endsWith('/subtasks')) return { subtasks: [], total: 0, done: 0 };
    return {};
  };
  sandbox.lockCard = async () => true;
  let threw = null;
  try {
    await sandbox.openEdit('NC1', SUB);
  } catch (e) { threw = e; }
  ok(threw === null, 'openEdit 不抛异常（编辑弹窗可以正常打开）' + (threw ? '：' + threw.message : ''));
  eq(getEl('editModal').style.display, 'flex', '编辑弹窗确实显示出来了');
  eq(getEl('editTitle').textContent, '编辑子事项', '标题为「编辑子事项」');
  // 子事项模式下不再设置 display（不隐藏即默认可见）——断言「没有被设为 none」
  ok(getEl('e_cc_wrap').style.display !== 'none', '子事项模式下「参与人」区域可见（未被隐藏）');
  ok(getEl('e_board_wrap').style.display === 'none', '子事项模式下「所属看板」仍隐藏（继承父看板）');

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证异常:', e); process.exit(1); });
