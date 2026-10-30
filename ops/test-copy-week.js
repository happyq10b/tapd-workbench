// 复制（看板/板块/主事项/子事项）+ 周数字段 专项回归测试（前端源码断言）
// 覆盖：
//   1) 周数维度：列表字段列位于「创建日期」之前；主/子事项共用同一套网格列宽
//   2) 复制弹窗：三种层级的字段（归属重选）+ 副本命名 + 提示文案
//   3) 复制入口：看板管理列表 / 板块头部 / 事项编辑弹窗
//   4) 复制选项**只来自权限过滤后的接口**（/api/me、/api/boards/{id}/columns、/api/cards）
//   5) 周数筛选：多选（勾选式下拉）+ 参数传递
// 运行：node ops/test-copy-week.js
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src', 'static', 'index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'app.py'), 'utf8');
const initDbSrc = fs.readFileSync(path.join(ROOT, 'src', 'app', 'init_db.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

// ============================================================
// 用例 1：周数字段（数据模型 + 计算 + 列表展示）
// ============================================================
console.log('\n【用例1】周数字段');
ok(/week_no\s+TEXT NOT NULL DEFAULT ''/.test(initDbSrc), 'cards 表新增 week_no 列（自然周维度）');
ok(/week_no\s+TEXT NOT NULL DEFAULT ''/.test(pySrc) || /'week_no','copy_from'/.test(pySrc),
  'week_no 纳入 CARD_FIELDS（可随 JSON 导入导出往返）');
ok(/def week_label\(s\) -> str:/.test(pySrc), '后端提供周数计算 week_label()');
ok(/isocalendar\(\)/.test(pySrc), '按 ISO 周计算（周四定归属年，周一~周日为一周）');
ok(/def _norm_week\(v\) -> str:/.test(pySrc), '周数字段有格式归一与校验');
ok(/'周数'\s*:\s*'2026年第41周'/.test(pySrc) || /第%d周/.test(pySrc), '周数格式为「YYYY年第N周」');
ok(/\['week_no'\] = _norm_week\(req\.week_no or vals\.get\('week_no', ''\)\) or week_label\(vals\['created'\]\)/.test(pySrc),
  '新建事项默认按创建日期所在自然周取周数');
ok(/week: Optional\[str\] = None/.test(pySrc), '列表接口支持 week 筛选参数');
ok(/wset = \{x\.strip\(\) for x in week\.split\(','\) if x\.strip\(\)\}/.test(pySrc),
  '周数筛选支持多值（逗号分隔 = 任一命中）');
ok(/'weeks': week_options/.test(pySrc), '接口回传可选周数列表（供筛选栏下拉）');
// 前端：列表字段列
ok(/\{key:'week_no', label:'周数'/.test(htmlSrc), '列表字段列包含「周数」');
ok(/\{key:'owner',\s+label:'负责人'[\s\S]{0,120}\{key:'week_no', label:'周数'[\s\S]{0,120}\{key:'created', label:'创建日期'/.test(htmlSrc),
  '「周数」位于「创建日期」之前（创建信息列之前）');
ok(/fieldCols\(\{owner:c\.owner,week_no:c\.week_no,created:c\.created,due:c\.due,column_name:c\.column_name\}\)/.test(htmlSrc),
  '主事项行传入周数（并带所属板块名，用于标注板块年份）');
ok(/fieldCols\(\{owner:n\.owner,week_no:n\.week_no,created:n\.created,due:n\.due,column_name:n\.column_name\}\)/.test(htmlSrc),
  '子事项行传入周数（并带所属板块名，用于标注板块年份）');
// 主/子网格列宽必须完全一致（否则父子两行字段列起点会错位）
const mainGrid = (htmlSrc.match(/\.fcols\{grid-template-columns:([^;]+);/) || [])[1];
const subGrid = (htmlSrc.match(/\.sub-node \.fcols\{grid-template-columns:([^;]+);/) || [])[1];
ok(!!mainGrid && !!subGrid && mainGrid === subGrid,
  `主/子事项网格列宽一致：${mainGrid} / ${subGrid}`);
ok(/166px 118px 146px 178px/.test(mainGrid || ''), '网格含周数列（118px）且定宽');
const mainWidth = (htmlSrc.match(/\.fcols\{[\s\S]*?width:(\d+)px;flex:0 0 (\d+)px/) || []);
const subWidth = (htmlSrc.match(/\.sub-node \.fcols\{[\s\S]*?width:(\d+)px;flex:0 0 (\d+)px/) || []);
ok(mainWidth[1] === subWidth[1] && mainWidth[2] === subWidth[2],
  `主/子事项字段列容器宽度一致：${mainWidth[1]}/${mainWidth[2]} vs ${subWidth[1]}/${subWidth[2]}`);
// 编辑 / 新建 / 详情弹窗
ok(/id="e_week"/.test(htmlSrc), '事项编辑弹窗有「周数」字段');
ok(/id="n_week"/.test(htmlSrc), '新建事项弹窗有「周数」字段');
ok(/周数：<b>\$\{esc\(c\.week_no\|\|'—'\)\}/.test(htmlSrc), '详情弹窗展示周数');

// ============================================================
// 用例 2：复制弹窗与三个层级的归属重选
// ============================================================
console.log('\n【用例2】复制弹窗与归属重选');
ok(/id="copyModal"/.test(htmlSrc), '存在复制弹窗');
ok(/id="cp_board"/.test(htmlSrc) && /id="cp_col"/.test(htmlSrc) && /id="cp_parent"/.test(htmlSrc),
  '复制弹窗含目标看板 / 目标板块 / 所属主事项三级归属选择');
ok(/id="cp_board_cfg"/.test(htmlSrc), '看板复制可重选归属部门/年份/属性/状态');
ok(/id="cp_col_cfg"/.test(htmlSrc), '板块复制可设置创建日期/性质/归属年份');
ok(/COPY_SUFFIX='（副本）'/.test(htmlSrc), '副本命名后缀为「（副本）」');
ok(/document\.getElementById\('cp_name'\)\.value=\(P\.board_name\|\|''\)\+COPY_SUFFIX/.test(htmlSrc),
  '看板副本默认标题带后缀');
ok(/document\.getElementById\('cp_name'\)\.value=\(P\.column_name\|\|''\)\+COPY_SUFFIX/.test(htmlSrc),
  '板块副本默认标题带后缀');
ok(/document\.getElementById\('cp_name'\)\.value=\(P\.card_name\|\|''\)\+COPY_SUFFIX/.test(htmlSrc),
  '事项副本默认标题带后缀（可编辑）');
ok(/复制子事项必须重新选择所属主事项|复制子事项时还必须重新选择所属主事项/.test(htmlSrc + pySrc),
  '复制子事项必须重新选择所属主事项');
ok(/kind==='sub'\?\{[\s\S]{0,200}cp_parent_wrap/.test(htmlSrc) || /show\('cp_parent_wrap',kind==='sub'\)/.test(htmlSrc),
  '子事项复制才显示「所属主事项」选择');
// 选项来源：必须是权限过滤后的接口
ok(/const list=\(ME&&ME\.boards\)\|\|\[\]/.test(htmlSrc), '目标看板选项来自 /api/me（已按权限过滤）');
ok(/\/api\/boards\/'\+encodeURIComponent\(bid\)\+'\/columns/.test(htmlSrc),
  '目标板块选项来自 /api/boards/{id}/columns（visible_columns 过滤）');
ok(/\/api\/cards\?'\+qs/.test(htmlSrc) && /cards=\(d\.cards\|\|\[\]\)\.filter\(c=>!c\.parent_id\)/.test(htmlSrc),
  '所属主事项选项来自 /api/cards（列表本身已按可见性过滤，且只取主事项）');
ok(/越权数据既不会出现在下拉里，也提交不上去/.test(htmlSrc), '前端注释写明越权不可见不可选');

// ============================================================
// 用例 3：三个层级的复制入口
// ============================================================
console.log('\n【用例3】复制入口');
ok(/openCopyModal\('column'/.test(htmlSrc), '板块头部有复制入口');
ok(/openCopyModal\([^)]{0,12}board/.test(htmlSrc), '看板管理列表有复制入口');
ok(/openCopyModal\(kind/.test(htmlSrc) && /copyCurrentCard\(\)/.test(htmlSrc), '事项编辑弹窗有复制入口');
ok(/id="e_copy_btn"/.test(htmlSrc), '编辑弹窗页脚含复制按钮');
ok(/openCopyModal\('board'[\s\S]{0,400}ME\.is_admin/.test(htmlSrc) || /kind==='board'&&!ME\.is_admin/.test(htmlSrc),
  '看板复制仅管理员可用（与看板新建/配置同级）');

// ============================================================
// 用例 4：后端复制接口与权限校验
// ============================================================
console.log('\n【用例4】后端复制接口与权限校验');
ok(/@app\.post\('\/api\/boards\/\{board_id\}\/copy'\)/.test(pySrc), '看板复制接口');
ok(/@app\.post\('\/api\/columns\/copy'\)/.test(pySrc), '板块复制接口');
ok(/@app\.post\('\/api\/cards\/copy'\)/.test(pySrc), '事项（主/子）复制接口');
ok(/copy_from\s+TEXT NOT NULL DEFAULT ''/.test(initDbSrc), '副本标识列 copy_from（boards/board_columns/cards）');
ok(/check_card_access\(req\.card_id, username\)/.test(pySrc), '复制前校验源事项可见性');
ok(/check_board_access\(req\.board_id, username\)/.test(pySrc), '复制前校验目标看板可见 + 可编辑');
ok(/check_column_access\(req\.board_id, req\.column_id, username\)/.test(pySrc), '复制前校验目标板块可见');
ok(/if not perm_pass\(prow, boards, columns\)/.test(pySrc), '复制子事项时校验目标主事项可见');
ok(/raise HTTPException\(400, '复制子事项必须重新选择所属主事项'\)/.test(pySrc), '子事项副本缺父事项 → 400');
ok(/'status'\] = 'open'/.test(pySrc), '副本状态重置为未完成');
ok(/'creator'\] = username/.test(pySrc), '副本创建人 = 当前账号');
ok(/'copy_from'\] = src\['card_id'\]/.test(pySrc), '副本记录复制来源（copy_from）');
ok(/CARD_COPY_FIELDS = \[/.test(pySrc), '副本只带业务字段（运行态字段不复制）');

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
