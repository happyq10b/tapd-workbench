# -*- coding: utf-8 -*-
"""T-205b（2026-11-18 #146）：统计卡三级回退口径 CDP 实测

① 初始（无架构无看板）→ 统计 = /api/overview 全局（用户权限范围）
② 选「核算部」架构、未选看板 → 统计 = 该架构全部看板合计
③ 再选「财务中心」（多选）→ 统计 = 两架构看板并集合计
④ 点看板 tab → 统计 = 该看板口径
⑤ 取消该看板 → 回到架构口径（curBoards 空、ARCH_SEL 2 项）
⑥ 口径一致：done+progressing+open == total（同一响应）
⑦ 无 JS 错误
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9559
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
B_FIN = '1162069797001000238'    # 综合工作事项（测试）——财务中心自身挂载
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def stat_consistent(stat):
    """⑥ 四卡口径一致：done+progressing+open == total"""
    try:
        return int(stat['done']) + int(stat['progressing']) + int(stat['open']) == int(stat['total'])
    except Exception:
        return False


async def main():
    import websockets
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205b')
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

        # 页面内读取统计卡四值
        READ_STAT = """(function(){
          const box=document.getElementById('progressOverview');
          if(!box)return null;
          const g=function(label){
            const el=[].slice.call(box.querySelectorAll('.stat-card'))
              .find(function(c){return (c.querySelector('.stat-label')||{}).textContent===label});
            return el?el.querySelector('.stat-value').textContent.trim():null;
          };
          return {total:g('总事项'),done:g('已完成'),progressing:g('进行中'),open:g('未完成')};
        })()"""

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

        # ① 初始：无架构无看板 → 全局
        await asyncio.sleep(1)
        s0 = await ev(READ_STAT)
        api0 = await ev("api('/api/overview').then(function(d){return {t:d.total,d:d.done,p:d.progressing||0,o:d.open}})", aw=True)
        ok(s0 and api0 and str(api0['t']) == str(s0['total']),
           f"① 初始全局口径：卡片总事项={s0.get('total')} = API 全局 total={api0.get('t')}")
        ok(stat_consistent(s0), f"① 四卡口径一致：{s0.get('done')}+{s0.get('progressing')}+{s0.get('open')}={s0.get('total')}")

        # ② 选「核算部」架构、未选看板 → 架构全部看板合计
        await ev("toggleDept('核算部')")
        await asyncio.sleep(1.5)
        s1 = await ev(READ_STAT)
        api1 = await ev("(function(){const ids=[];ARCH_SEL.forEach(function(name){"
                        "(ME.boards||[]).forEach(function(b){if((b.dept||'__unassigned__')===name)ids.push(b.board_id);});});"
                        "return api('/api/overview?board_ids='+encodeURIComponent(ids.join(',')))"
                        ".then(function(d){return {n:ids.length,t:d.total}})})()", aw=True)
        ok(s1 and api1 and str(api1['t']) == str(s1['total']),
           f"② 架构口径（核算部 {api1.get('n')} 看板）：卡片={s1.get('total')} = API 合计={api1.get('t')}")

        # ③ 多选「财务中心」→ 并集合计
        await ev("toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        s2 = await ev(READ_STAT)
        api2 = await ev("(function(){const ids=[];ARCH_SEL.forEach(function(name){"
                        "(ME.boards||[]).forEach(function(b){if((b.dept||'__unassigned__')===name)ids.push(b.board_id);});});"
                        "return api('/api/overview?board_ids='+encodeURIComponent(ids.join(',')))"
                        ".then(function(d){return {n:ids.length,t:d.total}})})()", aw=True)
        ok(s2 and api2 and str(api2['t']) == str(s2['total']),
           f"③ 多架构并集（{api2.get('n')} 看板）：卡片={s2.get('total')} = API 合计={api2.get('t')}")

        # ④ 点看板 tab → 该看板口径
        await ev("pickBoard('%s')" % B_FIN)
        await asyncio.sleep(1.5)
        s3 = await ev(READ_STAT)
        api3 = await ev("api('/api/overview?board_id=%s').then(function(d){return d.total})" % B_FIN, aw=True)
        ok(s3 and str(api3) == str(s3['total']),
           f"④ 看板口径：卡片={s3.get('total')} = API 该看板 total={api3}")

        # ⑤ 取消该看板 → 回到架构口径（ARCH_SEL 2 项、curBoards 空）
        await ev("pickBoard('%s')" % B_FIN)
        await asyncio.sleep(1.5)
        s4 = await ev(READ_STAT)
        api4 = await ev("(function(){const ids=[];ARCH_SEL.forEach(function(name){"
                        "(ME.boards||[]).forEach(function(b){if((b.dept||'__unassigned__')===name)ids.push(b.board_id);});});"
                        "return api('/api/overview?board_ids='+encodeURIComponent(ids.join(',')))"
                        ".then(function(d){return {n:ids.length,t:d.total,selN:ARCH_SEL.size,curN:curBoards.size}})})()", aw=True)
        ok(s4 and api4 and str(api4['t']) == str(s4['total']) and api4.get('selN') == 2 and api4.get('curN') == 0,
           f"⑤ 取消看板 → 回架构口径（ARCH_SEL={api4.get('selN')},{api4.get('n')} 看板）：卡片={s4.get('total')} = API={api4.get('t')}")

        # ⑥ 全取消架构 → 全局
        await ev("toggleDept('核算部');toggleDept('财务中心')")
        await asyncio.sleep(1.5)
        s5 = await ev(READ_STAT)
        ok(s5 and api0 and str(api0['t']) == str(s5['total']) and stat_consistent(s5),
           f"⑥ 全取消 → 全局口径恢复（卡片={s5.get('total')} = 初始全局 {api0.get('t')}）")

        # ⑦ 无 JS 错误
        errs = await ev("window.__errs")
        ok(not errs, f"⑦ 无 JS 错误（实际：{errs}）")
    finally:
        kill_profile_chrome("cdp_t205b")
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
