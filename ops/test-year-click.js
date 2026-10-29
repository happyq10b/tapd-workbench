// 年份筛选 chip 的真实点击测试（node vm 沙箱 + 真实 MouseEvent）
// 验证：✕ 移除单个年份、「全部年份」清空、点 chip 主体不误触发、多选后移除其一
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

// ---------- 最小 DOM stub（与 test-dept.js 同构） ----------
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
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest(sel) {
      // 简化实现：只处理我们关心的 .yc-x / [data-all="1"]
      if (sel.includes('yc-x')) return el._isX ? el : null;
      if (sel.includes('data-all')) return el._isAll ? el : null;
      if (sel === '#yearFilter') return el._inFilter ? el : null;
      return null;
    },
    appendChild(c) { return c; }, insertBefore(c) { return c; }, remove() {},
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
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
  alert() {}, confirm: () => true, MouseEvent: class { constructor(t, o) { Object.assign(this, o); } },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(main, sandbox, { filename: 'index-inline.js' }); }
catch (e) { console.error('装载失败:', e); process.exit(1); }

const setLet = (n, v) => vm.runInContext(`${n}=${JSON.stringify(v)};`, sandbox);
const getLet = (n) => vm.runInContext(n, sandbox);
const getEl = (id) => document.getElementById(id);

// 模拟 document 上的委托点击：按 e.target 分发到注册的 click handler
function fireClick(target) {
  const handlers = (document._h && document._h.click) || [];
  for (const fn of handlers) {
    fn({ target, stopPropagation() {} });
  }
}
// 造一个 chip 元素（带 closest 能力）
function makeChip(html, isX, isAll, year) {
  const el = mkEl('chip');
  el._html = html;
  el._isX = !!isX; el._isAll = !!isAll; el._inFilter = true;
  if (year) el.dataset.year = year;
  if (isAll) el.dataset.all = '1';
  return el;
}

(async () => {
  console.log('\n【年份筛选 chip 的真实点击】');
  const COLS = [{ column_name: '板块A', year: '2026' }, { column_name: '板块B', year: '2025' }, { column_name: '板块C', year: '2024' }];

  // 记录 reload 调用
  let reloadCalls = [];
  sandbox.reload = (p) => { reloadCalls.push(p); };
  sandbox.api = async () => ({ cards: [], columns: [] });
  sandbox.renderBoard = () => {};
  // 选项来源由 renderYearFilter 自行记录到 _yearOptions

  // ① 选中 2026 + 2025 → 两个 chip
  vm.runInContext("curYears=new Set(['2026','2025']);", sandbox);
  sandbox.renderYearFilter(COLS);
  const box = getEl('yearFilter');
  const html = box.innerHTML;
  ok((html.match(/class="year-chip"/g) || []).length === 2, '两个已选年份 → 两个 chip');
  ok((html.match(/class="yc-x"/g) || []).length === 2, '每个 chip 都有独立的 ✕ 移除入口');
  ok(html.includes('data-all="1"'), '提供「全部年份」清空入口');

  // ② 真实点击 ✕（data-year=2026）→ 应移除 2026
  const x2026 = makeChip('', true, false, '2026');
  fireClick(x2026);
  const afterX = getLet('curYears');
  eq([...afterX].sort().join(','), '2025', '点 ✕ 后该年份被移除（其余保持选中）');
  ok(reloadCalls.length === 1, '移除后触发了一次列表刷新');

  // ③ 真实点击「全部年份」→ 清空
  reloadCalls = [];
  const all = makeChip('', false, true, null);
  fireClick(all);
  eq([...getLet('curYears')].join(','), '', '点「全部年份」后清空所有已选');
  ok(reloadCalls.length === 1, '清空后触发了一次列表刷新');

  // ④ 点 chip 主体（既非 ✕ 也非全部年份）→ 不应改变状态
  vm.runInContext("curYears=new Set(['2026']);", sandbox);
  reloadCalls = [];
  const body = makeChip('', false, false, null);
  fireClick(body);
  eq([...getLet('curYears')].join(','), '2026', '点 chip 主体不改变选中状态（标签本身不可点）');
  eq(reloadCalls.length, 0, '点 chip 主体不触发无谓的列表刷新');

  // ⑤ 多选三个 → 移除中间那个
  vm.runInContext("curYears=new Set(['2024','2025','2026']);", sandbox);
  sandbox.renderYearFilter(COLS);
  ok((getEl('yearFilter').innerHTML.match(/class="year-chip"/g) || []).length === 3, '三个年份 → 三个 chip');
  reloadCalls = [];
  const x2025 = makeChip('', true, false, '2025');
  fireClick(x2025);
  eq([...getLet('curYears')].sort().join(','), '2024,2026', '多选状态下移除其中一个，其余不受影响');

  // ⑥ 边界：移除最后一个 → 变成空集合（= 全部年份）
  vm.runInContext("curYears=new Set(['2026']);", sandbox);
  const xLast = makeChip('', true, false, '2026');
  fireClick(xLast);
  eq([...getLet('curYears')].join(','), '', '移除最后一个年份后为空集合（= 不筛选）');

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证异常:', e); process.exit(1); });
