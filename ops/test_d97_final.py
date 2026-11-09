# -*- coding: utf-8 -*-
"""#96b 终验（真实路径）：详情→编辑→改周数保存 → 库+目录双验证"""
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
    sub = con.execute("SELECT card_id,parent_id,week_no FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid, old_week = sub['parent_id'], sub['card_id'], sub['week_no']
    con.close()
    new_week = '2026年第40周' if old_week != '2026年第40周' else '2026年第41周'
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d97g')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9430', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9430/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9430/json', timeout=5).read())
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
                return {'__err__': desc[:150]}
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
        await ev("openSubModal('" + sid + "'); 'ok'", aw=True)
        await asyncio.sleep(1.5)
        print('详情开:', await ev("document.getElementById('detailModal').style.display"))
        await ev("openDetailEdit(); 'done'", aw=True)
        await asyncio.sleep(1.2)
        print('editModal:', await ev("document.getElementById('editModal').style.display"))
        print('EDIT_IS_SUB:', await ev("JSON.stringify(EDIT_IS_SUB)"))
        print('e_week 值:', await ev("JSON.stringify(document.getElementById('e_week').value)"))
        print('e_week display:', await ev("getComputedStyle(document.getElementById('e_week_group')).display"))
        await ev("document.getElementById('e_week').value='" + new_week + "';")
        await ev("saveEdit(); 'x'", aw=True)
        await asyncio.sleep(2.5)
        con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        now = con.execute("SELECT week_no FROM cards WHERE card_id=?", (sid,)).fetchone()[0]
        con.close()
        print('库中周数:', repr(now), 'PASS 生效' if now == new_week else 'FAIL')
        await ev("toggleSubTree('" + pid + "', true); 'x'", aw=True)
        await asyncio.sleep(2)
        tree = await ev("(function(){const fc=document.querySelector('#subtree_" + pid +
                        " .fcols');return fc?fc.textContent:'';})()")
        print('目录子树行:', (tree or '')[:70])
        print('PASS 目录同步' if new_week in (tree or '') else 'FAIL 目录未同步')
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d97_sub_layout.png', 'wb').write(base64.b64decode(shot['data']))
        # 还原
        await ev("openDetailEdit(); 'x'", aw=True)
        await asyncio.sleep(1)
        await ev("document.getElementById('e_week').value='" + old_week + "';")
        await ev("saveEdit(); 'x'", aw=True)
        await asyncio.sleep(1.5)
        con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        back = con.execute("SELECT week_no FROM cards WHERE card_id=?", (sid,)).fetchone()[0]
        con.close()
        print('（已还原为 %s）' % back)
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
