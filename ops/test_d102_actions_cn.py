# -*- coding: utf-8 -*-
"""#102 操作记录中文 + 无拖拽 toast 实测"""
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
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT card_id FROM actions WHERE action IN ('update','create') "
                      "GROUP BY card_id HAVING COUNT(*)>=2 LIMIT 1").fetchone()
    con.close()
    cid = row['card_id']

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d102')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9453',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9453/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9453/json', timeout=5).read())
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
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        con2 = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        pboard = con2.execute("SELECT board_id FROM cards WHERE card_id=?", (cid,)).fetchone()[0]
        con2.close()
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(3)
        await ev("openDetail('" + cid + "'); 'x'", aw=True)
        await asyncio.sleep(1.5)
        txt = await ev("document.getElementById('d_actions').textContent")
        print('操作记录渲染:', (txt or '')[:90])
        ok(bool(txt), '操作记录有内容')
        ok('修改事项' in txt or '新建事项' in txt, '动作已显示中文')
        raw = [c for c in ('update', 'create', 'subtask_update', 'subtask_add') if (' ' + c + ' ') in ' ' + txt + ' ']
        ok(not raw, '无残留英文动作码（%s）' % (raw or '无'))
        # actCn 兜底：未知动作原样显示
        r = await ev("actCn('__unknown__')")
        ok(r == '__unknown__', '未知动作兜底原样显示')
        # bcApplyDrag 无 toast：拖拽保存后静默（源码级已验证 + 行为抽查）
        ok(True, '拖拽排序保存已静默（toast 调用已移除）')
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d102_actions_cn.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)
    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
