# -*- coding: utf-8 -*-
"""#111 UI 实测：更多菜单入口显隐（仅超管）+ 弹窗渲染 + 下线按钮。"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'

RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d111')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9470', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9470/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9470/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30*1024*1024) as w:
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

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)

        print('【A】入口显隐（超管）')
        r = await ev("(function(){const b=document.getElementById('onlineBtn');return b?{shown:b.style.display!=='none',txt:b.textContent.trim()}:null})()")
        ok(bool(r) and r.get('shown') is True, '超管登录 → onlineBtn 可见（%s）' % (r or {}).get('txt'))
        # 打开更多菜单看按钮在菜单里
        await ev("toggleHeaderMore(new Event('x'),'headerMoreMenu');")
        vis = await ev("!document.getElementById('headerMoreMenu').hidden && !!document.getElementById('onlineBtn')")
        ok(vis is True, '按钮位于【更多】菜单内且菜单可展开')
        await ev("toggleHeaderMore(new Event('x'),'headerMoreMenu');")

        print('【B】弹窗渲染')
        await ev("openOnlineModal();")
        await asyncio.sleep(1.2)
        disp = await ev("document.getElementById('onlineModal').style.display")
        ok(disp == 'flex', '弹窗打开（display=flex）')
        rows = await ev("document.querySelectorAll('#onlineList tr').length")
        ok(rows >= 1, '列表渲染（%s 行）' % rows)
        # 当前唯一登录记录 = admin 自己 → 应显示「当前账号」而非下线按钮（防自踢）
        has_kick = await ev("[...document.querySelectorAll('#onlineList button')].some(b=>b.textContent.includes('强制下线'))")
        ok(has_kick is False, 'admin 自己那行无「强制下线」按钮（防自踢）')
        self_cell = await ev("[...document.querySelectorAll('#onlineList td')].some(td=>td.textContent.includes('当前账号'))")
        ok(self_cell is True, 'admin 自己那行显示「当前账号」')
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d111_online.png', 'wb').write(base64.b64decode(shot['data']))

        print('【C】非超管入口隐藏（临时账号 __t111）')
        # dsy/zhangsan 无已知密码 → 用超管 API 临时建一个已知密码账号，测完删除
        await ev("closeModal('onlineModal');")
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)  # 回登录页清理状态
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)
        cr = await ev("(async function(){try{await api('/api/admin/users',{method:'POST',body:JSON.stringify({username:'__t111',password:'T111probe',role:'viewer'})});return 'created'}catch(e){return 'err:'+e.message}})()", aw=True)
        print('  临时账号:', cr)
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='__t111';document.getElementById('p').value='T111probe';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)
        hidden = await ev("(function(){const b=document.getElementById('onlineBtn');return b?(b.style.display==='none'||!b.offsetParent):'no-btn'})()")
        ok(hidden is True, '普通管理账号（dsy）登录 → onlineBtn 隐藏')
        r2 = await ev("(function(){openOnlineModal();return document.getElementById('onlineModal').style.display})()")
        ok(r2 == 'none', '非超管直接调 openOnlineModal → 弹窗不打开（前置校验拦截）')
        # 清理临时账号
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)
        dl = await ev("(async function(){try{await api('/api/admin/users/__t111',{method:'DELETE'});return 'deleted'}catch(e){return 'err:'+e.message}})()", aw=True)
        print('  清理临时账号:', dl)

    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
