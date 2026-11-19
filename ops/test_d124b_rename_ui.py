# -*- coding: utf-8 -*-
"""#124 CDP 实测：编辑看板配置界面修改看板名称 → 保存生效 → 顶栏卡片同步 → 还原"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9428
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d124')
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
                   {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)
        # 展开看板最多的部门并选中其第一个看板
        setup = await ev("""(function(){
          const g=groupBoardsByDept();
          let best=null,bn=0;
          g.depts.forEach(d=>{if(d.boards.length>bn){bn=d.boards.length;best=d}});
          if(!best)return {none:true};
          DEPT_OPEN[best.name]=true;
          renderTabs();
          return {bid:best.boards[0].board_id,name:best.boards[0].board_name};
        })()""")
        if setup.get('none'):
            ok(False, '无看板'); return
        bid, origName = setup['bid'], setup['name']
        print('目标看板：%s (%s)' % (origName, bid))
        tmpName = origName + '·改名测试'

        print('【① 编辑界面出现名称输入框并回填】')
        await ev("openBoardConfigModalFor('%s')" % bid)
        await asyncio.sleep(3)
        r1 = await ev("""(function(){
          const inp=document.getElementById('bc_board_name');
          return {exists:!!inp, value:inp?inp.value:'', editable:inp?!inp.disabled:false,
                  modal:document.getElementById('boardConfigModal').style.display==='flex'};
        })()""")
        ok(r1.get('exists') and r1.get('modal'), '编辑界面有「看板名称」输入框')
        ok(r1.get('value') == origName, '回填现有名称：%s' % r1.get('value'))
        ok(r1.get('editable'), '管理员可编辑')

        print('【② 改名保存 → 弹窗关闭 + 顶栏同步】')
        # ⚠️ 必须 IIFE：`const i=...` 会污染页面全局作用域，后续同一段代码
        #    再执行就重复声明 SyntaxError，赋值+保存整段被吞（③ 还原失败的根因）
        await ev("(function(){var i=document.getElementById('bc_board_name');i.value=%s;i.dispatchEvent(new Event('input'));saveBoardAll();})()"
                 % json.dumps(tmpName, ensure_ascii=False))
        await asyncio.sleep(3)
        r2 = await ev("""(function(){
          const card=[...document.querySelectorAll('#tbBoards .tab-btn')].find(x=>(x.getAttribute('onclick')||'').indexOf('%s')>=0);
          return {closed:document.getElementById('boardConfigModal').style.display!=='flex',
                  cardName:card?card.querySelector('.tab-name').textContent:'',
                  meName:(ME.boards.find(x=>x.board_id==='%s')||{}).board_name};
        })()""" % (bid, bid))
        ok(r2.get('closed'), '保存后弹窗自动关闭（卡片入口）')
        ok(r2.get('cardName') == tmpName, '顶栏看板卡片显示新名：%s' % r2.get('cardName'))
        ok(r2.get('meName') == tmpName, 'ME.boards 已刷新（%s）' % r2.get('meName'))

        print('【③ 还原原名】')
        await ev("openBoardConfigModalFor('%s')" % bid)
        await asyncio.sleep(3)
        await ev("(function(){var i=document.getElementById('bc_board_name');i.value=%s;i.dispatchEvent(new Event('input'));saveBoardAll();})()"
                 % json.dumps(origName, ensure_ascii=False))
        await asyncio.sleep(3)
        r3 = await ev("""(function(){
          const card=[...document.querySelectorAll('#tbBoards .tab-btn')].find(x=>(x.getAttribute('onclick')||'').indexOf('%s')>=0);
          return {cardName:card?card.querySelector('.tab-name').textContent:'',
                  meName:(ME.boards.find(x=>x.board_id==='%s')||{}).board_name,
                  closed:document.getElementById('boardConfigModal').style.display!=='flex'};
        })()""" % (bid, bid))
        ok(r3.get('meName') == origName, 'ME.boards 还原原名：%s' % r3.get('meName'))
        ok(r3.get('cardName') == origName and r3.get('closed'), '顶栏卡片还原原名且弹窗关闭')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
