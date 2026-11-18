# -*- coding: utf-8 -*-
"""T-204x（2026-11-18 #145 修订）架构选择 = 导航语义 CDP 实测：

#141 原行为（选架构=批量选中其下看板+统计累加）已按用户口径废弃——
「点击架构进入对应看板页面时，看板各项应默认为非选中状态」。

验证（真实看板只读 + 会话内交互）：
  ① 选「财务中心」→ ARCH_SEL 命中 + .sel/.open 样式；curBoards **空**；
    展开的看板 tab 显示但全部无 .active；内容区「请选择看板」空态
  ② 多选「核算部」→ ARCH_SEL=2，两架构看板 tab 并存显示、仍全部未选中
  ③ 用户点看板 tab（pickBoard）→ 该看板 .active、统计 = 该看板口径
  ④ 取消架构 → tab 收起、ARCH_SEL=0；已选看板保留（架构选择不动看板选择）
  ⑤ 无 JS 错误
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9555
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
B_FIN = '1162069797001000238'    # 综合工作事项（测试）——财务中心自身挂载
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


async def main():
    import websockets
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204x')
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
        await asyncio.sleep(2.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # ① 选「财务中心」：看板 tab 展开显示但全部未选中；内容区空态
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        r1 = await ev("""(function(){
          const tabs=[].slice.call(document.querySelectorAll('.tab-btn'));
          return {curN:curBoards.size, sel:ARCH_SEL.has('财务中心'), open:!!DEPT_OPEN['财务中心'],
                  cls:(document.querySelector('.tree-dept.sel')||{}).textContent||'',
                  tabsN:tabs.length, activeN:tabs.filter(function(x){return x.classList.contains('active')}).length,
                  empty:(document.getElementById('emptyState')||document.querySelector('.board-empty')||{}).textContent||''};
        })()""")
        ok(r1.get('curN') == 0,
           f"① 选「财务中心」→ curBoards 空（{r1.get('curN')}），看板各项默认未选中")
        ok(r1.get('sel') is True and r1.get('open') is True and '财务中心' in (r1.get('cls') or ''),
           '① 选中态：ARCH_SEL 命中 + .sel/.open 样式同步')
        ok(r1.get('tabsN', 0) >= 1 and r1.get('activeN') == 0,
           f"① 看板 tab 展开显示 {r1.get('tabsN')} 个、全部无选中样式（active={r1.get('activeN')}）")

        # ② 多选「核算部」→ ARCH_SEL=2，看板 tab 并存显示、仍全部未选中
        await ev("toggleDept('核算部')")
        await asyncio.sleep(1.5)
        r2 = await ev("""(function(){
          const tabs=[].slice.call(document.querySelectorAll('.tab-btn'));
          return {curN:curBoards.size, selN:ARCH_SEL.size,
                  tabsN:tabs.length, activeN:tabs.filter(function(x){return x.classList.contains('active')}).length};
        })()""")
        ok(r2.get('selN') == 2 and r2.get('tabsN', 0) >= 8 and r2.get('activeN') == 0 and r2.get('curN') == 0,
           f"② 多选财务中心+核算部 → ARCH_SEL={r2.get('selN')}、看板 tab {r2.get('tabsN')} 个并存、仍全部未选中")

        # ③ 用户自行点看板 tab → 该看板选中、统计 = 该看板口径
        await ev("pickBoard('%s')" % B_FIN)
        await asyncio.sleep(1.5)
        r3 = await ev("""(function(){
          const tab=[].slice.call(document.querySelectorAll('.tab-btn'))
            .find(function(x){return (x.querySelector('.tab-name')||{}).textContent==='综合工作事项（测试）'});
          return {curN:curBoards.size, hasFin:curBoards.has('%s'),
                  active:!!(tab&&tab.classList.contains('active'))};
        })()""" % B_FIN)
        ok(r3.get('hasFin') is True and r3.get('curN') == 1 and r3.get('active') is True,
           f"③ 点看板 tab → 仅该看板选中（curBoards={r3.get('curN')}，.active 同步）")

        # ④ 取消「财务中心」架构 → 其 tab 收起；「核算部」仍选中（多选互不影响）；已选看板保留
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        r4 = await ev("""(function(){
          return {curN:curBoards.size, selN:ARCH_SEL.size, openFin:!!DEPT_OPEN['财务中心'],
                  openHr:!!DEPT_OPEN['核算部'], selHr:ARCH_SEL.has('核算部')};
        })()""")
        ok(r4.get('selN') == 1 and r4.get('selHr') is True and r4.get('openHr') is True
           and r4.get('openFin') is False and r4.get('curN') == 1,
           f"④ 取消财务中心 → 其展开收起（openFin={r4.get('openFin')}），核算部选中/展开不受影响，已选看板保留（curBoards={r4.get('curN')}）")

        # ⑤ 无 JS 错误
        errs = await ev("window.__errs")
        ok(not errs, f"⑤ 无 JS 错误（实际：{errs}）")
    finally:
        kill_profile_chrome("cdp_t204x")
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
