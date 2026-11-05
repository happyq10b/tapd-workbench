#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图留档：看板管理「+ 新建看板」按钮对架构负责人（部门长）可见（#69）。

以部门长账号打开看板管理，截左上角区域 —— 供人工目视确认按钮出现在
「真实看板 …… N 个」旁（用户截图标记位置）。不参与断言。
"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9393
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__shot2_'
U_DEPT = P + 'dept'
PWD = 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'bc_new_board_btn.png')
CENTER_NAME = '财务中心'
DEPT_NAME = P + '核算部'


def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-05 12:00:00'
    c.execute("DELETE FROM users WHERE username=?", (U_DEPT,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_DEPT,))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name=?)", (DEPT_NAME,))
    c.execute("DELETE FROM org_nodes WHERE name=?", (DEPT_NAME,))
    c.execute("DELETE FROM workgroups WHERE name=?", (DEPT_NAME,))
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
              (P + '部门长', U_DEPT, now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
              " VALUES (?,?,?,?,?,?)", (U_DEPT, hash_pw(PWD), 'editor', '*', '*', now))
    # 挂到真实「财务中心」下的部门节点（arch_scope 才非空）
    center = c.execute("SELECT id FROM org_nodes WHERE name=? AND node_type='center'", (CENTER_NAME,)).fetchone()
    cid = center['id'] if center else 0
    wg = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','', '')",
                   (DEPT_NAME,)).lastrowid
    nd = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,?,?)",
                   (DEPT_NAME, 'dept', cid, wg)).lastrowid
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
              " VALUES (?,?,?,1,?)", (nd, c.execute("SELECT id FROM team_members WHERE account=?", (U_DEPT,)).fetchone()[0], 'dept_head', now))
    c.commit(); c.close()


def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name=?)", (DEPT_NAME,))
    c.execute("DELETE FROM org_nodes WHERE name=?", (DEPT_NAME,))
    c.execute("DELETE FROM workgroups WHERE name=?", (DEPT_NAME,))
    c.execute("DELETE FROM users WHERE username=?", (U_DEPT,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_DEPT,))
    c.commit(); c.close()


async def main():
    setup()
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
                       {'width': 1080, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U_DEPT), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            vis = await ev("(function(){var b=document.getElementById('bcNewBoardBtn');"
                           "return {vis:b?(b.style.display!=='none'&&b.offsetParent!==null):false,"
                           "disp:b?b.style.display:'<no btn>',arch:(ME.arch_scope||[]).length,"
                           "ia:!!ME.is_admin};})()")
            print('部门长视角探针:', vis)
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
        cleanup()
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
