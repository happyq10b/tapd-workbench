# -*- coding: utf-8 -*-
"""T-205a（2026-11-17 #144）：进入系统架构默认无选中/展开项

用户报告：进入系统后「财务中心」呈展开态样式（▼+蓝底）但未选中——
根因 = 三条恢复/自动展开链路（localStorage、user_prefs.dept_open、
ensureInitialSelection 自动展开第一个有看板的部门）。

验证（真实看板「财务中心/综合工作事项（测试）」只读验证 + 会话内交互）：
① 预置 localStorage tapd.deptOpen={"财务中心":true} → 登录后所有架构节点无 open/sel
② DEPT_OPEN / ARCH_SEL 均为空
③ 看板带为空态（无任何看板 tab 显示）
④ 点「财务中心」→ 展开 + .sel；再点 → 收起取消（会话内行为不变）
⑤ 点看板 tab → 其所属部门自动展开（ensureDeptOpen 保留）
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
from app.app import make_token  # noqa: E402

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9557
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


async def main():
    import websockets
    tk = make_token('admin')

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205a')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      f'--remote-debugging-port={PORT}', '--user-data-dir=' + profile,
                      'about:blank'],
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

        async def send(method, params=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': method, 'params': params or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(expr, aw=False):
            r = await send('Runtime.evaluate',
                           {'expression': expr, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}),
                                                ensure_ascii=False)}
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        # 先预置旧持久化数据（模拟历史用户的 localStorage 残留），再注入 token 刷新
        await ev("localStorage.setItem('tapd.deptOpen', JSON.stringify({'财务中心': true}));"
                 "document.cookie=%s;location.href='/';" %
                 json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        for _ in range(30):
            await asyncio.sleep(1)
            if await ev("Array.isArray((window.ROW_OPS||{}).toolbarOps)") is True:
                break
        await asyncio.sleep(1)

        # ①② 全部架构节点无 open/sel；DEPT_OPEN/ARCH_SEL 空
        st = await ev('''(function(){
          const ds=[].slice.call(document.querySelectorAll('.tree-dept'));
          return {n:ds.length,
                  openN:ds.filter(function(x){return x.classList.contains('open')}).length,
                  selN:ds.filter(function(x){return x.classList.contains('sel')}).length,
                  deptOpen:Object.keys(DEPT_OPEN).length,
                  archSel:ARCH_SEL.size,
                  ls:localStorage.getItem('tapd.deptOpen')};
        })()''')
        ok(st and st.get('n', 0) > 0 and st.get('openN') == 0 and st.get('selN') == 0,
           f'① 预置旧 localStorage 后登录：{st.get("n")} 个架构节点全部无 open/sel（open={st.get("openN")}, sel={st.get("selN")}）')
        ok(st and st.get('deptOpen') == 0 and st.get('archSel') == 0,
           f'② DEPT_OPEN={st.get("deptOpen")} 项、ARCH_SEL={st.get("archSel")} 项（均空）')

        # ③ 看板带无 tab（空态）
        bt = await ev('''(function(){
          const tabs=[].slice.call(document.querySelectorAll('#boardTabs .tab-btn, [id^=tab_]'));
          return {tabs:tabs.length};
        })()''')
        ok(bt is not None and bt.get('tabs', 1) == 0, f'③ 看板带无任何看板 tab（{bt}）')

        # ④ 点「财务中心」→ 展开+选中；再点 → 收起取消
        #   （.cur 是部门页导航标记，不是选中态；选中态=.sel，按 ARCH_SEL 断言）
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(0.5)
        s1 = await ev('''(function(){
          const el=[].slice.call(document.querySelectorAll('.tree-dept'))
            .find(function(x){return x.textContent.indexOf('财务中心')>=0});
          return {open:!!(el&&el.classList.contains('open')),
                  sel:!!(el&&el.classList.contains('sel')),
                  selN:ARCH_SEL.size};
        })()''')
        ok(s1 and s1.get('open') and s1.get('sel') and s1.get('selN') == 1,
           f'④a 点「财务中心」→ 展开+选中（{s1}）')
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(0.5)
        s2 = await ev('''(function(){
          const ds=[].slice.call(document.querySelectorAll('.tree-dept'));
          return {openN:ds.filter(function(x){return x.classList.contains('open')}).length,
                  selN:ds.filter(function(x){return x.classList.contains('sel')}).length};
        })()''')
        ok(s2 and s2.get('openN') == 0 and s2.get('selN') == 0, f'④b 再点 → 收起+取消选中（{s2}）')

        # ⑤ 选看板 → 所属部门自动展开（ensureDeptOpen 保留）
        #   看板 1162069797001000238 = 「综合工作事项（测试）」，挂「财务中心」
        await ev("pickBoard('1162069797001000238')")
        await asyncio.sleep(1)
        s3 = await ev('''(function(){
          const el=[].slice.call(document.querySelectorAll('.tree-dept'))
            .find(function(x){return x.textContent.indexOf('财务中心')>=0});
          return {deptOpen:!!DEPT_OPEN['财务中心'],
                  open:!!(el&&el.classList.contains('open')),
                  boardSel:curBoards.has('1162069797001000238')};
        })()''')
        ok(s3 and s3.get('deptOpen') and s3.get('open') and s3.get('boardSel'),
           f'⑤ 选看板 → 所属部门自动展开（{s3}）')
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        kill_profile_chrome('cdp_t205a')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
