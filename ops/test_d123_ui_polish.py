# -*- coding: utf-8 -*-
"""#122 实测：看板带两行完整显示（动态量高）+ 搜索区一体化 + 仅按钮/回车触发搜索"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9423
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d123t')
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
                return {'__error__': str(r['exceptionDetails'])[:400]}
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
        # 展开一个看板最多的部门（保证 ≥3 行，可验证滚动）
        await ev("""(function(){
          const g=groupBoardsByDept();
          let best=null,bn=0;
          g.depts.forEach(d=>{if(d.boards.length>bn){bn=d.boards.length;best=d}});
          if(best){DEPT_OPEN[best.name]=true;}
          renderTabs();
        })()""")
        await asyncio.sleep(1.5)

        print('【① 可选看板带：两行完整显示】')
        r1 = await ev("""(function(){
          const grid=document.getElementById('tbBoards');
          const items=[...grid.children];
          const gap=parseFloat(getComputedStyle(grid).rowGap)||6;
          const h1=items[0].getBoundingClientRect().height;
          const h2=items.length>1?items[1].getBoundingClientRect().height:h1;
          const need=h1+gap+h2;
          return {n:items.length,h1:Math.round(h1),h2:Math.round(h2),need:Math.round(need),
                  client:grid.clientHeight,maxH:grid.style.maxHeight,
                  clipped:grid.clientHeight<need-1};
        })()""")
        ok(r1.get('n', 0) >= 3, '展开部门含 %s 个看板（≥3 行，可验证滚动）' % r1.get('n'))
        ok(not r1.get('clipped'), '两行完整可见：需 %spx，可视 %spx（行高 %s/%s）'
           % (r1.get('need'), r1.get('client'), r1.get('h1'), r1.get('h2')))
        ok(str(r1.get('maxH') or '') not in ('', '82px'), 'maxHeight 由 JS 动态写入：%s' % r1.get('maxH'))

        print('【② 搜索区一体化】')
        r2 = await ev("""(function(){
          const g=document.querySelector('.search-group');
          const inp=document.getElementById('searchInput');
          const btn=g?g.querySelector('.search-btn'):null;
          if(!g||!inp||!btn)return {missing:true};
          const a=inp.getBoundingClientRect(),b=btn.getBoundingClientRect();
          const cb=getComputedStyle(inp);
          return {attached:Math.abs(b.left-a.right)<1,
                  sameH:Math.abs(b.height-a.height)<2,
                  inputNoBorder:cb.borderStyle==='none'||cb.borderTopWidth==='0px',
                  groupR:getComputedStyle(g).borderRadius};
        })()""")
        if r2.get('missing'):
            ok(False, '搜索组缺失：%s' % r2)
        else:
            ok(r2.get('attached'), '按钮贴输入框右侧（拼接为整体）')
            ok(r2.get('sameH'), '输入框与按钮同高')
            ok(r2.get('inputNoBorder'), '输入框自身无边框（边框由组件容器承载）')

        print('【③ 搜索行为：仅按钮/回车触发】')
        await ev("""(function(){
          window.__rc=0;const _r=window.reload;
          window.reload=function(p){window.__rc++;return _r(p)};
          const inp=document.getElementById('searchInput');
          inp.value='测试输入不触发';
          inp.dispatchEvent(new Event('input'));
        })()""")
        await asyncio.sleep(1)
        c1 = await ev("window.__rc")
        ok(c1 == 0, '输入文字（input 事件）不触发搜索（触发数=%s）' % c1)
        await ev("document.querySelector('.search-group .search-btn').click()")
        await asyncio.sleep(0.5)
        c2 = await ev("window.__rc")
        ok(c2 == 1, '点击「搜索」按钮触发一次（触发数=%s）' % c2)
        await ev("document.getElementById('searchInput').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))")
        await asyncio.sleep(0.5)
        c3 = await ev("window.__rc")
        ok(c3 == 2, '回车触发一次（触发数=%s）' % c3)

        print('【④ 搜索功能回归（点击后出结果）】')
        from app.app import make_token
        g = await ev("(function(){window.reload=window.__origReload||window.reload;return 'ok';})()")
        await ev("clearBoardSelection('已取消选择');renderTabs();")
        await ev("document.getElementById('searchInput').value=%s;reload(1);'fired'" % json.dumps('测试', ensure_ascii=False))
        await asyncio.sleep(2)
        sr = await ev("!!document.querySelector('#boardContent .sr-wrap')")
        ok(sr, '未选看板 + 点按钮后全局搜索出结果（#121 回归）')
        await ev("document.getElementById('searchInput').value='';reload(1);")

        print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
        for f in FAIL:
            print('  -', f)
        shot = await send('Page.captureScreenshot', {'format': 'png', 'clip': {'x': 0, 'y': 0, 'width': 1440, 'height': 480, 'scale': 1}})
        import base64
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d123_after.png', 'wb').write(base64.b64decode(shot['data']))
        print('截图: ops/.shots/d123_after.png')


if __name__ == '__main__':
    asyncio.run(main())
