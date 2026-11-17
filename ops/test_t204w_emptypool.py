# -*- coding: utf-8 -*-
"""T-204w（2026-11-17 #140）空板块选人池严格口径 CDP 实测（用户报告场景）：
「收入工作事项/测试」板块负责人与参与人都为空，事项新增不应再选到看板层人员。
  ① cardPickPool('收入工作事项','测试') = []（板块已登记名单空 → 池空，不回退看板池）
  ② 对照组：同看板「收入组（第27周）」板块（owner=lmz, participants=wtt）
     → 池 = [李梦子, 吴婷婷]（板块名单 + 部门约束过滤后）
  ③ 无 JS 错误
只读验证（不开弹窗不提交、零写库）；D6：一次性 __cdp_ui 账号 + 树杀 + 强制下线。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9551
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BID = '1162069797001000243'          # 收入工作事项（真实看板，只读）
COL_EMPTY = '测试'                    # 用户报告：负责人与参与人都为空
COL_FULL = '收入组（第27周）'          # 对照组：owner=lmz, participants=wtt
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


async def main():
    import websockets
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204w')
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
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'") is True:
                break
        # 等 COLS_META / BC_ACL_MEMBERS 就绪（cardPickPool 依赖）
        for _ in range(30):
            await asyncio.sleep(1)
            if await ev("Array.isArray(window.COLS_META)&&window.COLS_META.length>0"
                        "&&typeof cardPickPool==='function'") is True:
                break
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")
        await asyncio.sleep(2)

        # ① 空板块 → 池空（不回退看板池）
        r1 = await ev("cardPickPool('%s','%s')" % (BID, COL_EMPTY), aw=True)
        ok(isinstance(r1, list) and r1 == [],
           f"① 空板块「{COL_EMPTY}」选人池 = []（实际：{r1}——不再回退看板池选到吴婷婷/李梦子）")

        # ② 对照组：有名单板块 → 池 = 板块名单（经部门约束/离岗过滤）
        r2 = await ev("cardPickPool('%s','%s')" % (BID, COL_FULL), aw=True)
        ok(isinstance(r2, list) and '李梦子' in (r2 or []) and '吴婷婷' in (r2 or []),
           f"② 对照板块「{COL_FULL}」池 = 板块名单（实际：{r2}）")

        # ③ 无 JS 错误
        errs = await ev("window.__errs")
        ok(not errs, f'③ 无 JS 错误（实际：{errs}）')
    finally:
        kill_profile_chrome("cdp_t204w")
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
