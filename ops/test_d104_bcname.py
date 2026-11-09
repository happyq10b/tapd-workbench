# -*- coding: utf-8 -*-
"""#104 看板名左对齐 + 两行截断 UI 实测"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d104')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9457',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9457/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9457/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__err__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 720, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        await ev("openBoardConfigModal(); 'x'", aw=True)
        await asyncio.sleep(2)
        r = await ev("""(function(){
          const names=[...document.querySelectorAll('#bcList .bc-name')];
          if(!names.length) return {none:true};
          const cs=getComputedStyle(names[0]);
          const long=names.find(x=>x.textContent.length>=14);
          const lcs=long?getComputedStyle(long):null;
          return {count:names.length,
                  clamp:lcs?lcs.webkitLineClamp:'', orient:lcs?lcs.webkitBoxOrient:'',
                  ovf:lcs?(lcs.overflow||lcs.overflowY):'', ta:lcs?lcs.textAlign:'',
                  longName:long?long.textContent.slice(0,20):'',
                  longH:long?long.clientHeight:0, lineH:lcs?parseFloat(lcs.lineHeight):0};
        })()""")
        print('探针:', r)
        ok(r.get('count', 0) > 3, '看板列表渲染（%s 个）' % r.get('count'))
        ok(r.get('clamp') == '2' and r.get('orient') == 'vertical', 'line-clamp=2（两行截断）')
        ok(r.get('ta') == 'start' or r.get('ta') == 'left', '左对齐（text-align=%s）' % r.get('ta'))
        ok(r.get('longH', 0) > 0 and r.get('lineH', 1) > 0 and r.get('longH') <= r.get('lineH') * 2 + 2,
           '长名高度 ≤ 2 行（%s ≤ %s）' % (r.get('longH'), round(r.get('lineH', 0) * 2)))
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d104_bcname.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)
    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
