# -*- coding: utf-8 -*-
"""T-205k-bis 防跳闪实测：
① 模拟真实点击序列（focus→click 双触发）→ 面板只创建一次（无拆建闪动）
② 已打开时再次调用 → 同一面板节点不重建
③ cc 树同款
④ 勾选→确定 → 筛选仍生效（功能无回退）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = '1162069797001000238'

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205kb')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9631',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9631/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    w = None
    ok_n = fail_n = 0
    def ok(cond, msg):
        nonlocal ok_n, fail_n
        print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
        if cond: ok_n += 1
        else: fail_n += 1
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9631/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50*1024*1024)
        pending = {}
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        seq = [0]
        async def send(mm, p=None):
            seq[0] += 1
            f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        # 记录面板创建次数：hook document.body.appendChild 统计 .tree-pick 挂载
        await ev("""window.__tpCreated=0;
          (function(){
            const orig=document.body.appendChild.bind(document.body);
            document.body.appendChild=function(el){
              if(el&&el.classList&&el.classList.contains('tree-pick'))window.__tpCreated++;
              return orig(el);
            };
          })();""")

        # ① 模拟真实点击：focus 事件 + click 事件（与浏览器同序）
        r1 = await ev("""(function(){
          const inp=document.getElementById('personFilterInput');
          inp.dispatchEvent(new Event('focus'));
          inp.click();
          return {triggered:true};
        })()""", aw=True)
        await asyncio.sleep(2.5)
        r1b = await ev("""(function(){
          return {open:!!window.TREE_PICK, src:window.TREE_PICK?window.TREE_PICK.srcAnchor:'',
                  created:window.__tpCreated,
                  panels:document.querySelectorAll('.tree-pick').length};
        })()""")
        ok(r1b and r1b.get('open') and r1b.get('created') == 1 and r1b.get('panels') == 1,
           "① focus+click 双触发 → 面板只创建 1 次（创建 %s、现存 %s 个，跳闪消除）"
           % (r1b.get('created'), r1b.get('panels')))
        ok(r1b and r1b.get('src') is not None and r1b.get('src') != '',
           "① srcAnchor 锚点正确（%r）" % r1b.get('src'))

        # ② 已打开时再次调用 → 不重建
        r2 = await ev("""(function(){
          const before=TREE_PICK.panel;
          openPersonFilterPicker(document.getElementById('personFilterInput'));
          return {samePanel:TREE_PICK.panel===before, created:window.__tpCreated};
        })()""")
        ok(r2 and r2.get('samePanel') is True and r2.get('created') == 1,
           "② 已打开时重复调用 → 同一面板不重建（创建计数仍 %s）" % r2.get('created'))

        # ③ 收起负责人树 → 打开参与人树（双触发）
        r3 = await ev("""(function(){
          closeTreePick();
          const inp=document.getElementById('ccFilterInput');
          inp.dispatchEvent(new Event('focus'));
          inp.click();
          return {ok:true};
        })()""", aw=True)
        await asyncio.sleep(2.5)
        r3b = await ev("""(function(){
          return {open:!!window.TREE_PICK, src:window.TREE_PICK?window.TREE_PICK.srcAnchor:'',
                  created:window.__tpCreated,
                  panels:document.querySelectorAll('.tree-pick').length};
        })()""")
        ok(r3b and r3b.get('open') and r3b.get('src') is not None
           and r3b.get('panels') == 1,
           "③ cc 树双触发 → 单面板、srcAnchor 已写入（现存 %s 个面板）" % r3b.get('panels'))

        # ④ 勾选 → 确定 → CC_SEL 生效（功能无回退）
        r4 = await ev("""(function(){
          const lab=[].slice.call(document.querySelectorAll('.tp-node.tp-person .tp-label'))
            .find(function(x){return x.textContent.indexOf('郭柳红')>=0;});
          if(!lab)return {err:'找不到郭柳红'};
          lab.click();
          // 点确定按钮（.tp-ok / data 属性）
          const btn=[].slice.call(document.querySelectorAll('.tree-pick button'))
            .find(function(b){return b.textContent.indexOf('确定')>=0;});
          if(!btn)return {err:'找不到确定按钮'};
          btn.click();
          return {picked:true};
        })()""")
        await asyncio.sleep(2)
        r4b = await ev("""(function(){
          return {ccSel:!!(CC_SEL&&CC_SEL.has('郭柳红')), ccFilter:window._ccFilter||'',
                  selList:CC_SEL?[...CC_SEL]:[]};
        })()""")
        ok(r4b and r4b.get('ccSel') and r4b.get('ccFilter') == '郭柳红',
           "④ 树内勾选→确定 → CC_SEL 存**纯姓名**（%s，_ccFilter=%r，后端可子串匹配）"
           % (r4b.get('selList'), r4b.get('ccFilter')))
        # 还原
        await ev("CC_SEL=new Set();window._ccFilter='';paintFilterCombos();reload(1);")
        print('---- 结果: %d PASS / %d FAIL ----' % (ok_n, fail_n), flush=True)
    finally:
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205kb')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
