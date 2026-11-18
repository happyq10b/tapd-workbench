# -*- coding: utf-8 -*-
"""T-205c-bis：版本号下移 + 登入通知至少 2 行（几何断言）

① 通知区（hint/noticeBar）渲染高度 ≥ 2 行（≥36px），短通知也预留
② 版本号在通知区下方（ver.top ≥ hint 底部），不重叠
③ 版本号仍在登录卡片内、右下角
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, _set_setting  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9563
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


def api_put(version, notice):
    _set_setting('app_version', version)
    _set_setting('login_notice', notice)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205c2')
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

        # 短通知（单行文字）+ 版本号 → 验证最小 2 行预留
        api_put('v2026.11.18', '系统维护通知')
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2.5)
        s = await ev("""(function(){
          const hint=document.getElementById('noticeBar');
          const ver=document.getElementById('appVer');
          if(!hint||!ver)return null;
          const hr=hint.getBoundingClientRect(), vr=ver.getBoundingClientRect();
          return {hintH:Math.round(hr.height), lines:Math.round(hr.height/18.4),
                  verTop:Math.round(vr.top), hintBottom:Math.round(hr.bottom),
                  noOverlap:vr.top>=hr.bottom-1,
                  inCard:!!document.querySelector('.card')&&document.querySelector('.card').contains(ver),
                  verText:ver.textContent};
        })()""")
        ok(s and s.get('hintH', 0) >= 36,
           f"① 通知区高度 {s.get('hintH')}px ≥ 2 行（≈{s.get('lines')} 行）——短通知也预留两行空间")
        ok(s and s.get('noOverlap'), f"② 版本号在通知区下方不重叠（ver.top={s.get('verTop')} ≥ hint 底={s.get('hintBottom')}）")
        ok(s and s.get('inCard') and s.get('verText') == 'v2026.11.18',
           f"③ 版本号仍在卡片内右下角（{s.get('verText')}）")
    finally:
        api_put('', '')   # 环境还原
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205c2')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
