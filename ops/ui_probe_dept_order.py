#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断：读取 #tbDepts 的 DOM 顺序、computed order、网格轨道位置。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9349
BASE = 'http://127.0.0.1:8100'

PROBE = r"""
(function(){
  var box=document.getElementById('tbDepts');
  var out=[];
  Array.prototype.forEach.call(box.children,function(el,i){
    var cs=getComputedStyle(el);
    var b=el.getBoundingClientRect();
    out.push({
      domIdx:i+1,
      nthChildIdx:Array.prototype.indexOf.call(el.parentNode.children,el)+1,
      cls:(el.className||'').toString().slice(0,30),
      name:el.textContent.replace(/\s+/g,' ').trim().slice(0,10),
      order:cs.order,
      x:Math.round(b.x),y:Math.round(b.y)
    });
  });
  return JSON.stringify({
    children:out,
    gridDisplay:getComputedStyle(box).display,
    autoFlow:getComputedStyle(box).gridAutoFlow,
    cols:getComputedStyle(box).gridTemplateColumns
  });
})()
"""

async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_d%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1; mid = i
                await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';"
                     "document.getElementById('btn').click();")
            for _ in range(30):
                await asyncio.sleep(0.5)
                if await ev("!!document.getElementById('tbDepts')"):
                    break
            await asyncio.sleep(1.5)
            raw = await ev(PROBE)
            d = json.loads(raw)
            print('grid display=%s  autoFlow=%s  cols=%s'
                  % (d['gridDisplay'], d['autoFlow'], d['cols']))
            print('\n%-4s %-6s %-8s %-10s %-6s %s' % ('DOM', 'nth', 'order', 'name', 'x', 'y'))
            for c in d['children']:
                print('%-4s %-6s %-8s %-10s %-6s %s'
                      % (c['domIdx'], c['nthChildIdx'], c['order'], c['name'], c['x'], c['y']))
    finally:
        out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                              '/FORMAT:CSV'], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if 'cdp_profile_d%d' % PORT in line:
                pid = line.strip().split(',')[-1].strip()
                if pid.isdigit():
                    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)

if __name__ == '__main__':
    asyncio.run(main())
