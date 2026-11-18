# -*- coding: utf-8 -*-
"""T-205h-bis：全选 checkbox 简化形态 CDP 实测（零写库）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9597
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205h2')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', f'--remote-debugging-port={PORT}',
                      '--user-data-dir=' + profile, 'about:blank'],
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
        await asyncio.sleep(2.5)

        r1 = await ev("""(function(){
          const host=document.createElement('div');
          host.id='__all_test__';
          host.style.cssText='position:fixed;left:0;top:0;width:300px';
          document.body.appendChild(host);
          // 预置：池外存量 1 人 + 池内空选
          initPersonPicker('__all_test__', ['池外老张'], null, '', false);
          const o=PP['__all_test__'];
          o.rd('');
          const drop=o.drop;
          // ① 全选条 = checkbox 形态、文字「全选」
          const allLabel=drop.querySelector('label.pp-all');
          const allText=allLabel?allLabel.querySelector('span').textContent:'';
          // ② 勾选全选 → 池内全选（71）、池外老张保留、tags=72
          const allCb=allLabel.querySelector('input');
          allCb.click();
          const afterAll={arrN:o.arr.length, poolAllIn:o.ALL.every(n=>o.arr.includes(n)),
                          legacyKept:o.arr.includes('池外老张'),
                          tagsN:host.querySelectorAll('.pp-tag').length,
                          openStill:drop.style.display==='block'};
          // ③ 取消全选 → arr 清空、全部 checkbox 取消、tags 清空
          //   ⚠️ 取 rd 重绘后的**新节点**（旧节点已脱离 DOM，click() 不派发 change）
          const allCb2=drop.querySelector('.pp-all input');
          allCb2.click();
          const allCbUnchecked=!allCb2.checked;
          const afterUn={arrN:o.arr.length, legacyGone:!o.arr.includes('池外老张'),
                         tagsN:host.querySelectorAll('.pp-tag').length,
                         checkedN:drop.querySelectorAll('input:checked').length,
                         allCbUnchecked:allCbUnchecked};
          return {allText:allText, isCheckbox:!!allCb,
                  afterAll:afterAll, afterUn:afterUn};
        })()""")
        print(json.dumps(r1, ensure_ascii=False, indent=1))
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205h2')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
