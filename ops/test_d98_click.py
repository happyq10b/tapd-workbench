# -*- coding: utf-8 -*-
"""#98 复现：目录点击子事项——第一次点击后 detailModal 状态（真实 element.click）"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'


async def main():
    import websockets
    from app.app import make_token
    tok = make_token('admin')
    import sqlite3
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'); con.row_factory = sqlite3.Row
    sub = con.execute("SELECT card_id,parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid = sub['parent_id'], sub['card_id']
    con.close()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d98')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9433', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9433/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9433/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                desc = r['exceptionDetails'].get('exception', {}).get('description', '') or r['exceptionDetails'].get('text', '')
                return {'__err__': desc[:200]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        # 抓 toast 与未捕获异常
        await ev("window.__toasts=[];window.__errs=[];")
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        con2 = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        pboard = con2.execute("SELECT board_id FROM cards WHERE card_id=?", (pid,)).fetchone()[0]
        con2.close()
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(3)
        # 恢复 toast 捕获（页面跳转后重挂）
        await ev("window.__toasts=[];"
                 "const _origToast=typeof toast==='function'?toast:null;"
                 "window.toast=function(m){window.__toasts.push(String(m));if(_origToast)_origToast(m);};"
                 "window.addEventListener('error',e=>window.__errs.push(String(e.message)));")
        # 展开子树
        await ev("toggleSubTree('" + pid + "', true); 'x'", aw=True)
        await asyncio.sleep(2)
        # 第一次点击：真实 element.click() 在子事项标题上
        r = await ev("""(function(){
          const t=document.querySelector('#subtree_%s .s-title');
          if(!t) return {noTitle:true};
          t.click();
          return {clicked:true, txt:t.textContent.trim().slice(0,20)};
        })()""" % pid)
        print('第一次点击:', r)
        for d in (0.3, 1.0, 2.0):
            await asyncio.sleep(d)
            st = await ev("document.getElementById('detailModal').style.display")
            title = await ev("document.getElementById('d_title')?document.getElementById('d_title').textContent:''")
            print('  t+%ss detailModal=%s d_title=%s' % (d, st, (title or '')[:20]))
        toasts = await ev("JSON.stringify(window.__toasts)")
        errs = await ev("JSON.stringify(window.__errs)")
        print('toasts:', toasts, '| errs:', errs)
        # 第二次点击
        await ev("(function(){const t=document.querySelector('#subtree_%s .s-title');if(t)t.click();})()" % pid)
        await asyncio.sleep(1.5)
        st = await ev("document.getElementById('detailModal').style.display")
        title = await ev("document.getElementById('d_title')?document.getElementById('d_title').textContent:''")
        print('第二次点击后 detailModal=%s d_title=%s' % (st, (title or '')[:20]))
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d98_click.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
