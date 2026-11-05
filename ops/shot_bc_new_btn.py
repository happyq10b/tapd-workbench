#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图留档：事项编辑弹窗「负责人/参与人」选择器内外框匹配修复（#74）。

管理员登录 → 打开既有真实事项的编辑弹窗 → 截图。
不参与断言。
"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9394
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
U = 'admin'
PWD = 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'edit_pp_box.png')


def pick_card():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    row = c.execute("SELECT card_id, board_id FROM cards WHERE deleted=0 ORDER BY rowid DESC LIMIT 1").fetchone()
    col = None
    if row:
        col = c.execute("SELECT col_key FROM board_columns WHERE board_id=? LIMIT 1",
                        (row['board_id'],)).fetchone()
    c.close()
    return (row['card_id'] if row else None), (col['col_key'] if col else None), (row['board_id'] if row else None)


async def main():
    card, col_key, board = pick_card()
    print('样本事项:', card, '板块:', col_key)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_s2%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1
                mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1080, 'height': 860, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            # 用真实事项 + 真实板块元数据打开编辑弹窗
            r = await ev("window.COLS_META=[{col_key:%s,column_id:'c1',owner:'',participants:''}];"
                         "openEdit(%s);" % (json.dumps(col_key or ''), json.dumps(card)), aw=True)
            await asyncio.sleep(2)
            st = await ev("(function(){var m=document.getElementById('editModal');"
                          "if(!m)return 'no modal';"
                          "var io=document.querySelector('#e_owner .pp-in'),ic=document.querySelector('#e_cc .pp-in');"
                          "function info(el){if(!el)return null;var r=el.getBoundingClientRect();"
                          "var box=el.closest('.member-picker').getBoundingClientRect();"
                          "return {inpW:Math.round(r.width),boxW:Math.round(box.width),"
                          "ph:el.placeholder};}"
                          "return {owner:info(io),cc:info(ic)};})()")
            print('宽度对齐探针:', json.dumps(st, ensure_ascii=False))
            shot = await send('Page.captureScreenshot', {'format': 'png'})
            data = shot.get('data')
            if data:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, 'wb') as f:
                    f.write(base64.b64decode(data))
                print('截图已保存：%s' % OUT)
            else:
                print('截图失败')
    finally:
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
