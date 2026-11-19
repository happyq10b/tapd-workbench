# -*- coding: utf-8 -*-
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9433
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASS = 0
FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1
        print('  PASS', m)
    else:
        FAIL += 1
        print('  FAIL', m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d126f')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=50 * 1024 * 1024) as w:
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

        async def hint():
            return await ev("""(function(){
              const h=document.getElementById('boardSelHint');
              const cs=getComputedStyle(h);
              return {text:h.textContent,fs:cs.fontSize,color:cs.color};
            })()""")

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)

        print('【① 初始未选】')
        h0 = await hint()
        print('  ', json.dumps(h0, ensure_ascii=False))
        ok(h0.get('text') == '未选择看板', '未选时显示「未选择看板」：%s' % h0.get('text'))
        ok(h0.get('fs') == '12px', '字体与筛选明细同款（12px 灰字）')

        print('【② 多选两个看板】')
        ids = await ev("""(function(){
          var g=groupBoardsByDept();var d=g.depts.find(function(x){return x.boards.length>=2});
          if(!d)return [];
          DEPT_OPEN[d.name]=true;renderTabs();
          pickBoard(d.boards[0].board_id);pickBoard(d.boards[1].board_id);
          return [d.boards[0].board_name,d.boards[1].board_name];
        })()""")
        await asyncio.sleep(2)
        h1 = await hint()
        print('  ', json.dumps(h1, ensure_ascii=False), '预期看板:', json.dumps(ids, ensure_ascii=False))
        expect = '已选：' + '、'.join(ids)
        ok(h1.get('text') == expect, '已选明细按目录顺序列出两个看板：%s' % h1.get('text'))
        ok(h1.get('fs') == '12px', '字体 12px')

        print('【③ 全部取消 → 回到未选】')
        await ev("clearBoardSelection('已取消选择');renderTabs();")
        await asyncio.sleep(1)
        h2 = await hint()
        print('  ', json.dumps(h2, ensure_ascii=False))
        ok(h2.get('text') == '未选择看板', '取消选择后回到「未选择看板」')

    print('\n结果：PASS=%d FAIL=%d' % (PASS, FAIL))


if __name__ == '__main__':
    asyncio.run(main())
