# -*- coding: utf-8 -*-
"""T-205f-bis：按 chip 整体裁剪验证（无半裁残影、角标渐变、输入行完好）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9583
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_clamp2')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      f'--remote-debugging-port={PORT}', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}

        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done():
                        f.set_result(m)

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)

        # 场景 A：看板管理弹窗（截图区域）
        await ev("openBoardConfigModal()")
        await asyncio.sleep(2)
        await ev("bcSelect('1162069797001000238')")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
          const box=document.getElementById('bc_parts_box');
          if(!box)return {err:'no box'};
          box.innerHTML=Array.from({length:30},function(_,i){
            return '<span class="cf-chip"><span>测试人员'+i+'</span><i>✕</i></span>';}).join('');
          clampAllPersonBoxes();
          const kids=[].slice.call(box.children);
          const visible=kids.filter(function(k){return k.style.display!=='none';});
          const cr=box.getBoundingClientRect();
          const maxB=Math.max.apply(null,visible.map(function(k){return k.getBoundingClientRect().bottom;}));
          const st=getComputedStyle(box,'::after');
          return {total:kids.length, visibleN:visible.length, hiddenN:kids.length-visible.length,
                  boxH:Math.round(cr.height), clamped:box.classList.contains('clamped'),
                  noClip:maxB<=cr.bottom+1,
                  afterContent:st.content,
                  afterGradient:(st.backgroundImage||'').indexOf('gradient')>=0};
        })()""")
        print('A 看板管理参与人框:', json.dumps(r, ensure_ascii=False))

        # 场景 B：member-picker
        r2 = await ev("""(function(){
          const host=document.createElement('div');
          host.id='__clamp2__';
          host.style.cssText='position:fixed;left:0;top:0;width:300px';
          document.body.appendChild(host);
          initPersonPicker('__clamp2__', Array.from({length:30},function(_,i){return '测试人员'+i;}), null, '', false);
          const tags=host.querySelector('.pp-tags');
          clampAllPersonBoxes();
          const kids=[].slice.call(tags.children);
          const visible=kids.filter(function(k){return k.style.display!=='none';});
          const cr=tags.getBoundingClientRect();
          const maxB=Math.max.apply(null,visible.map(function(k){return k.getBoundingClientRect().bottom;}));
          const ip=host.querySelector('.pp-ip');
          return {total:kids.length, visibleN:visible.length, hiddenN:kids.length-visible.length,
                  tagsH:Math.round(cr.height), clamped:tags.classList.contains('clamped'),
                  noClip:maxB<=cr.bottom+1,
                  ipVisible:ip.getBoundingClientRect().height>0};
        })()""")
        print('B member-picker:', json.dumps(r2, ensure_ascii=False))
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_clamp2')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
