# -*- coding: utf-8 -*-
"""T-204y（2026-11-17 #142）看板板块默认折叠 CDP 实测：
  ① 单选看板 → 板块默认折叠（全部 .week-group 无 open，week-body 不可见）
  ② 手动点 ▶ 展开 → reload(1) 重绘后该板块仍展开（COL_OPEN 记忆恢复），
    其余板块保持折叠
  ③ 再点 ▶ 收起 → reload 后保持折叠
  ④ 多选看板 → 同样默认折叠（单选/多选行为一致）
  ⑤ collapseAll → 记忆清空；expandAll → 全展开且记忆恢复
  ⑥ 无 JS 错误
只读验证（不写库）；D6：一次性 __cdp_ui 账号 + 树杀 + 强制下线。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9557
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BID = '1162069797001000243'   # 收入工作事项（真实看板，只读）
BID2 = '1162069797001000241'  # 成本工作事项（多选对照）
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


async def main():
    import websockets
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204y')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}

        async def reader():
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') is not None and msg['id'] in pending:
                    fut = pending.pop(msg['id'])
                    if fut and not fut.done():
                        fut.set_result(msg)

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
            res = await asyncio.wait_for(fut, timeout=30)
            return res.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        rt = asyncio.create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_ui))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'"
                        "&&(ME.boards||[]).length>0") is True:
                break
        await asyncio.sleep(2)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # ① 单选看板 → 板块默认折叠
        await ev("pickBoard('%s')" % BID)
        await asyncio.sleep(2.5)
        r1 = await ev("""(function(){
          const gs=[...document.querySelectorAll('.week-group')];
          return {n:gs.length, openN:gs.filter(g=>g.classList.contains('open')).length,
                  bodyShown:gs.some(g=>{const b=g.querySelector('.week-body');return b&&b.offsetParent!==null;})};
        })()""")
        ok(r1.get('n', 0) > 0 and r1.get('openN') == 0 and not r1.get('bodyShown'),
           f"① 单选看板 → {r1.get('n')} 个板块全部默认折叠（open={r1.get('openN')}，内容不可见）")

        # ② 手动展开第一个板块 → reload 重绘后记忆恢复，其余保持折叠
        r2a = await ev("""(function(){
          const g=document.querySelector('.week-group');
          g.querySelector('.chev').click();
          return {ck:g.getAttribute('data-ck'), open:g.classList.contains('open'), mem:COL_OPEN.has(g.getAttribute('data-ck'))};
        })()""")
        ok(r2a.get('open') is True and r2a.get('mem') is True,
           f"② 手动点 ▶ → 板块展开且记入 COL_OPEN（{r2a.get('ck')}）")
        await ev("reload(1)")
        await asyncio.sleep(2.5)
        r2b = await ev("""(function(){
          const gs=[...document.querySelectorAll('.week-group')];
          const hit=gs.find(g=>g.getAttribute('data-ck')===%s);
          return {n:gs.length, hitOpen:!!hit&&hit.classList.contains('open'),
                  otherOpen:gs.filter(g=>g.getAttribute('data-ck')!==%s&&g.classList.contains('open')).length};
        })()""" % (json.dumps(r2a.get('ck')), json.dumps(r2a.get('ck'))))
        ok(r2b.get('hitOpen') is True and r2b.get('otherOpen') == 0,
           f"② reload 重绘 → 手动展开的板块保持展开（{r2b.get('hitOpen')}），其余 {r2b.get('n')-1} 个仍折叠")

        # ③ 再点收起 → reload 后保持折叠
        await ev("document.querySelector('.week-group .chev').click()")
        await asyncio.sleep(0.5)
        await ev("reload(1)")
        await asyncio.sleep(2.5)
        r3 = await ev("(function(){const gs=[...document.querySelectorAll('.week-group')];"
                      "return {openN:gs.filter(g=>g.classList.contains('open')).length, mem:COL_OPEN.size};})()")
        ok(r3.get('openN') == 0 and r3.get('mem') == 0,
           f"③ 再点收起 → reload 后保持折叠（open={r3.get('openN')}，COL_OPEN={r3.get('mem')}）")

        # ④ 多选看板 → 同样默认折叠（单选/多选一致）
        await ev("pickBoard('%s')" % BID2)
        await asyncio.sleep(2.5)
        r4 = await ev("""(function(){
          const gs=[...document.querySelectorAll('.week-group')];
          return {nBoards:curBoards.size, n:gs.length,
                  openN:gs.filter(g=>g.classList.contains('open')).length};
        })()""")
        ok(r4.get('nBoards') == 2 and r4.get('n', 0) > 0 and r4.get('openN') == 0,
           f"④ 多选看板（{r4.get('nBoards')} 块）→ {r4.get('n')} 个板块全部默认折叠（open={r4.get('openN')}）")

        # ⑤ collapseAll/expandAll 记忆联动
        await ev("expandAll()")
        await asyncio.sleep(0.8)
        r5a = await ev("(function(){const gs=[...document.querySelectorAll('.week-group')];"
                       "return {openN:gs.filter(g=>g.classList.contains('open')).length, mem:COL_OPEN.size};})()")
        ok(r5a.get('openN') == r5a.get('mem') and r5a.get('openN', 0) > 0,
           f"⑤ expandAll → 全展开且记忆同步（open={r5a.get('openN')}，COL_OPEN={r5a.get('mem')}）")
        await ev("collapseAll()")
        await asyncio.sleep(0.5)
        r5b = await ev("(function(){const gs=[...document.querySelectorAll('.week-group')];"
                       "return {openN:gs.filter(g=>g.classList.contains('open')).length, mem:COL_OPEN.size};})()")
        ok(r5b.get('openN') == 0 and r5b.get('mem') == 0,
           f"⑤ collapseAll → 全折叠且记忆清空（open={r5b.get('openN')}，COL_OPEN={r5b.get('mem')}）")

        # ⑥ 无 JS 错误
        errs = await ev("window.__errs")
        ok(not errs, f"⑥ 无 JS 错误（实际：{errs}）")
    finally:
        kill_profile_chrome("cdp_t204y")
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
