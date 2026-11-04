#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图留档：看板管理页脚改造后的实际渲染（#61）。

生成 PNG 到 ops/.shots/board_footer.png —— 供人工目视确认按钮布局。
不参与断言（断言在 ui_check_board_footer.py）。
"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9391
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__shot_'
U_ADMIN = P + 'admin'
PWD = 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'board_footer.png')


def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-04 22:00:00'
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
              (P + U_ADMIN, U_ADMIN, now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
              " VALUES (?,?,?,?,?,?)", (U_ADMIN, hash_pw(PWD), 'admin', '*', '*', now))
    bid = 'SH' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,'','','',0,?)", (bid, '收入工作事项（2026年度）', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, '核算部', 0, '日常', '启用', now))
    c.commit(); c.close()
    return bid


def cleanup(bid):
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
    c.execute("DELETE FROM board_config WHERE board_id=?", (bid,))
    c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.commit(); c.close()


async def main():
    bid = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_sh%d' % PORT)
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
                       {'width': 1080, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U_ADMIN), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            await ev("(function(){var it=document.querySelector('#bcList .bc-item[data-bid=\"%s\"]');"
                     "if(it)it.click();})()" % bid)
            await asyncio.sleep(1.5)
            # 滚到页脚
            await ev("(function(){var f=document.querySelector('#bcEditArea .bc-footer');"
                     "if(f)f.scrollIntoView({block:'center'});})()")
            await asyncio.sleep(1)
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
        cleanup(bid)
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
