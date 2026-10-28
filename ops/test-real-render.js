// 用真实接口数据验证：子事项目录行的圆点颜色 / 负责人前缀，父事项行的责任人汇总
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const BASE = 'http://127.0.0.1:8100';
const TOKEN = fs.readFileSync('C:/tmp_tk.txt', 'utf8').trim();

const html = fs.readFileSync(path.join(__dirname, '..', 'src', 'static', 'index.html'), 'utf8');
const jsBlocks = html.match(/<script[^>]*>([\s\S]*?)<\/script>/g)
  .map(b => b.replace(/^<script[^>]*>/, '').replace(/<\/script>$/, ''));
const js = jsBlocks.join('\n');

// ---- 最小 DOM stub ----
function mkEl(id) {
  const attrs = {};
  const el = {
    id, style: {}, dataset: {}, className: '', innerHTML: '', textContent: '', value: '',
    children: [], classList: {
      add() {}, remove() {}, toggle() {}, contains() { return false; },
    },
    addEventListener() {}, removeEventListener() {}, focus() {}, click() {}, blur() {},
    querySelector() { return mkEl(id + '>q'); },
    querySelectorAll() { return []; },
    closest() { return null; },
    appendChild() {}, remove() {}, setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    removeAttribute(k) { delete attrs[k]; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
  };
  return el;
}
const els = {};
function getEl(id) { if (!els[id]) els[id] = mkEl(id); return els[id]; }
const document = {
  getElementById: getEl,
  querySelector() { return mkEl('q'); },
  querySelectorAll() { return []; },
  createElement() { return mkEl('new'); },
  addEventListener() {},
  body: mkEl('body'),
};
const sandbox = {
  document, console,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  location: { href: BASE, pathname: '/' },
  fetch: (u, o) => fetch(u.startsWith('http') ? u : BASE + u, o),
  setTimeout, clearTimeout, setInterval, clearInterval,
  navigator: { userAgent: 'node' },
  window: {},
  URL, URLSearchParams, JSON, Math, Date, Promise, RegExp, Error,
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(js, sandbox); } catch (e) { console.error('脚本注入失败:', e.message); process.exit(1); }

let pass = 0, fail = 0;
function ok(c, m) { if (c) { pass++; console.log('  ✓ ' + m); } else { fail++; console.log('  ✗ ' + m); } }

(async () => {
  const H = { Authorization: 'Bearer ' + TOKEN };
  const api = async (p) => (await fetch(BASE + p, { headers: H })).json();

  console.log('\n【真实数据渲染验证】');
  const cards = await api('/api/cards?size=2000');

  // 找有子事项的父事项
  const parent = cards.cards.find(c => (c.sub_owners || []).length > 0);
  ok(!!parent, '找到有子事项的父事项：' + (parent ? parent.card_name : '无'));

  if (parent) {
    // 1) 父事项行渲染：责任人汇总
    vm.runInContext(`ME={can_edit:true,is_admin:true,username:'admin',boards:[{board_id:'${parent.board_id}',board_name:'B'}]};curBoard='${parent.board_id}';`, sandbox);
    const rowHtml = sandbox.cardItem(parent, 1);
    console.log('    父事项行 HTML 片段:', rowHtml.match(/<span class="item-owner"[^>]*>[^<]*<\/span>/)?.[0] || '(无)');
    ok(/负责人：[^<]/.test(rowHtml), '父事项行显示了「负责人：」前缀');
    ok(rowHtml.includes(parent.sub_owners[0]), '父事项行包含子事项责任人');
    ok(rowHtml.includes('＋ 子事项'), '父事项行的子事项按钮文案正确');

    // 2) 子事项目录行渲染
    const children = await api('/api/cards/' + parent.card_id + '/children');
    const sub = children.children[0];
    ok(!!sub, '取到子事项：' + (sub ? sub.card_name : '无'));
    if (sub) {
      const subHtml = sandbox.subNodeHtml(sub, 0);
      console.log('    子事项行 HTML 片段:', subHtml.replace(/\n\s*/g, ' ').slice(0, 260));
      ok(subHtml.includes('负责人：' + sub.owner), '子事项行显示「负责人：' + sub.owner + '」');
      ok(!subHtml.includes('avatarColor'), '子事项行不再按姓名哈希颜色');
      ok(/class="s-dot"/.test(subHtml), '子事项行有 s-dot 圆点');
      ok(!/s-dot[^>]*style=/.test(subHtml), '圆点不再带内联背景色（统一走 CSS 的品牌金）');
    }

    // 3) 抽屉里的子事项行
    const drawerHtml = sandbox.drawerSubTree(children.children, parent.card_id, 0);
    ok(drawerHtml.includes('负责人：' + (sub ? sub.owner : '')), '抽屉子事项行显示「负责人：」前缀');
    ok(!drawerHtml.includes('avatarColor'), '抽屉子事项行不再按姓名哈希颜色');
  }

  // 4) 年份筛选默认值
  const cols = cards.columns.map(c => ({ column_name: c.column_name, year: c.year }));
  vm.runInContext('curYear=YEAR_DEFAULT;', sandbox);
  sandbox.renderYearFilter(cols);
  const sel = getEl('yearFilter').innerHTML;
  ok(/value="2026"[^>]*selected/.test(sel) || /selected[^>]*value="2026"/.test(sel), '年份下拉默认选中当前年份');
  console.log('    年份下拉 HTML:', sel.slice(0, 220));

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证异常:', e); process.exit(1); });
