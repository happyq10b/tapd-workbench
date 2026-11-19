# -*- coding: utf-8 -*-
"""T-0175 登录页小精灵设置：API（设置/下发/权限）+ CDP（菜单/弹窗/登录页生效）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8100'
PORT = 9480
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def setup():
    global _ORIG_PET, _MAX_SH_BEFORE
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    if not c.execute("SELECT 1 FROM users WHERE username='__t_pet_v'").fetchone():
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_pet_v',?,'viewer','__t_none_x')",
                  (hash_pw('Xx12345678'),))
    # 真实 login_pet 备份 + 快照段水位（T-0177：不再无条件复位/删快照——曾把真实固定配置清成随机）
    row = c.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone()
    _ORIG_PET = row[0] if row else ''
    _MAX_SH_BEFORE = c.execute("SELECT COALESCE(MAX(id),0) FROM state_history WHERE scope='login_pet'").fetchone()[0]
    c.commit()
    c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM users WHERE username='__t_pet_v'")
    c.execute("INSERT INTO app_settings (key, value) VALUES ('login_pet',?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_ORIG_PET,))
    c.execute("DELETE FROM state_history WHERE scope='login_pet' AND id>?", (_MAX_SH_BEFORE,))
    c.commit()
    c.close()
    print('清理：viewer 夹具已删，login_pet 已恢复原值(%r)，测试快照已清' % _ORIG_PET, flush=True)

def api(tk, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

async def main():
    setup()
    tk_admin = make_token('admin')
    tk_v = make_token('__t_pet_v')

    print('===== API 测试 =====', flush=True)
    st, d = api(tk_admin, 'POST', '/api/admin/pet', {'mode': 'fixed', 'no': 25})
    ok(st == 200 and d.get('ok'), '超管保存固定形象编号 25（T-0177 返回 {ok:true}）')
    st, d = api(tk_admin, 'GET', '/api/admin/pet')
    ok(st == 200 and d.get('mode') == 'fixed' and d.get('no') == 25, '读取回显 fixed/25')
    st, d = api(tk_v, 'GET', '/api/admin/pet')
    ok(st == 403, '非超管读取 → 403')
    st, d = api(tk_v, 'POST', '/api/admin/pet', {'mode': 'fixed', 'no': 3})
    ok(st == 403, '非超管保存 → 403')
    st, d = api(tk_admin, 'POST', '/api/admin/pet', {'mode': 'fixed', 'no': 400})
    ok(st == 400, '编号 400 超界 → 400')
    st, d = api(tk_admin, 'POST', '/api/admin/pet', {'mode': 'bogus'})
    ok(st == 400, '非法模式 → 400')

    c = sqlite3.connect(DB)
    pet = c.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone()[0]
    snap = c.execute("SELECT COUNT(*) FROM state_history WHERE scope='login_pet'").fetchone()[0]
    c.close()
    ok(pet.startswith('{') and json.loads(pet) == {'mode': 'fixed', 'kind': 'builtin', 'no': 25},
       '落库 app_settings.login_pet=T-0177 JSON 固定内置 25')
    ok(snap >= 1, '状态快照已记录（scope=login_pet，%d 条）' % snap)

    import urllib.request as u2
    pub = json.loads(u2.urlopen(BASE + '/api/login/notice', timeout=10).read())
    ok(pub.get('pet_url') == '/pet/25', '公开端点下发 pet_url=/pet/25（登录页可取）')

    st, d = api(tk_admin, 'POST', '/api/admin/pet', {'mode': 'random'})
    ok(st == 200 and d.get('ok'), '切回随机模式')
    pub = json.loads(u2.urlopen(BASE + '/api/login/notice', timeout=10).read())
    ok(str(pub.get('pet_url', '')).startswith('/pet/') and '/pet/up/' not in pub.get('pet_url', ''),
       '随机模式下发 pet_url=/pet/<随机内置编号>（登录页随机）')

    print('===== CDP 界面测试 =====', flush=True)
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0175')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    async def login_as(token, uname):
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2.5)
        cookie = 'tk=%s; path=/; SameSite=Lax' % token
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(60):
            await asyncio.sleep(0.5)
            r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='%s'" % uname)
            if r is True:
                break
        await asyncio.sleep(1.5)

    async def wait_guard_idle():
        for _ in range(40):
            r = await ev("!document.getElementById('saveGuard')&&SG_N===0")
            if r is True:
                return True
            await asyncio.sleep(0.5)
        return False

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')

    print('【① 超管：更多菜单含「小精灵设置」】', flush=True)
    await login_as(make_token('admin'), 'admin')
    r1 = await ev("(function(){const b=document.getElementById('petBtn');return {shown:b&&b.style.display!=='none'};})()")
    ok(r1.get('shown'), 'petBtn 对超管可见')

    print('【② 打开设置弹窗：网格 386 项 + 回显随机模式】', flush=True)
    await ev("openPetSettingModal()")
    await asyncio.sleep(1.5)
    r2 = await ev("""(function(){
      const g=document.getElementById('petGrid');
      const mode=document.querySelector('input[name=petMode]:checked');
      return {btns:g?g.querySelectorAll('button[data-no]').length:0, mode:mode?mode.value:null,
              modalShown:document.getElementById('petSettingModal').style.display};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('btns') == 386, '精灵网格渲染 386 个可选形象')
    ok(r2.get('mode') == 'random', '回显当前模式=随机')

    print('【③ 选编号 25 → 保存 → 落库 + 公开端点生效】', flush=True)
    await ev("(function(){document.querySelector('#petGrid button[data-no=\"25\"]').click();})()")
    await asyncio.sleep(0.3)
    await ev("document.getElementById('petSaveBtn').click()")
    ok(await wait_guard_idle(), '保存守卫释放')
    await asyncio.sleep(1)
    pub = json.loads(urllib.request.urlopen(BASE + '/api/login/notice', timeout=10).read())
    ok(pub.get('pet_url') == '/pet/25', '保存后公开端点下发 pet_url=/pet/25')
    toasts = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    ok(any('固定' in t for t in (toasts or [])), '保存 toast 提示固定生效')

    print('【④ 登录页显示固定形象 25】', flush=True)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(3)
    r4 = await ev("(function(){const i=document.getElementById('petImg');return i?i.getAttribute('src'):null;})()")
    print('  petImg.src =', r4, flush=True)
    ok(r4 and r4.endswith('/pet/25'), '登录页固定显示编号 25')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(3)
    r4b = await ev("(function(){const i=document.getElementById('petImg');return i?i.getAttribute('src'):null;})()")
    ok(r4b and r4b.endswith('/pet/25'), '再次打开登录页仍显示 25（固定不随机）')

    print('【⑤ 回显 fixed/25（③ 的保存结果）→ 切随机 → 登录页随机】', flush=True)
    await login_as(make_token('admin'), 'admin')
    await ev("openPetSettingModal()")
    await asyncio.sleep(1.5)
    r5 = await ev("""(function(){
      const b25=document.querySelector('#petGrid button[data-no=\"25\"]');
      const sel=b25?(b25.style.borderColor==='var(--primary)'||b25.style.boxShadow.indexOf('0.25')>=0):null;
      return {sel:sel, mode:document.querySelector('input[name=petMode]:checked').value};
    })()""")
    print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
    ok(r5.get('mode') == 'fixed' and r5.get('sel') is True, '弹窗回显 fixed/25（③ 的保存结果，编号高亮）')
    await ev("(function(){document.querySelector('input[name=petMode][value=random]').checked=true;document.getElementById('petSaveBtn').click();})()")
    ok(await wait_guard_idle(), '保存守卫释放')
    await asyncio.sleep(1)
    pub = json.loads(urllib.request.urlopen(BASE + '/api/login/notice', timeout=10).read())
    ok(str(pub.get('pet_url', '')).startswith('/pet/') and '/pet/up/' not in pub.get('pet_url', ''),
       '随机模式 pet_url=/pet/<随机内置编号>')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(3)
    r5b = await ev("(function(){const i=document.getElementById('petImg');return i?i.getAttribute('src'):null;})()")
    print('  petImg.src =', r5b, flush=True)
    ok(r5b and '/pet/' in r5b and not r5b.endswith('/pet/25'), '登录页恢复随机（非固定 25）')

    print('【⑥ 非超管：菜单项隐藏】', flush=True)
    await login_as(make_token('__t_pet_v'), '__t_pet_v')
    r6 = await ev("(function(){const b=document.getElementById('petBtn');return {exists:!!b, hidden:b?b.style.display==='none':null};})()")
    ok(r6.get('exists') and r6.get('hidden'), '非超管看不到「小精灵设置」菜单项')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    cleanup()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
