# -*- coding: utf-8 -*-
"""#108 弹窗拖拽移动 实测（CDP 真实鼠标事件）"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d108')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9463',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9463/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9463/json', timeout=5).read())
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

        async def mouse(x, y, type_, btn='left', clicks=1):
            await send('Input.dispatchMouseEvent',
                       {'type': type_, 'x': int(x), 'y': int(y), 'button': btn, 'clickCount': clicks})

        async def drag(from_xy, to_xy, steps=12):
            x0, y0 = from_xy
            x1, y1 = to_xy
            await mouse(x0, y0, 'mousePressed')
            for s in range(1, steps + 1):
                await mouse(x0 + (x1 - x0) * s / steps, y0 + (y1 - y0) * s / steps, 'mouseMoved')
                await asyncio.sleep(0.02)
            await mouse(x1, y1, 'mouseReleased')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 800, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        await ev("(function(){const b=(ME.boards||[])[0];if(b)pickBoard(b.board_id);})()")
        await asyncio.sleep(3)

        print('【A】初始化覆盖')
        r = await ev("""(function(){
          const ov=[...document.querySelectorAll('.modal-overlay')];
          return {total:ov.length, inited:ov.filter(x=>x.querySelector('.modal')&&x.querySelector('.modal').dataset.dragInited).length};
        })()""")
        print('  探针:', r)
        ok(r.get('total', 0) == r.get('inited', 0) and r['total'] > 10,
           '静态弹窗全部初始化（%s/%s）' % (r.get('inited'), r.get('total')))

        print('【B】标题栏拖拽：跟随鼠标 + 松手停留')
        cid = await ev("(function(){const t=document.querySelector('.item-card .item-title');if(!t)return null;return t.getAttribute('onclick').match(/'([^']+)'/)[1];})()")
        ok(bool(cid), '卡片标题入口存在（cid=%s）' % str(cid)[:16])
        await ev("openDetail('%s');" % cid)
        await asyncio.sleep(1.2)
        disp = await ev("document.getElementById('detailModal').style.display")
        ok(disp == 'flex', '详情弹窗已打开（display=%s）' % disp)
        r0 = await ev("""(function(){
          const m=document.querySelector('#detailModal .modal');
          const r=m.getBoundingClientRect();
          return JSON.stringify({left:r.left,top:r.top,w:r.width,h:r.height});
        })()""")
        r0 = json.loads(r0)
        # 按住标题（modal 顶部 20px 处）拖动 (+320,+160)
        hx, hy = r0['left'] + r0['w'] / 2, r0['top'] + 18
        await drag((hx, hy), (hx + 320, hy + 160))
        await asyncio.sleep(0.3)
        r1 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top};})())"))
        dx, dy = r1['left'] - r0['left'], r1['top'] - r0['top']
        print('  位移:', round(dx), round(dy))
        # 预期位移要考虑边界钳制：右缘不得超过 视口宽-8（弹窗宽 900 时 320 必被钳制）
        dx_exp = min(320, 1280 - 8 - r0['left'] - r0['w'])
        dx_exp = max(dx_exp, 8 - r0['left'])          # 左缘钳制兜底
        ok(abs(dx - dx_exp) < 6 and abs(dy - 160) < 6,
           '弹窗跟随鼠标且贴边被钳制（位移 %s,%s，预期 %s,160）' % (round(dx), round(dy), round(dx_exp)))
        # 松手后停留（再等 0.5s 位置不变）
        await asyncio.sleep(0.5)
        r2 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top};})())"))
        ok(abs(r2['left'] - r1['left']) < 1 and abs(r2['top'] - r1['top']) < 1, '松开后停留在新位置')

        print('【C】边界限制：拖出可视区域被钳制')
        await drag((r0['left'] + r0['w'] / 2 + 320, r0['top'] + 18 + 160), (r0['left'] + r0['w'] / 2 + 1200, r0['top'] + 18 - 700))
        await asyncio.sleep(0.3)
        r3 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom};})())"))
        print('  极限拖后 rect:', r3)
        vw, vh = 1280, 800
        ok(r3['left'] >= 0 and r3['top'] >= 0 and r3['right'] <= vw and r3['bottom'] <= vh,
           '弹窗整体未拖出可视区域（left %s top %s right %s bottom %s ≤ 1280×800）'
           % (round(r3['left']), round(r3['top']), round(r3['right']), round(r3['bottom'])))

        print('【D】交互不冲突：正文输入/按钮可正常操作，不被拖拽劫持')
        # 在弹窗正文里 mousedown+move+up —— 弹窗不应移动
        r4 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top};})())"))
        bx, by = r4['left'] + 200, r4['top'] + 200
        await drag((bx, by), (bx + 150, by + 150))
        r5 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top};})())"))
        ok(abs(r5['left'] - r4['left']) < 1 and abs(r5['top'] - r4['top']) < 1, '正文区拖动不移动弹窗（交互不冲突）')
        # 关闭按钮仍可点击（header 内 button 不被拖拽劫持）
        await ev("(function(){const b=document.querySelector('#detailModal .modal-close');const r=b.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()")
        close_pos = json.loads(await ev("JSON.stringify((function(){const b=document.querySelector('#detailModal .modal-close');const r=b.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})())"))
        await mouse(close_pos['x'], close_pos['y'], 'mousePressed')
        await mouse(close_pos['x'], close_pos['y'], 'mouseReleased')
        await asyncio.sleep(0.6)
        closed = await ev("document.getElementById('detailModal').style.display==='none'")
        ok(closed, '标题栏内关闭按钮点击正常（拖拽不劫持按钮）')

        print('【E】重新打开：位置重置（原设计保留）+ 全部弹窗仍可拖')
        await ev("(function(){const b=document.querySelector('.item-card .item-title');const m=b.getAttribute('onclick').match(/'([^']+)'/);openDetail(m[1]);})()")
        await asyncio.sleep(1)
        r6 = json.loads(await ev("JSON.stringify((function(){const r=document.querySelector('#detailModal .modal').getBoundingClientRect();return {left:r.left,top:r.top};})())"))
        ok(abs(r6['left'] - r0['left']) < 8 and abs(r6['top'] - r0['top']) < 8,
           '重新打开后位置重置回原布局位')
        await ev("closeModal('detailModal');")

        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d108_modal_drag.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)
    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
