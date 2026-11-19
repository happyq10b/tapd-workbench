# -*- coding: utf-8 -*-
"""T-0173 协作部门按钮移至归属部门右侧同行——几何断言 + 截图。"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9476
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0173')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--window-size=1440,900', '--no-first-run',
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
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % make_token('admin')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(60):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True
            break
    ok(ok_login, 'admin 登录成功')
    await asyncio.sleep(1.5)

    print('【① 打开看板管理弹窗，选中心归属看板】', flush=True)
    await ev("openModal('boardConfigModal')")
    await asyncio.sleep(1)
    r0 = await ev("""(async function(){
      await loadBoardConfig();
      const b=(BC_BOARDS||[]).find(function(x){return x.dept==='财务中心' && x.config_id;});
      if(!b)return {found:false};
      bcSelect(b.board_id);
      return {found:true, name:b.board_name};
    })()""", aw=True)
    print('  ', json.dumps(r0, ensure_ascii=False), flush=True)
    ok(r0 and r0.get('found'), '找到中心归属看板：%s' % (r0 or {}).get('name'))
    await asyncio.sleep(1.5)

    print('【② 几何断言：协作部门按钮与归属部门下拉同一行、在其右侧】', flush=True)
    r2 = await ev("""(function(){
      const d=document.getElementById('bc_dept');
      const b=document.getElementById('bc_collab_btn');
      if(!d||!b)return {found:false};
      const dr=d.getBoundingClientRect(), br=b.getBoundingClientRect();
      return {found:true, sameRow:Math.abs(dr.top-br.top)<6, right:br.left>dr.right,
              sameHeightBand:Math.abs((dr.top+dr.height/2)-(br.top+br.height/2))<6,
              wrapParent:getComputedStyle(d.parentElement).flexWrap};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('found'), '两控件均存在（中心归属下协作按钮渲染）')
    ok(r2.get('sameRow'), '协作部门按钮与归属部门下拉同一行（top 差 <6px）')
    ok(r2.get('right'), '协作部门按钮在下拉右侧')
    ok(r2.get('sameHeightBand'), '两控件垂直居中对齐')
    ok(r2.get('wrapParent') == 'nowrap', '容器不换行（不会再被挤到下一行）')

    shot = await send('Page.captureScreenshot', {'format': 'png'})
    open(r'E:\WB缓存\2026-10-26-15-55-08\ops\.tmp_t0173_shot.png', 'wb').write(base64.b64decode(shot['data']))
    print('  截图已保存', flush=True)
    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
asyncio.run(main())

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
