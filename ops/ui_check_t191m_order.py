# -*- coding: utf-8 -*-
"""T-191m 探针：筛选按钮行顺序 —— 到期筛选在前，清空筛选固定尾部。
只读验证（不落库、无夹具）。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
BASE = 'http://127.0.0.1:8100'; PORT = 9556
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

N = []
def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)

async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191m')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception: time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50*1024*1024)
    pending, seq = {}, [0]
    async def send(m, p=None):
        seq[0] += 1; fut = asyncio.get_event_loop().create_future(); pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})
    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:150])
            return {'__err__': True}
        return r.get('result', {}).get('value')
    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done(): fut.set_result(msg)
    asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True: break
    await asyncio.sleep(1.5)
    r = await ev("""(function(){
      const row=document.querySelector('.toolbar-title-btns');
      const labels=[...row.querySelectorAll('button')].map(b=>b.textContent.trim().replace(/\\d+$/,''));
      const due=document.getElementById('dueFilterBtn');
      const wDue=Math.round(due.getBoundingClientRect().width);
      return {labels:labels,dueIdx:labels.indexOf('到期筛选'),clearIdx:labels.indexOf('清空筛选'),
        wDue:wDue,last:labels[labels.length-1]};})()""")
    print('  ', json.dumps(r, ensure_ascii=True), flush=True)
    if isinstance(r, dict) and not r.get('__err__'):
        labels = r['labels']
        ok(r['dueIdx'] > 0 and r['dueIdx'] < r['clearIdx'],
           '顺序：到期筛选(%d) 在 清空筛选(%d) 之前' % (r['dueIdx'], r['clearIdx']))
        ok(r['last'] == '清空筛选', '行尾最后一个按钮 = 清空筛选（实际 %s）' % r['last'])
        i_chk, i_all = labels.index('启用勾选'), labels.index('全选当前')
        ok(r['dueIdx'] > max(i_chk, i_all) if i_chk >= 0 else True,
           '到期筛选位于勾选类按钮之后（%s）' % ' > '.join(labels))
        ok(70 <= r['wDue'] <= 110, '到期筛选按钮宽度正常（%s px）' % r['wDue'])
    await send('Browser.close')

try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails: sys.exit(1)
