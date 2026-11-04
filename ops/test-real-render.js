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

  // 找有子事项的父事项（用 sub_count 判断，不依赖已移除的 sub_owners）
  const parent = cards.cards.find(c => (c.sub_count || 0) > 0);
  ok(!!parent, '找到有子事项的父事项：' + (parent ? parent.card_name : '无'));

  if (parent) {
    // 1) 父事项行渲染：负责人独立取值
    vm.runInContext(`ME={can_edit:true,is_admin:true,username:'admin',boards:[{board_id:'${parent.board_id}',board_name:'B'}]};curBoard='${parent.board_id}';`, sandbox);
    const rowHtml = sandbox.cardItem(parent, 1);
    console.log('    父事项行 HTML 片段:', rowHtml.match(/<span class="fcol[^>]*>[^<]*<\/span>/)?.[0] || '(无)');
    // 2026-11-04 #55：字段渲染从「label：value」改为「label value」（去冒号省宽）
    ok(/负责人 [^<]/.test(rowHtml), '父事项行显示了「负责人」前缀');
    ok(rowHtml.includes('＋ 子事项'), '父事项行的子事项按钮文案正确');
    // 父事项负责人独立：不借用子事项负责人
    const childOwners = await api('/api/cards/' + parent.card_id + '/children')
      .then(d => (d.children || []).map(c => c.owner).filter(Boolean));
    if (childOwners.length && !parent.owner) {
      ok(!childOwners.some(o => rowHtml.includes(o)),
        '父事项无负责人时不借用子事项负责人');
      ok(rowHtml.includes('负责人 —'), '父事项无负责人时占位为「负责人 —」');
    }
    // 字段列：创建日期只到年月日
    ok(/创建：\d{4}-\d{2}-\d{2}/.test(rowHtml), '行内显示「创建：YYYY-MM-DD」（标签精简）');
    ok(!/创建日期：\d{4}-\d{2}-\d{2}\s\d{2}:/.test(rowHtml), '创建日期不含时分秒');
    ok(rowHtml.includes('fcols'), '字段列用 grid 定宽容器');
    // 2026-11-04 #55：置顶/复制合并为 slot-ops（操作菜单）
    ok(rowHtml.includes('slot-overdue') && rowHtml.includes('slot-status')
      && rowHtml.includes('slot-ops') && rowHtml.includes('slot-sub'),
      '主事项行渲染全部固定槽位（有/无内容都占位）');

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
      // 子事项的字段集合与顺序与父事项一致
      const pOrder = (rowHtml.match(/fcol-(owner|created|due)/g) || []);
      const sOrder = (subHtml.match(/fcol-(owner|created|due)/g) || []);
      ok(pOrder.join(',') === 'fcol-owner,fcol-created,fcol-due', '父事项字段顺序 = 负责人/创建日期/截止日期');
      ok(sOrder.join(',') === pOrder.join(','), '子事项字段集合与顺序与父事项完全一致');
      ok(/创建：\d{4}-\d{2}-\d{2}/.test(subHtml), '子事项显示「创建：YYYY-MM-DD」（标签精简）');
      ok(!/创建日期：\d{4}-\d{2}-\d{2}\s\d{2}:/.test(subHtml), '子事项创建日期不含时分秒');
      ok(subHtml.includes('slot-overdue') && subHtml.includes('slot-status') && subHtml.includes('slot-ops'),
        '子事项行渲染全部固定槽位');
    }

    // 3) 右侧抽屉已移除：子事项只保留列表目录 + 详情弹窗两处入口
    ok(typeof sandbox.drawerSubTree === 'undefined', '抽屉子事项树已移除');
  }

  // 4) 年份筛选默认值（多选 chips）
  const cols = cards.columns.map(c => ({ column_name: c.column_name, year: c.year }));
  vm.runInContext('curYears=new Set([YEAR_DEFAULT]);', sandbox);
  sandbox.renderYearFilter(cols);
  const sel = getEl('yearFilter').innerHTML;
  ok(/data-year="\d{4}"/.test(sel), '年份筛选器默认渲染当前年份 chip');
  ok(sel.includes('全部年份'), '年份筛选器含「全部年份」清空入口');
  console.log('    年份筛选器 HTML:', sel.slice(0, 220));

  console.log(`\n结果：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证异常:', e); process.exit(1); });
