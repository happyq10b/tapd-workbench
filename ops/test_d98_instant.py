# -*- coding: utf-8 -*-
"""#98 实测：点击子事项 → 弹窗即刻弹出（同步帧内）+ 数据正确填充"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


def js_click(subtree_pid):
    return ('(function(){const t=document.querySelector("#subtree_' + subtree_pid +
            ' .s-title");if(!t)return{noTitle:true};'
            'window.__t0=performance.now();t.click();'
            'return{clicked:true,immediate:(function(){'
            'const em=document.getElementById("editModal");'
            'return{shown:em.style.display==="flex",'
            'elapsed:Math.round(performance.now()-window.__t0)};})()};})()')


async def main():
    import websockets
    from app.app import make_token
    tok = make_token('admin')
    import sqlite3
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'); con.row_factory = sqlite3.Row
    sub = con.execute("SELECT card_id,parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid = sub['parent_id'], sub['card_id']
    con.close()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d98c')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9446', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9446/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9446/json', timeout=5).read())
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

        # 第一次点击：同步帧内弹窗应已 flex（即刻弹出）
        r = await ev(js_click(pid))
        print('第一次点击:', r)
        ok(r.get('clicked') is True and r.get('immediate', {}).get('shown') is True,
           '点击后同步帧内弹窗已 display=flex（elapsed %sms）'
           % r.get('immediate', {}).get('elapsed'))
        await asyncio.sleep(1.5)
        r2 = await ev("(function(){return {name:document.getElementById('e_name').value,"
                      "week:document.getElementById('e_week').value,"
                      "sub:EDIT_IS_SUB};})()")
        ok(bool(r2.get('name')), '数据异步填充完成（标题=%s）' % (r2.get('name') or '')[:16])
        ok(r2.get('sub') is True, '子事项模式正确')
        await ev("closeEdit();")
        await asyncio.sleep(1)
        r = await ev(js_click(pid))
        ok(r.get('immediate', {}).get('shown') is True, '第二次点击同样即刻弹出')
        await ev("closeEdit();")
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d98_instant.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图:', out)
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
