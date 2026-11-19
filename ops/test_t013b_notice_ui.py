# -*- coding: utf-8 -*-
"""T-013b CDP 实测：精灵阴影+紧凑间距 / 通知栏渲染 / 个人界面标签按角色切换"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9463
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS = []
NOTICE = '11月20日 22:00 系统升级，届时暂停登录，请提前保存工作'


def ok(cond, msg):
    PASS.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


# 夹具：viewer 账号（非超管标签验证用）
c = sqlite3.connect(DB)
c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES ('__t_notice_v','x','viewer')")
c.execute("INSERT INTO app_settings (key, value) VALUES ('login_notice',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (NOTICE,))
c.execute("UPDATE users SET status_text='__t_我的状态__' WHERE username='__t_notice_v'")
c.execute("INSERT INTO team_members (id,name,workgroups,account) VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_通知成员__','','__t_notice_v')")
c.commit(); c.close()

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t013b')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--window-size=1280,800', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
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
        seq[0] += 1; mid = seq[0]
        fut = asyncio.get_event_loop().create_future(); pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return None
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')

    print('【① 登录页：通知栏显示超管配置 + 精灵阴影/紧凑间距】', flush=True)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    r1 = await ev("""(function(){
      const bar=document.getElementById('noticeBar'), pet=document.getElementById('pet');
      const pcs=getComputedStyle(pet);
      const pr=pet.getBoundingClientRect();
      const cr=document.querySelector('.card').getBoundingClientRect();
      return {bar:bar.textContent, flt:pcs.filter, off:Math.round(pr.left-cr.left), bottomShown:!!pet,
              centered:getComputedStyle(bar).textAlign, ws:getComputedStyle(bar).whiteSpace};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1 and r1.get('bar') == NOTICE, '通知栏显示超管配置的登入通知')
    ok(r1 and 'drop-shadow' in (r1.get('flt') or ''), '精灵带 drop-shadow 阴影：%s' % r1.get('flt'))
    ok(r1 and r1.get('off') == 30, '精灵右移（距卡片左 30px，紧靠文字区）：%s' % r1.get('off'))
    ok(r1 and r1.get('centered') in ('left', 'start') and r1.get('ws') == 'normal', '通知栏文字左对齐（紧随精灵）且允许换行')

    print('【② 超管登录 → 个人界面显示「登入通知」标签并回显】', flush=True)
    cookie = "tk=%s; path=/; SameSite=Lax" % make_token('admin')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True; break
    ok(ok_login, 'admin 注入登录成功')
    await asyncio.sleep(1.5)
    await ev("openProfileModal()")
    await asyncio.sleep(0.8)
    r2 = await ev("""(function(){
      return {lbl:document.getElementById('profileStatusLbl').textContent.trim().slice(0,4),
              val:document.getElementById('profileStatus').value};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2 and r2.get('lbl') == '登入通知', '超管标签为「登入通知」')
    ok(r2 and r2.get('val') == NOTICE, '回显已配置的通知内容')
    await ev("document.getElementById('profileStatus').value='__t_新通知__'")
    serr = await ev("saveProfile.call(null).then(function(){return 'OK';},function(e){return 'REJ:'+(e&&e.message||e);})", aw=True)
    await asyncio.sleep(1)
    tw = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    print('   save(超管):', serr, '| toasts:', json.dumps(tw, ensure_ascii=False), flush=True)
    await asyncio.sleep(0.5)
    srv = await ev("(async function(){const d=await api('/api/login/notice');return d.notice;})()", aw=True)
    row = sqlite3.connect(DB).execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()
    print('   服务端通知:', repr(srv), '| sqlite直读:', repr(row), flush=True)
    ok(row and row[0] == '__t_新通知__', '超管界面保存 → 落库为通知')
    row2 = sqlite3.connect(DB).execute("SELECT status_text FROM users WHERE username='admin'").fetchone()
    ok(row2[0] != '__t_新通知__', '超管个人状态列未被顶替')

    print('【③ 非超管登录 → 标签仍为「个人状态」，保存写 status_text】', flush=True)
    cookie = "tk=%s; path=/; SameSite=Lax" % make_token('__t_notice_v')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__t_notice_v'")
        if r is True:
            ok_login = True; break
    ok(ok_login, 'viewer 注入登录成功')
    await asyncio.sleep(1.5)
    await ev("openProfileModal()")
    await asyncio.sleep(0.8)
    r3 = await ev("""(function(){
      return {lbl:document.getElementById('profileStatusLbl').textContent.trim().slice(0,4),
              val:document.getElementById('profileStatus').value};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3 and r3.get('lbl') == '个人状态', '非超管标签保持「个人状态」')
    ok(r3 and r3.get('val') == '__t_我的状态__', '回显个人状态（非通知）')
    await ev("document.getElementById('profileStatus').value='__t_新状态__'")
    serr = await ev("saveProfile.call(null).then(function(){return 'OK';},function(e){return 'REJ:'+(e&&e.message||e);})", aw=True)
    await asyncio.sleep(1)
    tw = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    print('   save(超管v):', serr, '| toasts:', json.dumps(tw, ensure_ascii=False), flush=True)
    await asyncio.sleep(0.5)
    srv2 = await ev("(async function(){const d=await api('/api/me');return d.status_text;})()", aw=True)
    row = sqlite3.connect(DB).execute("SELECT status_text FROM users WHERE username='__t_notice_v'").fetchone()
    print('   服务端状态:', repr(srv2), '| sqlite直读:', repr(row), flush=True)
    ok(row[0] == '__t_新状态__', '非超管保存 → 写个人状态')
    row2 = sqlite3.connect(DB).execute("SELECT value FROM app_settings WHERE key='login_notice'").fetchone()
    ok(row2 and row2[0] == '__t_新通知__', '通知未被非超管改动')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM app_settings WHERE key='login_notice'")
    c.execute("DELETE FROM team_members WHERE account='__t_notice_v'")
    c.execute("DELETE FROM users WHERE username='__t_notice_v'")
    c.execute("UPDATE users SET status_text='' WHERE username='admin'")
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM app_settings WHERE key='login_notice'").fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t_notice%'").fetchone()[0]
    print('夹具残留检查: settings=%d users=%d' % (n1, n2), flush=True)
    c.close()
n = sum(PASS)
print('结果: PASS=%d/%d' % (n, len(PASS)), flush=True)
sys.exit(0 if n == len(PASS) else 1)
