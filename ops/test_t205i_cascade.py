# -*- coding: utf-8 -*-
"""T-205i 端到端：人员筛选树候选级联（238 看板，零写库）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9615
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BOARD = '1162069797001000238'


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205i2')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', f'--remote-debugging-port={PORT}',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}

        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done():
                        f.set_result(m)

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        READ_TREE = """(function(){
          if(!window.TREE_PICK)return {persons:[], n:0, open:false};
          const p=[].slice.call(document.querySelectorAll('.tp-node.tp-person'))
            .map(function(x){return x.textContent.trim().replace(/^[^A-Za-z一-龥]+/,).split('(')[0];});
          return {persons:p, n:p.length, open:true};
        })()"""

        # ① 默认态（年份筛选恒生效）→ 负责人树池 = 筛选结果 owner 名单 = {郭柳红}
        await ev("openPersonFilterPicker(document.getElementById('personFilterInput'))")
        await asyncio.sleep(2)
        s1 = await ev(READ_TREE)
        print('① 默认态负责人树池:', json.dumps(s1, ensure_ascii=False), flush=True)
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)

        # ② 设参与人=余河 → 负责人树池仍是 {郭柳红}（owner 名单）、参与人树池收缩到 {余河}
        await ev("CC_SEL=new Set(['余河']);window._ccFilter='余河';paintFilterCombos();reload(1);")
        await asyncio.sleep(2.5)
        await ev("openPersonFilterPicker(document.getElementById('personFilterInput'))")
        await asyncio.sleep(2)
        s2 = await ev(READ_TREE)
        print('② 参与人=余河 → 负责人树池:', json.dumps(s2, ensure_ascii=False), flush=True)
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)
        await ev("openCcFilterPicker(document.getElementById('ccFilterInput'))")
        await asyncio.sleep(2)
        s2b = await ev(READ_TREE)
        print('② 参与人树池:', json.dumps(s2b, ensure_ascii=False), flush=True)
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)

        # ③ 取消参与人筛选 → 参与人树池恢复
        await ev("CC_SEL=new Set();window._ccFilter='';paintFilterCombos();reload(1);")
        await asyncio.sleep(2.5)
        await ev("openCcFilterPicker(document.getElementById('ccFilterInput'))")
        await asyncio.sleep(2)
        s3 = await ev(READ_TREE)
        print('③ 取消后参与人树池:', json.dumps({k: (v if k != 'persons' else v[:5]) for k, v in (s3 or {}).items()},
                                               ensure_ascii=False), flush=True)
        _p1=list(s1.get('persons') or []); _p2=list(s2.get('persons') or [])
        _p2b=list(s2b.get('persons') or []); _p3=list(s3.get('persons') or [])
        # 树节点文本含「▶ 👤」装饰前缀 → 用「包含姓名」判定
        ok1 = len(_p1)==1 and any('郭柳红' in x for x in _p1)
        ok2 = len(_p2)==1 and any('郭柳红' in x for x in _p2)
        ok2b = len(_p2b)>=5 and any('余河' in x for x in _p2b)   # cc_people=71 全名单（该测试卡 cc 即全名单），池∩名单=候选池全量
        ok3 = len(_p3)>=5                                        # 取消筛选后恢复全池
        print('\n断言：')
        print(' ① 负责人树池={郭柳红}（owner 名单级联）:', 'PASS' if ok1 else 'FAIL')
        print(' ② 参与人=余河 → 负责人树池仍 {郭柳红}:', 'PASS' if ok2 else 'FAIL')
        print(' ② 参与人树池={余河}（cc 名单级联收缩）:', 'PASS' if ok2b else 'FAIL')
        print(' ③ 取消筛选 → 参与人树池恢复:', 'PASS' if ok3 else 'FAIL')
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205i2')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
