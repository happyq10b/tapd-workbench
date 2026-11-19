# -*- coding: utf-8 -*-
"""T-0180 精灵弹窗交互 CDP 测试：裁切器置顶 + 保存设置不关窗。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9493
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []
_ORIG_PET = None
_MAX_SH = 0


def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


def backup():
    global _ORIG_PET, _MAX_SH
    c = sqlite3.connect(DB)
    row = c.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone()
    _ORIG_PET = row[0] if row else ''
    _MAX_SH = c.execute("SELECT COALESCE(MAX(id),0) FROM state_history WHERE scope='login_pet'").fetchone()[0]
    c.close()


def restore():
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO app_settings (key,value) VALUES ('login_pet',?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_ORIG_PET,))
    c.execute("DELETE FROM state_history WHERE scope='login_pet' AND id>?", (_MAX_SH,))
    c.commit(); c.close()
    print('清理：login_pet 已恢复原值(%r)，测试快照已清' % _ORIG_PET, flush=True)


async def main():
    tk = make_token('admin')
    backup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0180')
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
    pending = {}
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)
    asyncio.get_event_loop().create_task(reader())

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % tk
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【① 裁切器置顶：z-index 必须高于设置弹窗】', flush=True)
    await ev("openPetSettingModal()")
    await asyncio.sleep(1.5)
    r1 = await ev("""(function(){
      const zi=function(id){const el=document.getElementById(id);return el?Number(getComputedStyle(el).zIndex||0):null};
      return {crop:zi('cropModal'), pet:zi('petSettingModal')};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(isinstance(r1, dict) and (r1.get('crop') or 0) > (r1.get('pet') or 0),
       'cropModal z-index 高于 petSettingModal（裁切器可交互）')
    # 真实性验证：pet 弹窗打开时打开裁切器，确认其可点击（最顶层元素属于裁切器）
    await ev("openCropper('pet','data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',null)")
    await asyncio.sleep(0.8)
    r1b = await ev("(function(){const el=document.elementFromPoint(window.innerWidth/2,window.innerHeight/2);"
                   "return el?el.closest('#cropModal')!==null:null})()")
    ok(r1b is True, '弹窗叠放时视口中心命中的是裁切器（不被设置弹窗遮挡）')
    await ev("cancelCrop()")

    print('【② 保存设置后留在弹窗内】', flush=True)
    await ev("(function(){document.querySelector('input[name=petMode][value=random]').checked=true;})()")
    await ev("PET_RAND_ZONE='__builtin__'")
    await ev("document.getElementById('petSaveBtn').click()")
    for _ in range(20):
        await asyncio.sleep(0.3)
        if await ev("SG_N===0") is True:
            break
    ok(await ev("document.getElementById('petSettingModal').style.display==='flex'") is True,
       '保存设置后弹窗保持打开')
    toasts = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    ok(any('随机' in t2 or '生效' in t2 for t2 in (toasts or [])), f'保存成功 toast 出现（{toasts}）')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    restore()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
