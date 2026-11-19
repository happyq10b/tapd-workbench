# -*- coding: utf-8 -*-
"""T-191b 修复验证：人员图片直出（cookie 通道）端到端——缩略图懒加载等待后真实解码 + 大图预览。"""
import asyncio, json, os, shutil, subprocess, sys, time
import urllib.request
import sqlite3

BASE = 'http://127.0.0.1:8100'
PORT = 9535
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

FIX_U = '__imgauth_u'
PNG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
       'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def cleanup():
    c = sqlite3.connect(ROOT + '/src/app.db', timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM users WHERE username=?", (FIX_U,))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (FIX_U,)).fetchone()[0]
    c.close()
    print('夹具残留:', n, flush=True)
    return n


async def main():
    c = sqlite3.connect(ROOT + '/src/app.db', timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT INTO users(username,password_hash,role,active_seq,avatar,photo) VALUES(?,?,?,1,?,?)",
              (FIX_U, hash_pw('x'), 'editor', PNG, PNG))
    c.commit(); c.close()

    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_imgauth2')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending, seq = {}, [0]

    async def send(m, p=None):
        seq[0] += 1
        fut = asyncio.get_event_loop().create_future()
        pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)
    await ev("openStaffModal()")
    for _ in range(20):
        await asyncio.sleep(0.4)
        if await ev("document.querySelectorAll('#staffTableWrap img.staff-photo-thumb').length>0") is True:
            break

    # 等待懒加载缩略图真实解码（夹具账号在搜索结果首行，必在可视区）
    r1 = await ev("""(async function(){
      const si=document.getElementById('staffSearch');si.value='__imgauth_u';renderStaffTable();
      const av=document.querySelector('#staffTableWrap img.staff-av');
      const ph=document.querySelector('#staffTableWrap img.staff-photo-thumb');
      const wait=im=>new Promise((res)=>{
        if(im.complete&&im.naturalWidth>0)return res(true);
        im.addEventListener('load',()=>res(true));
        im.addEventListener('error',()=>res(false));
        setTimeout(()=>res(im.complete&&im.naturalWidth>0),6000);
      });
      const a=await wait(av), p=await wait(ph);
      return {a:a,p:p,avW:av.naturalWidth,phW:ph.naturalWidth};})()""", True)
    print('缩略图解码:', json.dumps(r1), flush=True)
    ok(isinstance(r1, dict) and r1.get('a'),
       '头像缩略图真实加载（cookie 通道，naturalWidth=%s）' % (r1 or {}).get('avW'))
    ok(isinstance(r1, dict) and r1.get('p'),
       '照片缩略图真实加载（naturalWidth=%s）' % (r1 or {}).get('phW'))

    await ev("""(function(){
      document.querySelector('#staffTableWrap img.staff-photo-thumb').click();})()""")
    await asyncio.sleep(1.2)
    r3 = await ev("({open:document.getElementById('imgPreviewModal').style.display==='flex',"
                  "w:document.getElementById('imgPreviewSrc').naturalWidth,"
                  "err:document.getElementById('imgPreviewCap').textContent})")
    print('预览弹窗:', json.dumps(r3), flush=True)
    ok(isinstance(r3, dict) and r3.get('open') and r3.get('w', 0) > 0
       and '加载失败' not in str(r3.get('err')),
       '大图预览加载成功（naturalWidth=%s，无加载失败提示）' % (r3 or {}).get('w'))
    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    left = cleanup()
    fails = [m for s, m in N if not s]
    print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
    if fails or left:
        sys.exit(1)
