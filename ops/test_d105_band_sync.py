# -*- coding: utf-8 -*-
"""#105 架构排序 → 外部目录顺序实时同步 实测（CDP，v2）"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


def api_reorder(tok, nid, direction):
    r = urllib.request.Request(BASE + '/api/org/nodes/%d/reorder' % nid, method='POST',
                               data=json.dumps({'direction': direction}).encode(),
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + tok})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())


async def main():
    from app.app import make_token
    tok = make_token('admin')

    # 归一化还原起点（防此前测试残留）：sort=id 序
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    ids = [r[0] for r in con.execute("SELECT id FROM org_nodes WHERE parent_id=1 ORDER BY sort, id")]
    con.close()

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d105b')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9460',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9460/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9460/json', timeout=5).read())
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

        async def login():
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True:
                    break
            await asyncio.sleep(2.5)

        async def band_order():
            r = await ev("JSON.stringify([...document.querySelectorAll('#tbDepts .tree-dept')]"
                         ".map(x=>x.childNodes[1]?x.childNodes[1].textContent.trim():''))")
            return json.loads(r) if isinstance(r, str) else (r or [])

        async def me_depts():
            return json.loads(await ev("JSON.stringify(ME.depts||[])"))

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await login()

        print('【A】页面加载：目录带顺序 = 架构排序（后端 ME.depts）')
        d0 = await me_depts()
        b0 = await band_order()
        print('  ME.depts:', d0)
        print('  目录带 DOM:', b0)
        ok(len(b0) == len(d0) and b0 == d0, '目录带 DOM 顺序与 ME.depts 完全一致（%s）' % b0)

        print('【B】架构排序（API）→ 刷新页面 → 目录带跟随')
        # 把当前第二位的部门上移（与第一位交换）
        nid = ids[1]
        api_reorder(tok, nid, 'up')
        new_ids = [nid] + ids[:1] + ids[2:]
        await login()   # 刷新页面
        d1 = await me_depts()
        b1 = await band_order()
        expect_names = []
        con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        for bid in new_ids:
            nm = con.execute('SELECT name FROM org_nodes WHERE id=?', (bid,)).fetchone()[0]
            expect_names.append(nm)
        con.close()
        print('  预期:', ['财务中心'] + expect_names)
        print('  ME.depts:', d1)
        ok(d1 == ['财务中心'] + expect_names, '排序后 ME.depts 跟随（%s）' % d1)
        ok(b1 == d1, '刷新后目录带 DOM 顺序 = 新架构顺序（%s）' % b1)

        print('【C】会话内实时：orgMoveNode → 目录带不刷新页面即时更新')
        # 打开架构管理（加载 ORG_TREE）→ 关闭 → 调 orgMoveNode（首位下移）
        await ev("openWgModal(); 'x'", aw=True)
        await asyncio.sleep(2)
        await ev("closeModal('wgModal');")
        await asyncio.sleep(0.5)
        before = await me_depts()
        r = await ev("(function(){const f=ORG_TREE[0].children[0];return f.name;})()")
        print('  移动节点:', r, '（下移）')
        await ev("orgMoveNode(ORG_TREE[0].children[0].id,'down'); 'x'", aw=True)
        for _ in range(20):
            await asyncio.sleep(0.5)
            d2 = await me_depts()
            if d2 != before:
                break
        b2 = await band_order()
        print('  ME.depts:', d2)
        print('  目录带 DOM:', b2)
        ok(d2 != before and d2[1] != before[1], 'orgMoveNode 后 ME.depts 会话内即时更新（%s）' % d2[:3])
        ok(b2 == d2, '未刷新页面下目录带 DOM 即时同序（%s）' % b2)
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d105_band_sync.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)

    # 还原
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    for idx, nid in enumerate(ids):
        con.execute('UPDATE org_nodes SET sort=? WHERE id=?', (idx, nid))
    con.commit()
    con.close()
    print('  （org 顺序已还原）')
    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
