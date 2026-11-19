# -*- coding: utf-8 -*-
"""#118 实测：统计卡片在事项状态变更后**无需刷新页面**立即更新

根因背景：
  · 后端所有卡片变更 WS 广播 exclude=操作者本人 → 本机收不到自己的广播；
  · toggleCardDone（勾选完成）/ setCardStatus（弹窗改状态）此前只 reload 不刷统计
    → 四张统计卡（总事项/已完成/进行中/未完成）只有 F5 才更新。
修复后：两条路径本地显式调 renderProgress()，并带请求序号防乱序回落。

验证口径（不刷新页面、不依赖全局基线数字）：
  ① 真实勾选一张主事项为 done → 「已完成」+1 且「未完成/进行中」相应 -1
  ② 立即改回原状态 → 数字还原
  ③ 全程 window.__t 标记不变 = 页面没有 reload
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.parse
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9416
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


def api_get(path, token):
    q = urllib.parse.quote(path.split('?', 1)[1], safe='=&,') if '?' in path else ''
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + token})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


async def main():
    from app.app import make_token
    tok = make_token('admin')
    # 找一个有主事项的看板（相对断言，不依赖具体板块）
    d = api_get('/api/cards?size=500', tok)
    cards = [c for c in d['cards'] if not (c.get('parent_id') or '')]
    if not cards:
        print('库中无主事项，测试跳过'); return
    target = cards[0]
    bid = target['board_id']
    orig_status = target['status'] if target['status'] in ('done', 'progressing') else 'open'

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d119')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
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
        await ev("pickBoard('%s');window.__t=Date.now();" % bid)
        await asyncio.sleep(3)

        async def stats():
            return await ev("[...document.querySelectorAll('#progressOverview .stat-value')].map(x=>x.textContent)")

        before = await stats()
        ok(isinstance(before, list) and len(before) == 4, '四张统计卡渲染：%s' % json.dumps(before, ensure_ascii=False))

        # ① 勾选完成（不刷新页面）
        new_st = 'done' if orig_status != 'done' else 'open'
        await ev("toggleCardDone('%s',%s,false);'fired'" % (target['card_id'], 'true' if new_st == 'done' else 'false'))
        await asyncio.sleep(2.5)
        after = await stats()
        same_page = await ev("window.__t")
        ok(same_page and await ev("typeof window.__t!=='undefined'") and before != after,
           '勾选后统计卡变化：%s → %s（页面未刷新）' % (json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False)))
        # 数字方向校验
        if new_st == 'done':
            ok(int(after[1]) == int(before[1]) + 1, '已完成 +1：%s→%s' % (before[1], after[1]))
        else:
            ok(int(after[1]) == int(before[1]) - 1, '已完成 -1：%s→%s' % (before[1], after[1]))

        # ② 立即改回原状态 → 数字还原
        await ev("toggleCardDone('%s',%s,false);'fired'" % (target['card_id'], 'true' if orig_status == 'done' else 'false'))
        await asyncio.sleep(2.5)
        restored = await stats()
        ok(restored == before, '改回后数字还原：%s' % json.dumps(restored, ensure_ascii=False))

        # ③ setCardStatus 路径（编辑弹窗头部状态按钮）
        await ev("openEdit('%s');" % target['card_id'])
        await asyncio.sleep(1.5)
        await ev("setCardStatus('e','progressing');'fired'")
        await asyncio.sleep(2.5)
        st3 = await stats()
        ok(int(st3[2]) == int(before[2]) + 1, '弹窗改「进行中」→ 进行中 +1：%s→%s' % (before[2], st3[2]))
        await ev("setCardStatus('e','%s');" % orig_status)
        await asyncio.sleep(2.5)
        st4 = await stats()
        ok(st4 == before, '状态还原 → 统计还原：%s' % json.dumps(st4, ensure_ascii=False))
        await ev("closeEdit();")

        # 页面始终未 reload
        ok(await ev("window.__t") == same_page, '全程无页面刷新（window.__t 未变）')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
