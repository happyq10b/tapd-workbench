# -*- coding: utf-8 -*-
"""T-204x（2026-11-17 #141）架构选择多选 + 统计卡联动 CDP 实测：
  ① 选「财务中心」→ 统计卡仅统计财务中心自身挂载看板（综合工作事项（测试）1 块），
    不再是全局（整个财务中心树 8 块看板）汇总
  ② 多选「财务中心」+「核算部」→ curBoards = 并集（8 块看板），统计卡累加
  ③ 取消「财务中心」→ 只剩核算部 7 块
  ④ 取消全部 → 回到「请选择看板」空态、统计回全局（原行为）
  ⑤ 选中态样式 .sel + 展开态 .open 同步；无 JS 错误
只读验证（不开弹窗不写库）；D6：一次性 __cdp_ui 账号 + 树杀 + 强制下线。
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

        # ① 选「财务中心」：curBoards = 财务中心自身看板；统计卡 = 该看板口径
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        r1 = await ev("""(function(){
          return {n:curBoards.size, hasFin:curBoards.has('%s'),
                  sel:ARCH_SEL.has('财务中心'), open:!!DEPT_OPEN['财务中心'],
                  cls:(document.querySelector('.tree-dept.sel')||{}).textContent||'',
                  stat:(document.getElementById('progressOverview')||{}).textContent||''};
        })()""" % B_FIN)
        ok(r1.get('hasFin') is True and r1.get('n') == 1,
           f"① 选「财务中心」→ curBoards = 财务中心自身看板（{r1.get('n')} 块，含综合工作事项（测试））")
        ok(r1.get('sel') is True and r1.get('open') is True and '财务中心' in (r1.get('cls') or ''),
           '① 选中态：ARCH_SEL 命中 + .sel/.open 样式同步')
        fin_total = await ev("api('/api/overview?board_id=%s').then(function(d){return d.total})" % B_FIN, aw=True)
        ok(str(fin_total) in (r1.get('stat') or ''),
           f"① 统计卡总事项 = 财务中心看板口径（API total={fin_total}）")

        # ② 多选「核算部」→ 并集 8 块，统计累加
        await ev("toggleDept('核算部')")
        await asyncio.sleep(1.5)
        r2 = await ev("""(function(){
          return {n:curBoards.size, selN:ARCH_SEL.size,
                  stat:(document.getElementById('progressOverview')||{}).textContent||''};
        })()""")
        ok(r2.get('n') == 8 and r2.get('selN') == 2,
           f"② 多选财务中心+核算部 → curBoards 并集 {r2.get('n')} 块（ARCH_SEL={r2.get('selN')}）")
        comb_total = await ev("api('/api/overview?board_ids=%s,1162069797001000241,1162069797001000242,"
                              "1162069797001000243,1162069797001000245,1162069797001000246,"
                              "1162069797001000239,BCP1793717004248').then(function(d){return d.total})" % B_FIN, aw=True)
        ok(str(comb_total) in (r2.get('stat') or ''),
           f"② 统计卡 = 多架构累加（API 合计 total={comb_total}）")

        # ③ 取消「财务中心」→ 只剩核算部 7 块
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        r3 = await ev("""(function(){
          return {n:curBoards.size, selN:ARCH_SEL.size,
                  openFin:!!DEPT_OPEN['财务中心']};
        })()""")
        ok(r3.get('n') == 7 and r3.get('selN') == 1 and r3.get('openFin') is False,
           f"③ 取消财务中心 → 剩核算部 {r3.get('n')} 块（ARCH_SEL={r3.get('selN')}，展开态同步收起）")

        # ④ 取消全部 → 空态
        await ev("toggleDept('核算部')")
        await asyncio.sleep(1.5)
        r4 = await ev("""(function(){
          return {n:curBoards.size, selN:ARCH_SEL.size,
                  stat:(document.getElementById('progressOverview')||{}).textContent||''};
        })()""")
        ok(r4.get('n') == 0 and r4.get('selN') == 0,
           f"④ 取消全部架构 → curBoards 空（{r4.get('n')}），统计回全局口径（原行为）")

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
