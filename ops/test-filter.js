// 筛选功能专项回归测试（负责人「无负责人」+ 创建日期区间）
// 覆盖：
//   1) 负责人下拉含静态「无负责人」选项，且动态填充的负责人不会被覆盖/丢失
//   2) reload() 组装查询参数：日期区间、状态、负责人、搜索词可任意组合
//   3) 创建日期区间边界：起止颠倒自动交换、可清空、清除按钮显隐
//   4) 后端查询条件（SQL 层下推 + 哨兵值）静态核对
// 运行：node ops/test-filter.js
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlPath = path.join(ROOT, 'src', 'static', 'index.html');
const htmlSrc = fs.readFileSync(htmlPath, 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'app.py'), 'utf8');
const blocks = [...htmlSrc.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
// 浏览器会按顺序执行页面上所有 script 标签，测试必须照做：
// 块0 定义了 goLogin / apiUrl / API_BASE，块1 是主逻辑。只加载块1 会因缺 goLogin 而炸装载
const main = blocks.join('\n');

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
function mkEl(id) {
  const attrs = {};
  const el = {
    id, value: '', textContent: '', _html: '', style: {}, dataset: {},
    checked: false, disabled: false, hidden: false, tagName: 'DIV', options: [],
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      // 支持 toggle(cls, force)：传 force 时是「设置」而非「切换」
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
    removeAttribute(k) { delete attrs[k]; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
  };
  return el;
}

const els = new Map();
const getEl = (id) => { if (!els.has(id)) els.set(id, mkEl(id)); return els.get(id); };

const document = {
  getElementById: getEl,
  querySelector() { return mkEl('s'); },
  querySelectorAll() { return []; },
  createElement(tag) { const e = mkEl('new-' + tag); e.tagName = tag; return e; },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'), documentElement: mkEl('de'), head: mkEl('head'),
};

const sandbox = {
  console,
  setTimeout: () => 0, clearTimeout: () => 0, setInterval: () => 0, clearInterval: () => 0,
  document,
  URLSearchParams,
  localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
  fetch: () => Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve({}) }),
  location: { href: 'http://127.0.0.1:8100/', search: '', pathname: '/', origin: 'http://127.0.0.1:8100' },
  history: {}, navigator: { userAgent: 'node' },
  alert: () => {}, confirm: () => true,
  WebSocket: function () { return { close() {}, send() {}, readyState: 0 }; },
  addEventListener() {}, removeEventListener() {},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.self = sandbox;

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
function setLet(name, value) { vm.runInContext(`${name}=${JSON.stringify(value)};`, sandbox); }
function getLet(name) { return vm.runInContext(name, sandbox); }

// 捕获 reload() 发出的请求 URL
let captured = '';
// /api/overview 的返回（负责人下拉的动态数据源）
let OVERVIEW = { total: 0, done: 0, progressing: 0, open: 0, owners: [{ owner: '吴婷婷' }, { owner: '吕春梅' }] };
sandbox.api = async (u) => {
  if (String(u).indexOf('/api/overview') >= 0) return OVERVIEW;
  captured = u;
  return { cards: [], columns: [], column_hits: [] };
};
sandbox.renderBoard = () => {};

(async () => {
  // ============================================================
  // 用例 1：「无负责人」并入人员筛选面板（独立的「全部负责人」下拉已下线）
  // ============================================================
  console.log('\n【用例1】「无负责人」并入人员筛选面板');
  ok(!/<option value="">全部负责人<\/option>/.test(htmlSrc),
    '独立的「全部负责人」下拉已从 HTML 移除');
  ok(!/id="ownerFilter"/.test(htmlSrc),
    'ownerFilter 元素已从 HTML 移除');
  ok(/const OWNER_NONE='__no_owner__'/.test(htmlSrc),
    '前端定义 OWNER_NONE 特殊值');
  ok(/data-pick-person="\$\{OWNER_NONE\}"/.test(htmlSrc),
    '人员面板里有「无负责人」候选项（data-pick-person=OWNER_NONE）');
  ok(/function personLabel\(v\)\{return v===OWNER_NONE\?'无负责人':v\}/.test(htmlSrc),
    'personLabel() 把特殊值翻译成「无负责人」文案');
  ok(/want_none = OWNER_NONE in pnames/.test(pySrc),
    '后端 person 分支识别 __no_owner__（无负责人）');
  ok(/want_none and not o\.strip\(\)/.test(pySrc),
    '后端 person 分支：无负责人 = owner 为空或纯空白');
  ok(!/os_\.dataset\.filled/.test(htmlSrc),
    '旧的负责人下拉动态填充逻辑（dataset.filled）已移除');

  // ============================================================
  // 用例 2：reload() 组装查询参数（多条件组合）
  // ============================================================
  console.log('\n【用例2】查询参数组装与组合');
  setLet('curBoard', 'B1');
  const st = getEl('statusFilter'),
        se = getEl('searchInput'), cs = getEl('createdStart'), ce = getEl('createdEnd');

  // 2.1 只有日期区间
  st.value = ''; se.value = ''; cs.value = '2026-01-01'; ce.value = '2026-03-31';
  await sandbox.reload(1);
  ok(captured.includes('created_start=2026-01-01'), '带上了 created_start');
  ok(captured.includes('created_end=2026-03-31'), '带上了 created_end');
  ok(captured.includes('board_id=B1'), '原有 board_id 参数不受影响');

  // 2.2 日期为空 → 不传该参数
  cs.value = ''; ce.value = '';
  await sandbox.reload(1);
  ok(!captured.includes('created_start'), '日期为空时不传 created_start');
  ok(!captured.includes('created_end'), '日期为空时不传 created_end');

  // 2.3 单边区间（只填起 / 只填止）
  cs.value = '2026-05-01'; ce.value = '';
  await sandbox.reload(1);
  ok(captured.includes('created_start=2026-05-01') && !captured.includes('created_end'),
    '只填起日期 → 只传 created_start（单边区间可用）');
  cs.value = ''; ce.value = '2026-06-30';
  await sandbox.reload(1);
  ok(!captured.includes('created_start') && captured.includes('created_end=2026-06-30'),
    '只填止日期 → 只传 created_end（单边区间可用）');

  // 2.4 与状态/人员/搜索词组合
  st.value = 'done'; se.value = '报表';
  cs.value = '2026-01-01'; ce.value = '2026-12-31';
  setLet('PERSON_SEL', null);
  vm.runInContext("PERSON_SEL=new Set(['__no_owner__']);", sandbox);
  await sandbox.reload(1);
  ok(captured.includes('status=done'), '与状态筛选组合');
  ok(captured.includes('person=__no_owner__'), '与「无负责人」组合（走 person 参数）');
  ok(captured.includes('q='), '与搜索词组合');
  ok(captured.includes('created_start=2026-01-01') && captured.includes('created_end=2026-12-31'),
    '与创建日期区间组合（四个条件同时生效）');
  // 参数名不能与 TAPD 原始字段 created_from 混淆
  ok(!captured.includes('created_from'), '参数名用 created_start/end，不与 TAPD 原始字段 created_from 混淆');
  ok(!captured.includes('owner='), '不再提交 owner 参数（下拉已下线，人员筛选独占负责人维度）');
  vm.runInContext("PERSON_SEL=new Set();", sandbox);

  // ============================================================
  // 用例 3：创建日期区间的边界处理
  // ============================================================
  console.log('\n【用例3】创建日期区间边界');
  const btn = getEl('dateClearBtn'), box = getEl('dateFilterBox');

  // 3.1 起止颠倒 → 自动交换
  cs.value = '2026-09-30'; ce.value = '2026-01-01';
  await sandbox.onDateFilterChange();
  eq(cs.value, '2026-01-01', '起止颠倒时自动交换（起始变早）');
  eq(ce.value, '2026-09-30', '起止颠倒时自动交换（截止变晚）');

  // 3.2 清除按钮显隐
  btn.hidden = true; box.classList = { _s: new Set(), add() {}, remove() {}, toggle(c, f) { f ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } };
  cs.value = ''; ce.value = '';
  sandbox.syncDateFilterUI();
  eq(btn.hidden, true, '两端都为空时清除按钮隐藏');
  cs.value = '2026-01-01';
  sandbox.syncDateFilterUI();
  eq(btn.hidden, false, '有任一端取值时清除按钮显示');
  ok(box.classList.contains('active'), '有取值时日期区间容器高亮');

  // 3.3 清空 → 取消该筛选
  cs.value = '2026-01-01'; ce.value = '2026-02-28';
  await sandbox.clearDateFilter();
  eq(cs.value, '', '清除后起始日期为空');
  eq(ce.value, '', '清除后截止日期为空');
  eq(btn.hidden, true, '清除后按钮重新隐藏');
  ok(!captured.includes('created_start') && !captured.includes('created_end'),
    '清除后不再传日期参数（筛选已取消）');

  // 3.4 CSS：[hidden] 必须显式兜底，否则会被 inline-flex 覆盖导致按钮永远显示
  ok(/\.filter-clear\[hidden\]\{display:none\}/.test(htmlSrc),
    '[hidden] 有显式兜底样式（否则清除按钮会被 inline-flex 覆盖而常驻）');
  ok(/\.search-input\{[^}]*max-width:230px/.test(htmlSrc),
    '搜索框已限宽（给日期区间腾出空间，工具栏不被撑成两行）');
  // 筛选区整行不换行：日期区间必须与其它筛选控件同一行
  ok(/\.toolbar-left\{[^}]*flex-wrap:nowrap/.test(htmlSrc),
    '筛选区 flex-wrap:nowrap（搜索/状态/人员/周数/日期区间保持同一行）');
  ok(/\.cf-field\{[^}]*max-width:220px/.test(htmlSrc),
    '人员与周数输入区已限宽（max-width:220px）');

  // ============================================================
  // 用例 4：后端查询条件核对
  // ============================================================
  console.log('\n【用例4】后端查询条件');
  ok(/OWNER_NONE\s*=\s*'__no_owner__'/.test(pySrc),
    '后端定义了「无负责人」哨兵值 OWNER_NONE');
  ok(/if owner == OWNER_NONE:/.test(pySrc),
    '后端对「无负责人」走独立分支（不与普通负责人的子串匹配混淆）');
  ok(/not \(r\.get\('owner'\) or ''\)\.strip\(\)/.test(pySrc),
    '「无负责人」判定为负责人为空或纯空白');
  ok(/elif owner:/.test(pySrc) && /owner in \(r\.get\('owner'\) or ''\)/.test(pySrc),
    '普通负责人保持既有的子串匹配语义（不改变原有行为）');
  ok(/substr\(created,1,10\) >= \?/.test(pySrc) && /substr\(created,1,10\) <= \?/.test(pySrc),
    '创建日期区间下推到 SQL（substr 取日期部分比较，兼容带时分秒的 created）');
  ok(/def _norm_date/.test(pySrc),
    '有日期归一化函数（非法值忽略而不是报错）');
  ok(/created_start: Optional\[str\] = None, created_end: Optional\[str\] = None/.test(pySrc),
    '接口新增 created_start / created_end 查询参数');
  // 子事项计数必须用全量行，不能被日期区间裁剪
  ok(/all_rows = \[dict\(r\) for r in dbq\('SELECT \* FROM cards WHERE deleted=0'\)\]/.test(pySrc),
    '全量行仍单独查询（子事项计数不被筛选条件裁剪）');

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})();
