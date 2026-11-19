# -*- coding: utf-8 -*-
"""T-013 登录页小精灵挂件 CDP 实测：随机性 / 元素存在 / 布局零位移 / 登录回归"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9461
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PASS = []
def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t013')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}
    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)
    seq = [0]
    async def send(m, p=None):
        seq[0] += 1; mid = seq[0]
        fut = asyncio.get_event_loop().create_future(); pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})
    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return None
        return r.get('result', {}).get('value')
    rt = asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')

    print('【① 容器与图片元素存在 + 路由加载成功】', flush=True)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    r1 = await ev("""(function(){
      const pet=document.getElementById('pet'), img=document.getElementById('petImg');
      if(!pet||!img) return {has:false};
      const cs=getComputedStyle(pet), ics=getComputedStyle(img);
      const ir=img.getBoundingClientRect();
      return {has:true, src:img.getAttribute('src'), loaded:img.complete&&img.naturalWidth>0,
              pe:cs.pointerEvents, abs:cs.position, w:ir.width, h:ir.height,
              px:ics.imageRendering};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1 and r1.get('has'), '.pet 容器与 #petImg 存在')
    ok(r1 and (r1.get('src') or '').startswith('/pet/'), 'src 为 /pet/{1..386}：%s' % (r1.get('src')))
    ok(r1 and r1.get('loaded'), '精灵图加载成功（naturalWidth>0）')
    ok(r1 and r1.get('pe') == 'none' and r1.get('abs') == 'absolute', 'pointer-events:none + 绝对定位（不挡点击/不占布局）')
    ok(r1 and r1.get('px') == 'pixelated', 'image-rendering:pixelated（保像素风）')

    print('【② 随机性：刷新 6 次，出现 ≥3 个不同编号】', flush=True)
    nos = set()
    for i in range(6):
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(1.4)
        s = await ev("document.getElementById('petImg').getAttribute('src')")
        if s: nos.add(s)
    print('   编号集合:', sorted(nos), flush=True)
    ok(len(nos) >= 3, '6 次刷新出现 %d 个不同编号（随机性生效）' % len(nos))

    print('【③ 布局零位移：卡片内控件坐标符合预期区域】', flush=True)
    r3 = await ev("""(function(){
      const g=function(id){const e=document.getElementById(id);if(!e)return null;const r=e.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top),Math.round(r.width)];};
      const card=document.querySelector('.card').getBoundingClientRect();
      const logo=document.querySelector('.logo h1').getBoundingClientRect();
      return {u:g('u'), p:g('p'), btn:g('btn'), card:[Math.round(card.left),Math.round(card.top),Math.round(card.width)],
              h1Left:Math.round(logo.left), h1Width:Math.round(logo.width)};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3 and r3.get('u') and r3.get('u')[2] > 200, '账号输入框宽度正常（无位移挤压）')
    # 卡片 360 宽 + padding 36 → 输入框左 = 卡片左+36
    ok(r3 and r3['u'][0] == r3['card'][0] + 36, '输入框 x = 卡片左 + padding（布局未被挂件改变）')
    ok(r3 and r3['h1Left'] == r3['card'][0] + 36, '标题仍在文档流原位（挂件零影响）')

    print('【④ 登录回归：错误密码 → 提示正常（流程未被挂件影响）】', flush=True)
    await ev("document.getElementById('u').value='__t_no_such_user__';document.getElementById('p').value='WrongPass1';document.getElementById('btn').click();")
    got = False
    for _ in range(20):
        await asyncio.sleep(0.5)
        m = await ev("document.getElementById('msg').textContent")
        if m:
            got = True
            print('   msg:', m, flush=True)
            break
    ok(got, '登录失败提示正常返回（登录流程不受影响）')

    await send('Browser.close')
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
asyncio.run(main())
n = sum(1 for c, _ in PASS if c)
print('结果: PASS=%d/%d' % (n, len(PASS)), flush=True)
sys.exit(0 if n == len(PASS) else 1)
