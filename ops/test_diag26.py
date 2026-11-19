# -*- coding: utf-8 -*-
"""诊断：多周行的 fcols 几何（width=0 疑云）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.parse, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + make_token('admin'))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=25, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_diag26')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9629',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9629/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    cid = None; ck = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9629/json', timeout=5).read())
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
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
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
        # 夹具
        st, d = api('/api/columns', 'POST', {'board_id': 'BCP1793717004248', 'column_name': '__t205p_周数板块',
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
        ck = d.get('col_key')
        st3, d3 = api('/api/cards', 'POST', {'board_id': 'BCP1793717004248', 'card_name': '__t205p_跨周事项',
                                            'fields': {'column_name': '__t205p_周数板块',
                                                       'week_no': '2026年第47周;2026-46;2026-48',
                                                       'nature': '日常', 'created': '2026-11-18'}})
        cid = d3.get('card_id')
        print('fixture:', st, st3, cid, flush=True)
        await ev("pickBoard('BCP1793717004248')")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
          const row=document.querySelector('.item-wrap .fcols[style]');
          if(!row)return {err:'无'};
          const cs=getComputedStyle(row);
          const rect=row.getBoundingClientRect();
          const card=row.closest('.item-card');
          // 沿祖先链找 0 宽点
          let chain=[], el=row;
          while(el && el!==document.body){
            const r2=el.getBoundingClientRect();
            const st2=getComputedStyle(el);
            chain.push({cls:(el.className||'').toString().slice(0,30)||el.tagName,
                        w:Math.round(r2.width), disp:st2.display});
            el=el.parentElement;
          }
          return {attr:row.getAttribute('style'), chain:chain.slice(0,10)};
        })()""")
        print(json.dumps(r, ensure_ascii=False, indent=1))
    finally:
        try:
            if cid: api('/api/cards/' + cid, 'DELETE')
            if ck: api('/api/columns/' + urllib.parse.quote(ck, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_diag26')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
