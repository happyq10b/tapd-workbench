# -*- coding: utf-8 -*-
"""复现：BCP1793717004248 看板「2026年第1/2周」无法勾选"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205m')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9635',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9635/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9635/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50*1024*1024)
        pending = {}
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        seq = [0]
        async def send(mm, p=None):
            seq[0] += 1
            f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        r0 = await ev("""(function(){
          const b=(ME.boards||[]).find(function(x){return x.board_id==='BCP1793717004248';});
          return {found:!!b, name:b?b.board_name:'', dept:b?b.dept:'', attr:b?b.attr:'',
                  inCurBoards:(curBoards||new Set()).has('BCP1793717004248')};
        })()""")
        print('① 看板状态:', json.dumps(r0, ensure_ascii=False), flush=True)
        await ev("pickBoard('BCP1793717004248')")
        await asyncio.sleep(2.5)
        # 找目标板块的勾选框
        if not r0.get('chkMode', True) or True:
            pass
        # 开启勾选模式（CHK_MODE）后再查勾选框
        rA = await ev("""(function(){
          return {chkMode:!!window.CHK_MODE, fn:typeof toggleChkMode};
        })()""")
        print('②-a 勾选模式状态:', json.dumps(rA, ensure_ascii=False), flush=True)
        if not rA.get('chkMode'):
            await ev('toggleChkMode()')
            await asyncio.sleep(2.5)
        r = await ev("""(function(){
          const titles=[].slice.call(document.querySelectorAll('.week-title'));
          const el=titles.find(function(x){return x.textContent.indexOf('2026年第1/2周')>=0;});
          if(!el)return {err:'页面上找不到该板块', titlesN:titles.length,
                          allTitles:titles.slice(0,6).map(function(x){return x.textContent.trim().slice(0,20);})};
          const row=el.closest('.week-group');
          const chk=row?row.querySelector('.col-chk'):null;
          const key=el.dataset.colkey||'';
          return {found:true, colkey:key,
                  chkExists:!!chk, disabled:chk?chk.disabled:null,
                  canOwn:chkColOwnerOf(key,'BCP1793717004248'),
                  cardsInCol:(CHK_COL_CARDS[key]||[]).length,
                  boardName:(ME.boards||[]).find(function(x){return x.board_id==='BCP1793717004248';})||{}};
        })()""")
        print('② 勾选框状态:', json.dumps(r, ensure_ascii=False), flush=True)
        if r and r.get('found'):
            # 勾选（正常态：板块下有事项）
            r2 = await ev("""(function(){
              const titles=[].slice.call(document.querySelectorAll('.week-title'));
              const el=titles.find(function(x){return x.textContent.indexOf('2026年第1/2周')>=0;});
              const chk=el.closest('.week-group').querySelector('.col-chk');
              let err='';
              try{chk.click();}catch(e){err=String(e);}
              return {err:err, checked:chk.checked, disabled:chk.disabled,
                      inSet:COL_CHECKED.has(el.dataset.colkey),
                      setN:COL_CHECKED.size};
            })()""")
            print('③ 勾选结果（有事项）:', json.dumps(r2, ensure_ascii=False), flush=True)
            # ④ 用户场景：板块下无可聚合事项（空板块/事项被筛选过滤）→ 勾选不被打回
            r3 = await ev("""(function(){
              const titles=[].slice.call(document.querySelectorAll('.week-title'));
              const el=titles.find(function(x){return x.textContent.indexOf('2026年第1/2周')>=0;});
              const chk=el.closest('.week-group').querySelector('.col-chk');
              const key=el.dataset.colkey;
              COL_CHECKED.delete(key); ITEM_CHECKED.clear();
              CHK_COL_CARDS[key]=[];               // 模拟：事项被筛选过滤掉（板块仍显示）
              chk.checked=false;
              chk.click();
              const on={checked:chk.checked, inSet:COL_CHECKED.has(key)};
              chk.click();                          // 取消方向同样要能取消
              const off={checked:chk.checked, inSet:COL_CHECKED.has(key)};
              return {on:on, off:off};
            })()""")
            print('④ 空板块勾选/取消:', json.dumps(r3, ensure_ascii=False), flush=True)
            ok_n = fail_n = 0
            def ok(cond, msg):
                nonlocal ok_n, fail_n
                print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
                if cond: ok_n += 1
                else: fail_n += 1
            ok(r2 and r2.get('checked') and r2.get('inSet'),
               "① 有事项板块：勾选生效（checked+COL_CHECKED 入集）")
            ok(r3 and r3.get('on', {}).get('checked') and r3.get('on', {}).get('inSet'),
               "② 无事项板块（空板块/被筛选过滤）：勾选不被打回（#205m 修复）")
            ok(r3 and not r3.get('off', {}).get('checked') and not r3.get('off', {}).get('inSet'),
               "③ 无事项板块：取消勾选同样生效")
            print('---- 结果: %d PASS / %d FAIL ----' % (ok_n, fail_n), flush=True)
    finally:
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205m')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
