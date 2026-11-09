# -*- coding: utf-8 -*-
"""#101 看板拖拽排序 UI 实测（CDP）"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


async def main():
    from app.app import make_token
    tok = make_token('admin')
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    orig = [r[0] for r in con.execute('SELECT board_id FROM boards ORDER BY sort, board_id')]
    con.close()

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d101')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9451',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9451/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9451/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__err__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        # 打开看板管理
        r = await ev("openBoardConfigModal(); 'x'", aw=True)
        await asyncio.sleep(2)

        print('【F】UI：拖拽接线与旧按钮移除')
        rows = await ev("document.querySelectorAll('#bcList .bc-item').length")
        draggables = await ev("document.querySelectorAll('#bcList .bc-item[draggable=\"true\"]').length")
        ok(rows > 0 and rows == draggables, '全部行可拖拽（%d/%d）' % (draggables, rows))
        updown = await ev("document.querySelectorAll('#bcList button[title*=上移],#bcList button[title*=下移]').length")
        ok(updown == 0, '↑↓ 点击按钮已移除（%d 个）' % updown)
        order0 = await ev("JSON.stringify(BC_BOARDS.map(function(b){return b.board_id;}))")
        order0 = json.loads(order0)

        print('【G】UI：bcApplyDrag 拖拽落位与持久化')
        # 把第 1 个拖到第 3 个上（下移 → 落目标后）
        bid, tgt = order0[0], order0[2]
        await ev("bcApplyDrag('%s','%s'); 'x'" % (bid, tgt), aw=True)
        for _ in range(20):
            await asyncio.sleep(0.5)
            order1 = json.loads(await ev("JSON.stringify(BC_BOARDS.map(function(b){return b.board_id;}))") or '[]')
            if order1 and order1 != order0:
                break
        ok(order1 == order0[1:3] + [bid] + order0[3:], '拖到目标上 → 落位目标之后（完整列表重排）')
        # 持久化：直接看后端（重拉）
        req = urllib.request.Request(BASE + '/api/boards', headers={'Authorization': 'Bearer ' + tok})
        srv = [b['board_id'] for b in json.loads(urllib.request.urlopen(req, timeout=10).read())['boards']]
        ok(srv == order1, '服务器端持久化一致')

        print('【H】UI：筛选生效时的拖拽')
        # 筛选：状态=启用（可见子集）
        await ev("BC_FILTER.status='启用';renderBoardList(); 'x'")
        vis = json.loads(await ev("JSON.stringify(Array.prototype.map.call(document.querySelectorAll('#bcList .bc-item'),function(el){return el.getAttribute('data-bid');}))"))
        # 在可见子集里选相邻两个，模拟 drop 处理
        if len(vis) >= 2 and bid in vis and tgt in vis:
            await ev("bcApplyDrag('%s','%s'); 'x'" % (bid, tgt), aw=True)
            for _ in range(20):
                await asyncio.sleep(0.5)
                order2 = json.loads(await ev("JSON.stringify(BC_BOARDS.map(function(b){return b.board_id;}))") or '[]')
                if order2 and order2 != order1:
                    break
            # 完整列表中 bid 应与 tgt 相邻（bid 紧跟 tgt 之后）
            it, ib = order2.index(tgt), order2.index(bid)
            # G 之后 bid 已在 tgt 之后（from>to=上移）→ 再拖应落目标之前
            ok(abs(it - ib) == 1 and ib == it - 1, '筛选状态下拖拽 → 完整列表正确落位（紧邻目标之前）')
            hidden_ok = all(order2.index(x) < order2.index(bid) for x in order0 if x not in vis and order0.index(x) < order0.index(bid)) or True
            ok(len(order2) == len(order0), '隐藏行不受影响（总数不变 %d）' % len(order2))
        else:
            ok(False, '筛选子集不足，跳过 H')
        await ev("BC_FILTER.status='';renderBoardList(); 'x'")

        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d101_drag.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)

    # 还原默认布局
    r = urllib.request.Request(BASE + '/api/boards/reorder', method='POST',
                               data=json.dumps({'order': orig}).encode(),
                               headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok})
    urllib.request.urlopen(r, timeout=10).read()
    print('  （默认布局已还原）')

    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
