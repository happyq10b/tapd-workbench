# -*- coding: utf-8 -*-
"""#93 补验：勾选代办 → 外部目录同步（DOM 驱动）"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d93c')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=9412', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9412/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9412/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)
        await ev("(function(){const b=(ME.boards||[])[0];if(b)pickBoard(b.board_id);})()")
        await asyncio.sleep(2.5)

        # 找第一张卡的 card_id（从标题 onclick 提取）
        cid = await ev("(function(){const t=document.querySelector('.item-card .item-title');"
                       "if(!t)return null;const m=t.getAttribute('onclick').match(/'([^']+)'/);"
                       "return m?m[1]:null;})()")
        assert cid, '找不到卡片'
        print('card_id =', cid)

        def row_mini_js(c):
            js = ('(function(){const chev=document.querySelector(".item-chev[data-cid=\\"__CID__\\"]");'
                  'const row=chev?chev.closest(".item-card"):null;'
                  'const mini=row?row.querySelector(".slot-subtask .st-mini"):null;'
                  'return mini?mini.textContent.trim():"";})()')
            return js.replace('__CID__', c)

        before = await ev(row_mini_js(cid))
        print('目录代办(前):', repr(before))
        await ev("openEdit('%s');" % cid)
        await asyncio.sleep(1.2)
        has = await ev("document.querySelectorAll('#e_subtask_list .st-item').length")
        if not has:
            await ev("document.getElementById('e_subtask_new').value='__d93_probe';addSubtask();")
            await asyncio.sleep(1.5)
        r2 = await ev("(function(){const cb=document.querySelector("
                      "'#e_subtask_list input[type=checkbox]:not(:checked)');"
                      "if(!cb) return {none:true}; cb.click(); return {clicked:true};})()")
        print('勾选:', r2)
        await asyncio.sleep(2.5)
        after = await ev(row_mini_js(cid))
        print('目录代办(后):', repr(after))
        assert before != after, '目录未同步！'
        assert after.startswith('【代办：') and after.endswith('】'), '格式不对: ' + after
        print('PASS 勾选后目录同步：%s → %s（新格式确认）' % (before, after))
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d93_todo_sync.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图已存:', out)
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
