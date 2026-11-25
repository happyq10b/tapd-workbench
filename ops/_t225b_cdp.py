# -*- coding: utf-8 -*-
"""T-225b CDP：综合看板按钮多选/单选/未选三场景（一次性）"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token
TOK = make_token('admin')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9543

async def main():
    profile = os.path.join(os.environ.get('TEMP','.'), 'cdp_t225b_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                             '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                    json.loads(r.read()); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0
            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid: return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
                return r.get('result', {}).get('value')
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': 'http://127.0.0.1:8100/login'}); await asyncio.sleep(2)
            await ev("document.cookie='tk='+encodeURIComponent(%s)+'; path=/; SameSite=Lax';location.href='/';" % json.dumps(TOK))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(1.5)
            await ev("await ensureOrgTree(false).catch(function(){});", aw=True)
            await asyncio.sleep(1)
            # 场景1：未选 → toast 拦截
            st = await ev("""(function(){
              ARCH_SEL.clear();ARCH_LAST='';
              toggleSynMode();
              var t=document.querySelector('.toast,.toast-msg,#toast');
              return {synOn: !!SYN_MODE, toast: (document.body.textContent.match(/请先在上方架构区[^\"]*/)||[''])[0].slice(0,30)};
            })()""")
            print('场景1 未选:', json.dumps(st, ensure_ascii=False))
            # 场景2：多选（核算部最后点击）→ 应按核算部进入
            await ev("""(function(){
              ARCH_SEL.clear();
              ['管理部','核算部'].forEach(function(n){if(ORG_FLAT.some(function(x){return x.name===n&&x.node_type==='dept'}))toggleDept(n);});
              toggleSynMode();
            })()""")
            await asyncio.sleep(3)
            st2 = await ev("""(function(){
              var t=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent;}).slice(-2);
              return {synOn: !!SYN_MODE, name: SYN_MODE?SYN_MODE.name:null, nodeId: SYN_MODE?SYN_MODE.nodeId:null,
                      archSel: [...ARCH_SEL], archLast: ARCH_LAST, toasts: t,
                      flatHas: ORG_FLAT.filter(function(x){return x.name==='管理部'||x.name==='核算部';}).map(function(x){return x.name+'/'+x.node_type;})};
            })()""")
            print('场景2 多选(核算部最后点):', json.dumps(st2, ensure_ascii=False))
            await ev("if(SYN_MODE)exitSynMode();")
            await asyncio.sleep(1)
            # 场景3：单选核算部 → 直接进入
            await ev("ARCH_SEL.clear();toggleDept('核算部');toggleSynMode();")
            await asyncio.sleep(2.5)
            st3 = await ev("({synOn: !!SYN_MODE, name: SYN_MODE?SYN_MODE.name:null})")
            print('场景3 单选:', json.dumps(st3, ensure_ascii=False))
            ok = (st.get('synOn') is False and st2.get('synOn') is True and st2.get('name') == '核算部'
                  and st3.get('synOn') is True and st3.get('name') == '核算部')
            print('OK 三场景验收通过' if ok else 'FAIL 验收失败')
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
asyncio.run(main())
