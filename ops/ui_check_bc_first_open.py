#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""看板管理弹窗「首开尺寸异常」修复验证（2026-11-05）。

需求：首次打开看板管理弹窗，尺寸应与二次打开一致（此前首开被压扁——
renderBoardList 在 display:flex 之前执行，offsetHeight 量到 0 → maxHeight=20px）。

场景（管理员视角，夹具 __fo_ 前缀，含 1 个夹具看板；生产库另有 8 个 → 走 7 行上限分支）：
  A. 新会话首次打开：弹窗高度与 bcList maxHeight 均为正常值（非 20px 压扁态）
  B. 关闭后二次打开：尺寸与首开一致（相对断言，不硬编码绝对值）

⚠️ 夹具纪律：专属前缀 __fo_；try/finally 清理；断言用首开/二开相对比较。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9391
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__fo_'
U_ADMIN = P + 'admin'
PWD = 'At159357'
PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  x ') + msg)


def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-05 10:00:00'
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
              (P + U_ADMIN, U_ADMIN, now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
              " VALUES (?,?,?,?,?,?)", (U_ADMIN, hash_pw(PWD), 'admin', '*', '*', now))
    bid = 'FO' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,'','','',0,?)", (bid, P + '看板', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, '核算部', 0, '日常', '启用', now))
    c.commit(); c.close()
    return {'bid': bid}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        c.execute("DELETE FROM cards WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM board_config WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM boards WHERE board_id=?", (fx['bid'],))
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.commit(); c.close()


PROBE = ("(()=>{const m=document.querySelector('#boardConfigModal .modal');"
         "const box=document.getElementById('bcList');"
         "return {mh:m?m.offsetHeight:0,"
         "lmh:box?parseInt(box.style.maxHeight||'0',10):0,"
         "vis:box?box.offsetHeight:0};})()")


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_fo%d' % PORT)
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
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})

            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U_ADMIN), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                # ME 是脚本作用域 let/const，不在 window 上（与 ui_check_board_footer 同写法）
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            ok(bool(await ev("typeof ME!=='undefined'&&!!ME")), '登录成功')

            # ── A. 首次打开 ──
            await ev("openBoardConfigModal()")
            await asyncio.sleep(1.5)
            r1 = await ev(PROBE) or {}
            print('  首开实测:', r1)
            ok(r1.get('lmh', 0) > 200,
               '首开：bcList maxHeight 为正常值（>200px，压扁态是 20px；实际 %s）' % r1.get('lmh'))
            ok(r1.get('mh', 0) > 400,
               '首开：弹窗高度正常（>400px；实际 %s）' % r1.get('mh'))
            h1 = r1.get('mh', 0)

            # ── B. 关闭 → 二次打开 ──
            await ev("closeModal('boardConfigModal')")
            await asyncio.sleep(0.5)
            await ev("openBoardConfigModal()")
            await asyncio.sleep(1.5)
            r2 = await ev(PROBE) or {}
            print('  二开实测:', r2)
            h2 = r2.get('mh', 0)
            ok(abs(h1 - h2) <= 40,
               '二次打开与首开尺寸一致（|Δ|=%d，首开 %s / 二开 %s）' % (abs(h1 - h2), h1, h2))
            ok(r2.get('lmh', 0) > 200, '二开：bcList maxHeight 仍为正常值（实际 %s）' % r2.get('lmh'))
    finally:
        try:
            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/FI',
                            'WINDOWTITLE eq *cdp_fo*'], capture_output=True)
        except Exception:
            pass
        cleanup(fx)
        print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
        if FAIL:
            sys.exit(1)

asyncio.run(main())
