// -*- coding: utf-8 -*-
/**
 * 安全模块的静态断言：小眼睛（密码可见切换）+ 登录失败锁定策略。
 * 配套端到端测试：ops/test_login_lock.py（需实时服务）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src/static/index.html'), 'utf8');
const loginSrc = fs.readFileSync(path.join(ROOT, 'src/static/login.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src/app/app.py'), 'utf8');
const initSrc = fs.readFileSync(path.join(ROOT, 'src/app/init_db.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

// ============================================================
// 用例 1：密码框小眼睛（改密三框）
// ============================================================
console.log('\n【用例1】密码框小眼睛（可见切换）');
// —— 必须复用项目既有实现（.pwd-eye / togglePwd / pwdEyeHtml），
//    不得另造同名 class 覆盖既有样式（成员管理也在用）——
ok((htmlSrc.match(/^\.pwd-eye\{/gm) || []).length === 1, '.pwd-eye 样式只有一处定义（不覆盖既有）');
ok((htmlSrc.match(/^\.pwd-wrap\{/gm) || []).length === 1, '.pwd-wrap 样式只有一处定义');
ok(/function togglePwd\(inputId,btn\)/.test(htmlSrc), '复用既有切换函数 togglePwd');
ok(/function pwdEyeHtml\(inputId\)/.test(htmlSrc), '复用既有小眼睛 HTML helper');
ok(/inp\.type=show\?'text':'password'/.test(htmlSrc), '点击切换 type=password↔text');
ok(/btn\.innerHTML=show\?EYE_OFF:EYE_ON/.test(htmlSrc), 'SVG 眼睛图标随状态切换');
ok(/id="profileOldPwd"/.test(htmlSrc) && /id="profileNewPwd"/.test(htmlSrc) && /id="profileNewPwd2"/.test(htmlSrc),
  '三个改密输入框都在');
ok((htmlSrc.match(/id="eye_profile/g) || []).length === 3, '三个小眼睛挂载位');
ok(/slot\.innerHTML=pwdEyeHtml\(id\)/.test(htmlSrc), '打开弹窗时用既有 helper 渲染小眼睛');
ok(/el\.type='password'/.test(htmlSrc), '打开弹窗时输入框复位为密码类型');
ok(!/togglePwdEye/.test(htmlSrc), '未另造 togglePwdEye（避免与既有 togglePwd 重复）');

// ============================================================
// 用例 2：登录页小眼睛
// ============================================================
console.log('\n【用例2】登录页小眼睛');
ok(/id="pwdEye"/.test(loginSrc), '登录页有小眼睛按钮');
ok(/function toggleEye\(\)/.test(loginSrc), '登录页切换函数');
ok(/p\.type=willShow\?'text':'password'/.test(loginSrc), '登录页切换 type');
// —— 小眼睛必须写死尺寸：通用 button 样式若带 width:100%，
//    绝对定位后按钮会撑满并盖住输入框 → 「密码无法输入 + 显示错乱」——
ok(/\.pwd-eye\{[^}]*width:28px[^}]*height:28px/.test(loginSrc), '小眼睛写死 28×28（不被通用 button 撑大）');
ok(/\.pwd-eye\{[^}]*position:absolute/.test(loginSrc), '小眼睛绝对定位在输入框内右侧');
ok(/#btn\{width:100%\}/.test(loginSrc), '通用 button 的 width:100% 已收窄到 #btn');
ok(!/^button\{[^}]*width:100%/m.test(loginSrc), '通用 button 样式不再带 width:100%（避免误伤其他按钮）');
ok(/\.pwd-eye\{position:absolute/.test(loginSrc), '登录页小眼睛样式');

// ============================================================
// 用例 3：登录失败锁定策略（后端）
// ============================================================
console.log('\n【用例3】登录失败锁定策略');
ok(/LOGIN_FAIL_THRESHOLD = 5/.test(pySrc), '失败阈值 5 次');
ok(/LOGIN_COOLDOWN = 180/.test(pySrc), '冷却时长 180 秒（3 分钟）');
ok(/LOGIN_LOCK_THRESHOLD = 10/.test(pySrc), '锁定阈值 10 次');
ok(/CREATE TABLE IF NOT EXISTS login_attempts/.test(initSrc), 'login_attempts 表');
ok(/fail_count\s+INTEGER NOT NULL DEFAULT 0/.test(initSrc), '记录失败次数');
ok(/locked\s+INTEGER NOT NULL DEFAULT 0/.test(initSrc), '记录锁定标记');
ok(/def _login_lock_state\(username: str\)/.test(pySrc), '锁定状态判定函数');
ok(/def _login_record_fail\(username: str, ip: str\)/.test(pySrc), '失败计数函数');
ok(/def _login_record_success\(username: str\)/.test(pySrc), '成功清零函数');
ok(/DELETE FROM login_attempts WHERE username=\?/.test(pySrc), '成功后清零（DELETE 整行）');
ok(/HTTPException\(429/.test(pySrc), '达到阈值返回 429（冷却）');
ok(/HTTPException\(423/.test(pySrc), '锁定返回 423');
ok(/'Retry-After': str\(LOGIN_COOLDOWN\)/.test(pySrc), '429 携带 Retry-After 头');
ok(/账号已锁定，请联系管理员重置密码/.test(pySrc), '锁定提示需找管理员');
// 关键规则：冷却期内继续失败也必须累加计数，否则永远到不了 10 次
ok(/cnt = _login_record_fail\(req\.username, ip\)/.test(pySrc), '密码错误即累加计数');
ok(!/blocked, left, tip = _login_lock_state\(req\.username\)\s*\n\s*if blocked:/.test(pySrc),
  '冷却期内不直接拒绝（先验密码，冷却期正确密码要放行）');
ok(/if pwd_ok:/.test(pySrc), '先校验密码，冷却期内密码正确仍放行');
ok(/_login_record_success\(req\.username\)/.test(pySrc), '密码成功一次即清零');

// ============================================================
// 用例 4：管理员接口
// ============================================================
console.log('\n【用例4】管理员接口');
ok(/@app\.get\('\/api\/admin\/login-locks'\)/.test(pySrc), '锁定列表接口');
ok(/Depends\(require_admin\)/.test(pySrc), '管理员权限校验');
ok(/@app\.post\('\/api\/admin\/login-lock\/reset'\)/.test(pySrc), '重置锁定接口');
ok(/class LoginLockResetReq/.test(pySrc), '重置请求模型');
ok(/@app\.get\('\/api\/login\/lock-status'\)/.test(pySrc), '登录前状态查询接口');

// ============================================================
// 用例 5：登录页锁定提示与倒计时
// ============================================================
console.log('\n【用例5】登录页锁定提示');
ok(/id="lockBox"/.test(loginSrc), '锁定提示容器');
ok(/function renderLock\(state\)/.test(loginSrc), '锁定提示渲染');
ok(/⏳ 密码错误次数过多，请在 <b>'/.test(loginSrc), '冷却期显示剩余秒数');
ok(/🔒 密码错误次数过多，账号已锁定，请联系管理员重置密码。/.test(loginSrc), '永久锁定提示');
ok(/function pollLockState\(isTickEnd\)/.test(loginSrc), '轮询锁定状态');
ok(/lockPoll=setInterval\(.*pollLockState.*,5000\)/.test(loginSrc), '每 5 秒轮询一次');
ok(/u\.addEventListener\('input'/.test(loginSrc), '输入账号即查锁定状态');
ok(/retry_after/.test(loginSrc), '使用后端返回的剩余秒数');

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
