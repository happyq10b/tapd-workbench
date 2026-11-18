# -*- coding: utf-8 -*-
"""T-205c CDP 验证：登录页版本号真实渲染（只读 + 环境还原）

① 未配置 → 登录页 appVer 隐藏
② 配置 v2026.11.18 → 卡片底部右下角显示该版本号
③ 还原清空
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9561
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


def api_put(version):
    req = urllib.request.Request(BASE + '/api/version', method='PUT')
    req.add_header('Authorization', 'Bearer ' + make_token('admin'))
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req, json.dumps({'version': version}).encode(), timeout=15)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205c')
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

        async def send(method, params=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': method, 'params': params or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(expr):
            r = await send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')

        # ① 未配置 → 隐藏
        api_put('')
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2.5)
        s1 = await ev("(function(){const el=document.getElementById('appVer');"
                      "return el?{hidden:el.hidden,text:el.textContent}:null})()")
        ok(s1 and s1.get('hidden') is True, f"① 未配置 → 版本号隐藏（{s1}）")

        # ② 配置 → 卡片底部右下角显示
        api_put('v2026.11.18')
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2.5)
        s2 = await ev("""(function(){
          const el=document.getElementById('appVer');
          if(!el)return null;
          const card=document.querySelector('.card');
          const cr=card?card.getBoundingClientRect():null;
          const er=el.getBoundingClientRect();
          return {hidden:el.hidden,text:el.textContent,
                  inCard:!!card&&card.contains(el),
                  rightAlign:cr?Math.abs(cr.right-er.right)<40:false,
                  nearBottom:cr?(cr.bottom-er.bottom)<60:false};
        })()""")
        ok(s2 and s2.get('hidden') is False and s2.get('text') == 'v2026.11.18',
           f"② 配置后显示「{s2.get('text')}」")
        ok(s2 and s2.get('inCard') and s2.get('rightAlign') and s2.get('nearBottom'),
           f"② 位置在登录卡片底部右下角（inCard={s2.get('inCard')}, right={s2.get('rightAlign')}, bottom={s2.get('nearBottom')}）")
    finally:
        api_put('')   # 环境还原
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205c')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
