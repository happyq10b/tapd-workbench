# -*- coding: utf-8 -*-
"""T-191f UI CDP 校验：架构管理「点击节点后绑定板块消失」修复。
复现原 bug 链路：点击节点行 → 认领编辑锁 → 服务端广播 edit_lock →
前端 ensureOrgTree(true) 强制刷新树 → 新树节点缺 wg_boards →
小组行「板块：xxx」消失 + 编辑面板勾选清空（保存即清空绑定）。
修复后：WS 刷新路径补 syncWgBoards()，两处断言必须保持。
"""
import asyncio, json, os, shutil, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9545
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191f')
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
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending, seq = {}, [0]

    async def send(m, p=None):
        seq[0] += 1
        fut = asyncio.get_event_loop().create_future()
        pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:200])
            return {'__err__': True}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)
    await ev("openWgModal()")
    await asyncio.sleep(2.0)

    # 基线：未点任何行前，小组行的板块文案与勾选正常
    r0 = await ev("""(function(){
      const row=[...document.querySelectorAll('#wgList .org-node-row')]
        .find(r=>r.textContent.indexOf('收入组')>=0);
      return {rowTxt:row.textContent.indexOf('板块：收入工作事项')>=0};})()""")
    ok(isinstance(r0, dict) and r0.get('rowTxt'), '基线：收入组行显示「板块：收入工作事项」')

    # 触发原 bug：点击核算部行 → 认锁 → WS 广播 → ensureOrgTree(true) 刷新
    await ev("""(function(){
      const row=[...document.querySelectorAll('#wgList .org-node-row')]
        .find(r=>r.textContent.indexOf('核算部')>=0);
      row.click();})()""")
    await asyncio.sleep(2.0)   # 等锁广播 + 树刷新 + 重绘
    r1 = await ev("""(function(){
      const row=[...document.querySelectorAll('#wgList .org-node-row')]
        .find(r=>r.textContent.indexOf('收入组')>=0);
      const shou=ORG_FLAT.find(x=>x.name==='收入组');
      return {rowTxt:row.textContent.indexOf('板块：收入工作事项')>=0,
        synced:typeof shou.wg_boards==='string'&&shou.wg_boards.indexOf('1162069797001000243')>=0,
        refreshed:(document.querySelectorAll('#wgList .org-node-row').length>0)};})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('refreshed'), '点击核算部后树已重绘（刷新链路真实触发）')
    ok(isinstance(r1, dict) and r1.get('synced'),
       'WS 刷新后 ORG_TREE 的 wg_boards 已重同步（收入组=1162069797001000243）')
    ok(isinstance(r1, dict) and r1.get('rowTxt'), '刷新后收入组行仍显示「板块：收入工作事项」（原 bug：消失）')

    # 点击收入组行 → 编辑面板勾选必须包含已绑定看板
    r2 = await ev("""(async function(){
      const row=[...document.querySelectorAll('#wgList .org-node-row')]
        .find(r=>r.textContent.indexOf('收入组')>=0);
      row.click();
      await new Promise(r=>setTimeout(r,400));
      const sel=[...document.querySelectorAll('.g_brd_chk:checked')].map(c=>{
        const lbl=c.closest('label');return lbl?lbl.textContent.trim():'';});
      return {sel:sel};})()""", True)
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and any('收入工作事项' in s for s in (r2.get('sel') or [])),
       '点击收入组行 → 编辑面板勾选含已绑定的「收入工作事项」（原 bug：全空）')

    # 清理：释放本测试认领的节点锁（点核算部时 acquire 的 org:<id>），避免残锁
    await ev("""(async function(){
      if(typeof releaseEditLock==='function'&&ORG_LOCK_KEY){releaseEditLock(ORG_LOCK_KEY);ORG_LOCK_KEY='';}
      return 'ok';})()""", True)

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)
