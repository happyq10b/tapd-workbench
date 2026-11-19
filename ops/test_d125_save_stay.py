# -*- coding: utf-8 -*-
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9431
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BID = 'BCP1793717004248'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d125f')
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
        await ev("(function(){var g=groupBoardsByDept();var d=g.depts.find(function(x){return x.boards.some(function(b){return b.board_id==='%s'})})||g.depts.find(function(x){return x.boards.length});if(d){DEPT_OPEN[d.name]=true;}renderTabs();})()" % BID)
        await asyncio.sleep(1.5)

        print('【① 卡片入口 → 保存 → 弹窗保持打开 + toast】')
        await ev("openBoardConfigModalFor('%s')" % BID)
        await asyncio.sleep(3)
        await ev("(function(){var i=document.getElementById('bc_remark');i.value='#125 留窗验证';i.dispatchEvent(new Event('input'));saveBoardAll();})()")
        await asyncio.sleep(3)
        r1 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent});
          return {open:document.getElementById('boardConfigModal').style.display==='flex',
                  toast:toasts.join('|'),
                  fromCard:(typeof BC_FROM_CARD!=='undefined')&&BC_FROM_CARD===true};
        })()""")
        ok(r1.get('open') is True, '弹窗保持打开（卡片入口保存不再退出）')
        ok('已保存' in (r1.get('toast') or ''), '悬浮提示出现：%s' % r1.get('toast'))
        ok(r1.get('fromCard'), '入口标记保留（取消仍可关窗）')

        print('【② 取消 → 关闭弹窗】')
        await ev("resetBoardConfigForm()")
        await asyncio.sleep(1)
        ok(await ev("document.getElementById('boardConfigModal').style.display!=='flex'"),
           '「取消」仍关闭弹窗（轻量入口语义不变）')

        print('【③ 备注还原】')
        await ev("openBoardConfigModalFor('%s')" % BID)
        await asyncio.sleep(3)
        await ev("(function(){var i=document.getElementById('bc_remark');i.value='';i.dispatchEvent(new Event('input'));saveBoardAll();})()")
        await asyncio.sleep(3)
        r3 = await ev("(function(){var b=BC_BOARDS.find(function(x){return x.board_id==='%s'});return b.remark;})()" % BID)
        ok(r3 == '', '备注已还原（%r）' % r3)
        await ev("resetBoardConfigForm()")

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
