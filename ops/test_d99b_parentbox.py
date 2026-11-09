# -*- coding: utf-8 -*-
"""#99b 实测：子事项编辑/新增弹窗的父事项信息有边框盒"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    from app.app import make_token
    tok = make_token('admin')
    import sqlite3
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'); con.row_factory = sqlite3.Row
    sub = con.execute("SELECT card_id,parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid = sub['parent_id'], sub['card_id']
    con.close()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d99x')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9450', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9450/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9450/json', timeout=5).read())
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
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
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
        await ev("toggleSubTree('" + pid + "', true); 'x'", aw=True)
        await asyncio.sleep(1.5)

        # ① 编辑子事项：父事项盒有边框
        await ev("openSubModal('" + sid + "'); 'ok'", aw=True)
        await asyncio.sleep(1.5)
        await ev("openDetailEdit(); 'done'", aw=True)
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
          const g=document.getElementById('e_parent_info');
          if(!g) return {noEl:true};
          const cs=getComputedStyle(g);
          return {hasBoxClass:g.classList.contains('parent-box'),
                  border:cs.borderTopWidth, radius:cs.borderTopLeftRadius,
                  text:(g.textContent||'').slice(0,30)};
        })()""")
        print('编辑弹窗父事项盒:', r)
        ok(r.get('hasBoxClass') and r.get('border') not in ('0px', ''), '编辑弹窗：父事项信息有边框盒（%s）' % r.get('text'))
        shot1 = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d99b_edit_parentbox.png', 'wb').write(base64.b64decode(shot1['data']))
        await ev("closeEdit();")

        # ② 新增子事项：同样有边框盒
        await ev("openNewSubModal('" + pid + "');")
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
          const g=document.getElementById('n_parent_info');
          if(!g) return {noEl:true};
          const cs=getComputedStyle(g);
          return {hasBoxClass:g.classList.contains('parent-box'),
                  border:cs.borderTopWidth,
                  text:(g.textContent||'').slice(0,30)};
        })()""")
        print('新增弹窗父事项盒:', r)
        ok(r.get('hasBoxClass') and r.get('border') not in ('0px', ''), '新增弹窗：父事项信息有边框盒（%s）' % r.get('text'))
        shot2 = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d99b_new_parentbox.png', 'wb').write(base64.b64decode(shot2['data']))
        print('截图已存（edit/new 两张）')
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
