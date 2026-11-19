# -*- coding: utf-8 -*-
"""#115 UI 实测：姓名列/角色中文/弹窗动效（closing 类 + openModal 清理）。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d115')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9483', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = 'http://127.0.0.1:9483'
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

        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)

        print('【A】在线用户：姓名列 + 角色中文')
        await ev("openModal('onlineModal');openOnlineModal();")
        await asyncio.sleep(1.2)
        heads = await ev("[...document.querySelectorAll('#onlineModal th')].map(x=>x.textContent.trim())")
        print('  表头:', heads)
        ok('姓名' in (heads or []), '表头含「姓名」列')
        rows = await ev("(function(){return [...document.querySelectorAll('#onlineList tr')].map(tr=>[...tr.querySelectorAll('td,th')].map(td=>td.textContent.trim()))})()")
        ok(len(rows) >= 2, '列表渲染（%s 行）' % len(rows))
        data_rows = rows[1:] if rows else []
        roles = [r[2] for r in data_rows if len(r) > 2]
        ok(all(x in ('管理员', '可编辑', '只读') for x in roles), '角色列全为中文（%s）' % roles)
        names = [r[0] for r in data_rows if len(r) > 0]
        ok(all(n for n in names), '姓名列有值（%s；未绑定为 —）' % names)
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d115_online.png', 'wb').write(__import__('base64').b64decode(shot['data']))

        print('【B】弹窗动效')
        await ev("closeModal('onlineModal');")
        closing = await ev("document.getElementById('onlineModal').classList.contains('closing')")
        ok(closing is True, 'closeModal → 立即加 closing 类（淡出中）')
        await asyncio.sleep(0.3)
        hidden = await ev("document.getElementById('onlineModal').style.display==='none'")
        ok(hidden is True, '170ms 后隐藏完成')
        # 重开（含 170ms 窗口内重开防隐形）
        await ev("openModal('onlineModal');openOnlineModal();")
        await asyncio.sleep(0.05)
        visible = await ev("(function(){const m=document.getElementById('onlineModal');"
                           "return m.style.display==='flex' && getComputedStyle(m).opacity!=='0'})()")
        ok(visible is True, '170ms 窗口内重开 → closing 被清，弹窗正常显示（防隐形）')
        await ev("closeModal('onlineModal');")

    subprocess.Popen(['taskkill', '/F', '/IM', 'chrome.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
