// ============================================================
// 专项回归测试：个人界面（头像 / 个人状态 / 修改密码 / 顶栏状态栏）
// ============================================================
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const htmlSrc = fs.readFileSync(path.join(ROOT, 'src/static/index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(ROOT, 'src/app/app.py'), 'utf8');
const initSrc = fs.readFileSync(path.join(ROOT, 'src/app/init_db.py'), 'utf8');

let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✓ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

// ============================================================
// 用例 1：数据模型
// ============================================================
console.log('\n【用例1】users 表新增头像与个人状态');
ok(/avatar\s+TEXT NOT NULL DEFAULT ''/.test(initSrc), 'users 表有 avatar 列');
ok(/status_text\s+TEXT NOT NULL DEFAULT ''/.test(initSrc), 'users 表有 status_text 列');
ok(/if 'avatar' not in ucols:/.test(initSrc), '存量库自动补 avatar 列（幂等迁移）');
ok(/if 'status_text' not in ucols:/.test(initSrc), '存量库自动补 status_text 列（幂等迁移）');
ok(/ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''/.test(initSrc), '迁移语句为 ALTER ADD COLUMN');
ok(/ALTER TABLE users ADD COLUMN status_text TEXT NOT NULL DEFAULT ''/.test(initSrc), '迁移语句为 ALTER ADD COLUMN');

// ============================================================
// 用例 2：接口
// ============================================================
console.log('\n【用例2】个人资料与改密接口');
ok(/@app\.post\('\/api\/profile'\)/.test(pySrc), '有 POST /api/profile');
ok(/@app\.post\('\/api\/profile\/password'\)/.test(pySrc), '有 POST /api/profile/password');
ok(/class ProfileReq\(BaseModel\)/.test(pySrc), 'ProfileReq 请求模型');
ok(/class PasswordChangeReq\(BaseModel\)/.test(pySrc), 'PasswordChangeReq 请求模型');
ok(/_check_image_data_url\(req\.avatar\)/.test(pySrc), '头像复用既有图片校验（类型 + 512KB 上限）');
ok(/原密码不正确/.test(pySrc), '改密码校验原密码');
ok(/新密码至少 6 位/.test(pySrc), '新密码长度校验');
ok(/新密码不能与原密码相同/.test(pySrc), '新旧密码相同则拒绝');
ok(/hash_pw\(new\)/.test(pySrc), '新密码按哈希存储');
ok(/UPDATE users SET avatar=\?, photo=\?, status_text=\? WHERE username=\?/.test(pySrc),
  '个人资料按当前登录账号写入（只能改自己的）');
ok(/'avatar': avatar, 'photo': photo, 'status_text': status_text/.test(pySrc), '/api/me 返回头像、照片与个人状态');
ok(/audit_log\(username, client_ip\(request\), 'profile_update'/.test(pySrc), '资料修改写审计日志');
ok(/audit_log\(username, client_ip\(request\), 'password_change'/.test(pySrc), '改密码写审计日志');

// ============================================================
// 用例 3：前端个人界面
// ============================================================
console.log('\n【用例3】个人界面弹窗');
ok(/id="profileModal"/.test(htmlSrc), '存在个人界面弹窗');
ok(/id="profileAvatarBox"/.test(htmlSrc), '有头像上传区');
ok(/id="profileAvatarFile"/.test(htmlSrc), '有头像文件选择 input');
ok(/id="profileStatus"/.test(htmlSrc), '有个人状态文本输入');
ok(/id="profileOldPwd"/.test(htmlSrc) && /id="profileNewPwd"/.test(htmlSrc) && /id="profileNewPwd2"/.test(htmlSrc),
  '改密码三个输入框齐全');
ok(/function openProfileModal\(\)/.test(htmlSrc), '提供 openProfileModal');
ok(/function saveProfile\(\)/.test(htmlSrc), '提供 saveProfile');
ok(/function submitChangePassword\(\)/.test(htmlSrc), '提供 submitChangePassword');
ok(/function pickProfileAvatar\(inp\)/.test(htmlSrc), '提供头像文件选择处理');
ok(/function renderProfileAvatarBox\(\)/.test(htmlSrc), '提供头像预览渲染');
ok(/function renderMyProfile\(\)/.test(htmlSrc), '提供顶栏头像/状态统一渲染');
ok(/ME\.avatar=PROFILE_AVATAR; ME\.photo=PROFILE_PHOTO; ME\.status_text=status_text;/.test(htmlSrc), '保存后同步 ME 并刷新顶栏');
ok(/两次输入的新密码不一致/.test(htmlSrc), '前端校验两次新密码一致');
ok(/新密码至少 6 位/.test(htmlSrc), '前端校验新密码长度');
ok(/请输入原密码/.test(htmlSrc), '前端校验原密码非空');
ok(/onclick="openProfileModal\(\)"/.test(htmlSrc), '顶栏用户区为入口');

// ============================================================
// 用例 4：顶栏状态栏
// ============================================================
console.log('\n【用例4】顶栏个人状态栏');
ok(/id="myStatusBar"/.test(htmlSrc), '存在状态栏容器');
ok(/id="myStatusText"/.test(htmlSrc), '存在状态栏文案元素');
ok(/class="my-status-bar"/.test(htmlSrc), '状态栏有独立样式类');
ok(/id="headerAvatar"/.test(htmlSrc), '顶栏有头像元素');
ok(/class="header-avatar"/.test(htmlSrc), '头像有独立样式类');
ok(/renderMyProfile\(\);   \/\/ 顶栏头像 \+ 个人状态栏/.test(htmlSrc), 'init 时渲染头像与状态栏');
ok(/bar\.hidden=!st;/.test(htmlSrc), '无个人状态时状态栏隐藏');
ok(/av\.hidden=false/.test(htmlSrc), '有头像时顶栏显示头像');
// 状态栏必须紧跟页眉（不能插到部门主页 grid 区块里，否则被挤到奇怪位置）
const hdrIdx = htmlSrc.indexOf('</header>');
const barIdx = htmlSrc.indexOf('id="myStatusBar"');
const deptIdx = htmlSrc.indexOf('id="deptHomeWrap"');
ok(hdrIdx > 0 && barIdx > hdrIdx && barIdx - hdrIdx < 400, '状态栏紧跟页眉之后');
ok(deptIdx < 0 || barIdx < deptIdx || htmlSrc.indexOf('my-status-bar') < deptIdx,
  '状态栏不在部门主页 grid 区块内部');

// ============================================================
// 用例 5：数据安全
// ============================================================
console.log('\n【用例5】安全与数据约束');
ok(!/password_plain/.test(pySrc), '未使用 password_plain 明文列');
ok(/verify_pw\(old, u\[0\]\['password_hash'\]\)/.test(pySrc), '改密码用哈希校验，非明文比对');
ok(/status_text=.{0,40}\[:120\]/.test(pySrc) || /\[:120\]/.test(pySrc), '个人状态长度受限（120 字）');
ok(/PROFILE_MAX_IMG_BYTES=512\*1024/.test(htmlSrc), '前端图片大小上限与后端一致（512KB）');

// ============================================================
// 用例 6：顶栏显示「姓名(账号)」
// ============================================================
console.log('\n【用例6】顶栏显示姓名(账号)');
ok(/def _member_display_name\(username: str\) -> str:/.test(pySrc), '后端提供账号→姓名解析函数');
ok(/'display_name': display_name/.test(pySrc), '/api/me 返回 display_name');
ok(/SELECT name FROM team_members WHERE account=\? LIMIT 1/.test(pySrc),
  '姓名取自 team_members.account 绑定关系');
ok(/function meDisplayLabel\(\)/.test(htmlSrc), '前端提供顶栏文案组装函数');
ok(/dn \? \('\S*' \+ dn \+ '\(' \+ ME\.username \+ '\)'\)/.test(htmlSrc) ||
   /dn\?'[^']*'\s*\+\s*'\('/.test(htmlSrc) ||
   /\+\s*'\('\+ME\.username\+'\)'/.test(htmlSrc),
  '有姓名时拼成「姓名(账号)」');
ok(/getElementById\('userName'\)\.textContent=meDisplayLabel\(\)/.test(htmlSrc),
  '顶栏用户名使用 meDisplayLabel()');
ok(/id="profileTitle"/.test(htmlSrc), '个人界面标题有独立元素');
ok(/profileTitle/.test(htmlSrc) && /个人界面/.test(htmlSrc), '个人界面标题带姓名信息');
ok(/hu\.title=/.test(htmlSrc), '顶栏 hover 提示动态更新（带姓名）');
ok(/👤 '\+ME\.username/.test(htmlSrc), '未绑定姓名时回退为只显示账号');

// ============================================================
// 用例 7：个人照片（形象照）
// ============================================================
console.log('\n【用例7】个人照片上传');
ok(/photo\s+TEXT NOT NULL DEFAULT ''/.test(initSrc), 'users 表新增 photo 列（个人照片）');
ok(/ALTER TABLE users ADD COLUMN photo TEXT NOT NULL DEFAULT ''/.test(initSrc),
  'photo 列有幂等迁移');
ok(/MAX_PHOTO_BYTES = 2 \* 1024 \* 1024/.test(pySrc), '个人照片独立上限 2MB');
ok(/def _check_image_data_url\(data_url: str, max_bytes: int = None\)/.test(pySrc),
  '图片校验支持按用途区分上限');
ok(/photo: str = ''/.test(pySrc), 'ProfileReq 含 photo 字段');
ok(/_check_image_data_url\(req\.photo, MAX_PHOTO_BYTES\)/.test(pySrc),
  '照片按 2MB 上限校验');
ok(/UPDATE users SET avatar=\?, photo=\?, status_text=\?/.test(pySrc), '保存资料时写入 photo');
ok(/'photo': photo/.test(pySrc), '/api/me 返回 photo');
ok(/id="profilePhotoBox"/.test(htmlSrc), '个人界面有照片上传区');
ok(/id="profilePhotoFile"/.test(htmlSrc), '照片有文件选择控件');
ok(/class="profile-photo-clear"/.test(htmlSrc), '照片有「清除」按钮');
ok(/function renderProfilePhotoBox\(\)/.test(htmlSrc), '照片预览渲染函数');
ok(/function clearProfilePhoto\(ev\)/.test(htmlSrc), '清除照片函数（阻止冒泡避免触发上传）');
ok(/function compressProfilePhoto\(file\)/.test(htmlSrc), '照片自动压缩（canvas）');
ok(/PROFILE_PHOTO_MAX_EDGE=1200/.test(htmlSrc), '压缩后最长边 1200px');
ok(/cv\.toDataURL\('image\/jpeg',0\.85\)/.test(htmlSrc), '压缩输出 JPEG 质量 0.85');
ok(/photo:PROFILE_PHOTO/.test(htmlSrc), '保存资料时提交 photo');
ok(/ME\.photo=PROFILE_PHOTO/.test(htmlSrc), '保存后同步 ME.photo');
ok(/PROFILE_PHOTO=ME\.photo\|\|''/.test(htmlSrc), '打开弹窗时读回已存照片');

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
