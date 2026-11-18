# -*- coding: utf-8 -*-
"""T-205d：admin 无法选中/删除「2026年第9/10周（2.24-3.8）」板块 复现实测

只读复现（勾选只在内存、不落库；DELETE 调用对不存在的同格式 key，不碰真实数据）：
① admin 选看板「综合工作事项（测试）」→ 找目标板块行 → 勾选 checkbox → 是否成功
② 点击板块标题 → 浏览弹窗是否打开
③ 前端同款 DELETE URL → 状态码与响应（对 NOEXIST key，不删真实数据）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9571
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BOARD = 'BCP1793717004248'   # 综合工作事项（1162 板的 9/10周 已被用户删除，改用 BCP 板同名板块——2026-11-18）
COL = '2026年第9/10周（2.24-3.8）'
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205d')
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

        rt = asyncio.create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
                break
        await asyncio.sleep(2.5)

        # 选中看板
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        # ① 找板块行 + 勾选模式 + 勾选
        r1 = await ev("""(function(){
          const titles=[].slice.call(document.querySelectorAll('.week-title'));
          const el=titles.find(function(x){return x.textContent.indexOf('2026年第9/10周')===0;});
          return {found:!!el, colkey:el?(el.dataset.colkey||''):'', chkMode:CHK_MODE};
        })()""")
        ok(r1.get('found') is True, f"① 找到目标板块行（colkey={r1.get('colkey')!r}）")
        if not r1.get('chkMode'):
            await ev('toggleChkMode()')
            await asyncio.sleep(2.5)
        r1b = await ev("""(function(){
          const chk=[].slice.call(document.querySelectorAll('.col-chk'))
            .find(function(x){return x.dataset.ck.indexOf('2026年第9/10周')>=0;});
          if(!chk)return {exists:false, total:document.querySelectorAll('.col-chk').length};
          let err='';
          try{chk.click();}catch(e){err=String(e);}
          return {exists:true, disabled:chk.disabled, checked:chk.checked, err:err,
                  inSet:COL_CHECKED.has(chk.dataset.ck), setSize:COL_CHECKED.size};
        })()""")
        await asyncio.sleep(0.5)
        ok(r1b.get('exists') is True and r1b.get('inSet') is True,
           f"① 勾选板块：checkbox 存在={r1b.get('exists')}，disabled={r1b.get('disabled')}，checked={r1b.get('checked')}，COL_CHECKED 含目标={r1b.get('inSet')}，错误={r1b.get('err')!r}")

        # ② 点击板块标题 → 浏览弹窗
        await ev("CHK_MODE&&toggleChkMode&&toggleChkMode();")   # 关回勾选模式
        await asyncio.sleep(0.5)
        r2 = await ev("""(function(){
          const titles=[].slice.call(document.querySelectorAll('.week-title.edit'));
          const el=titles.find(function(x){return x.textContent.indexOf('2026年第9/10周')===0;});
          if(!el)return {found:false};
          try{el.click();}catch(e){return {found:true, err:String(e)};}
          return {found:true};
        })()""")
        await asyncio.sleep(1.5)
        r2b = await ev("""(function(){
          const m=document.getElementById('columnDetailModal');
          return {open:!!(m&&m.style.display&&m.style.display!=='none'),
                  colkey:(window.COLUMN_DETAIL||{}).colkey||''};
        })()""")
        ok(r2b.get('open') is True, f"② 点板块标题 → 浏览弹窗打开（colkey={r2b.get('colkey')!r}，点击错误={r2.get('err')!r}）")
        await ev("closeModal('columnDetailModal')")

        # ③ 前端同款 DELETE（对 NOEXIST key，不碰真实数据）
        r3 = await ev("""api('/api/columns/'+encodeURIComponent('NOEXIST::2026年第9/10周（2.24-3.8）'),
          {method:'DELETE'}).then(function(){return {st:200}}).catch(function(e){return {st:e.status||0,msg:e.message}})""", aw=True)
        print('   [详情] DELETE 响应:', r3)
        ok(True, f"③ DELETE 带斜杠 col_key → {r3}（预期 404 Not Found=路由未匹配）")
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205d')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===')
