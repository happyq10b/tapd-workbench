# -*- coding: utf-8 -*-
"""#114 会话级登录实测（单标签简化版）：
A. 登录 → token 写会话 cookie + localStorage 清空
B. 刷新页面（同标签）→ 保持登录（cookie 复用）
C. 清 cookie（等价浏览器重启后 session cookie 消失）→ 强制回登录页
D. logout → cookie 清空
E. 老用户迁移：localStorage 残留 tk → 自动迁到 cookie 并清掉
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d114b')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                             '--no-first-run', '--remote-debugging-port=9479', '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = 'http://127.0.0.1:9479'
    for _ in range(60):
        try:
            urllib.request.urlopen(cdp + '/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen(cdp + '/json', timeout=5).read())
    ws_url = [t for t in targets if t.get('type') == 'page'][0]['webSocketDebuggerUrl']

    async with websockets.connect(ws_url, max_size=30*1024*1024) as w:
        i = 0
        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid: return msg.get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__err__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
            return r.get('result', {}).get('value')

        print('【E-pre】老用户迁移：预置真实 token 到 localStorage → 打开首页应迁到 cookie')
        # 用真实登录拿有效 token（老用户场景 = localStorage 里是有效 token）
        _lr = urllib.request.Request(BASE + '/api/login', method='POST',
            data=json.dumps({'username': 'admin', 'password': 'At159357'}).encode(),
            headers={'Content-Type': 'application/json'})
        _tok = json.loads(urllib.request.urlopen(_lr, timeout=10).read())['token']
        # ⚠️ 先导航到站点（about:blank 的 opaque origin localStorage 与站点不互通）
        await send('Page.enable')
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(1.5)
        await ev("localStorage.setItem('tk','" + _tok + "')")   # token 为 base64+点，无引号可安全拼接
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(2.5)
        r = await ev("(function(){return {ck:/tk=/.test(document.cookie), ls:localStorage.getItem('tk'),"
                     " logged:(typeof ME!=='undefined'&&!!ME&&ME.username)||null}})()")
        print('  迁移结果:', r)
        ok(r.get('ck') is True, '旧 localStorage token 已迁到会话 cookie（老用户无缝过渡）')
        ok(r.get('logged') == 'admin', '迁移后老用户保持登录（有效 token 过渡）')
        ok(r.get('ls') in (None, ''), 'localStorage 已清（之后浏览器重启必重登）')

        print('【A】登录 → 会话 cookie')
        await ev("location.href='/login'")
        await asyncio.sleep(1.5)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        await asyncio.sleep(2)
        r = await ev("(function(){return {ck:/tk=/.test(document.cookie), ls:localStorage.getItem('tk'),"
                     " logged:(typeof ME!=='undefined'&&!!ME&&ME.username)||null}})()")
        print('  登录后:', r)
        ok(r.get('ck') is True, 'token 写入会话 cookie')
        ok(r.get('ls') in (None, ''), 'localStorage 无 token')
        ok(r.get('logged') == 'admin', '登录成功')

        print('【B】刷新页面（同标签）→ 保持登录')
        await ev("location.href='/'")
        await asyncio.sleep(2.5)
        r = await ev("(typeof ME!=='undefined'&&!!ME&&ME.username)||null")
        ok(r == 'admin', '刷新后保持登录（cookie 复用）')

        print('【C】清 cookie（= 浏览器重启后 session cookie 消失）→ 强制重登')
        await ev("document.cookie='tk=; path=/; Max-Age=0'")
        await ev("location.href='/'")
        await asyncio.sleep(2)
        r = await ev("!!document.getElementById('u')")
        ok(r is True, '回到登录页（不能自动登录）✓')

        print('【D】logout 清理')
        # 重新登录后再退出，验证 logout 清 cookie
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        await asyncio.sleep(2)
        await ev("logout();")
        await asyncio.sleep(1)
        r = await ev("/tk=/.test(document.cookie)")
        ok(r is False, 'logout 清空会话 cookie')

    proc.kill()   # 直接杀进程（session cookie 随进程消失，真实语义自然成立）
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
