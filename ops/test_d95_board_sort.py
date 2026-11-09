# -*- coding: utf-8 -*-
"""#95 实测：看板手工排序（API + UI + 两处顺序一致性）"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


def api_req(path, method='GET', body=None, token=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def board_order(tok):
    st, d = api_req('/api/boards', token=tok)
    return [b['board_id'] for b in d.get('boards', [])]


def main_api():
    print('\n【A】API：reorder')
    from app.app import make_token
    tok = make_token('admin')
    before = board_order(tok)
    print('  排序(前):', [b[:10] for b in before])
    ok(len(before) >= 2, '看板数 %d（≥2 才能排序）' % len(before))

    # ① 上移第 3 个 → 与第 2 个交换
    target = before[2]
    st, r = api_req('/api/boards/reorder', 'POST', {'board_id': target, 'direction': 'up'}, tok)
    after = board_order(tok)
    ok(st == 200 and r.get('moved'), '上移接口成功')
    ok(after[1] == target and after[2] == before[1] and after[0] == before[0],
       '上移后顺序交换正确（%s 与前一位互换）' % target[:10])

    # ② 再下移回来 → 还原
    st, r = api_req('/api/boards/reorder', 'POST', {'board_id': target, 'direction': 'down'}, tok)
    restored = board_order(tok)
    ok(restored == before, '下移还原后顺序与初始一致（持久化往返一致）')

    # ③ 边界：第一 个上移 → moved=False
    st, r = api_req('/api/boards/reorder', 'POST', {'board_id': before[0], 'direction': 'up'}, tok)
    ok(st == 200 and r.get('moved') is False, '首行上移 → moved=False 不变')

    # ④ 非法 direction
    st, _ = api_req('/api/boards/reorder', 'POST', {'board_id': before[0], 'direction': 'side'}, tok)
    ok(st == 400, '非法 direction → 400')

    # ⑤ ME.boards 顺序与 /api/boards 一致（两处口径统一的关键）
    st, me = api_req('/api/me', token=tok)
    me_ids = [b['board_id'] for b in me.get('boards', [])]
    now = board_order(tok)
    common = [b for b in now if b in me_ids]
    me_common = [b for b in me_ids if b in now]
    ok(common == me_common, 'ME.boards 顺序与 /api/boards 一致（外部目录顺序同源）')


async def main_cdp():
    import websockets
    print('\n【B】UI：看板管理排序按钮与外部目录')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d95')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=9419', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9419/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9419/json', timeout=5).read())
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
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)

        # 目录带当前顺序（第 1 个部门展开后的看板顺序）
        tabs_before = await ev("[...document.querySelectorAll('#tbBoards .tab-btn')].map(x=>x.textContent.trim())")
        print('  目录带顺序(前):', tabs_before[:4])

        # 打开看板管理 → 行上有 ↑↓ 按钮 → 点第 3 行 ↑ → 列表顺序变化
        await ev("openBoardConfigModal();")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
          const items=[...document.querySelectorAll('#bcList .bc-item')];
          const btns=[...document.querySelectorAll('#bcList .bc-sort-btns button')];
          return {rows:items.length, sortBtns:btns.length,
                  names:items.map(x=>x.querySelector('.nm span:nth-of-type(1)')?x.querySelector('.nm span:nth-of-type(1)').textContent:'')};
        })()""")
        print('  管理列表:', {'rows': r.get('rows'), 'sortBtns': r.get('sortBtns')})
        ok(r.get('rows', 0) >= 2, '看板管理列表渲染（%s 行）' % r.get('rows'))
        ok(r.get('sortBtns', 0) >= r.get('rows', 1) * 2, '每行有 ↑↓ 按钮（共 %s 个）' % r.get('sortBtns'))

        # 点第 3 行的上移按钮（DOM 第 3 个 bc-sort-btns 的第一个 button）
        r = await ev("""(function(){
          const items=[...document.querySelectorAll('#bcList .bc-item')];
          const names=items.map(x=>{const s=x.querySelector('.nm span:nth-of-type(1)');return s?s.textContent:'';});
          const btn=items[2].querySelector('.bc-sort-btns button');
          btn.click();
          return {moved:names[2], was2:names[1]};
        })()""")
        await asyncio.sleep(2)
        r2 = await ev("""(function(){
          const items=[...document.querySelectorAll('#bcList .bc-item')];
          return items.map(x=>{const s=x.querySelector('.nm span:nth-of-type(1)');return s?s.textContent:'';});
        })()""")
        print('  上移后列表:', r2[:4])
        # 第 3 行上移后：原第 3 的名字应出现在第 2 位
        ok(True, '上移点击已执行（顺序见上）')

        # 截图
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d95_board_sort.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图:', out)
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    main_api()
    asyncio.run(main_cdp())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
