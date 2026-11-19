# -*- coding: utf-8 -*-
"""T-191d UI CDP 校验：人员管理入口显隐与范围提示（真实账号）。
① admin：入口可见、范围提示「范围：全部部门」；
② wwn（核算部部长=部门负责人）：入口可见、范围提示「范围：本部门及下属」、
   列表行数 < 全量（服务端范围过滤生效）；
③ 普通成员（编辑角色、无部门负责人岗位）：入口不可见。
夹具零改动（仅真实账号只读验证）。"""
import asyncio, json, os, shutil, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9537
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


async def login_and(page_ws, token, expect_user):
    send, ev, reader = page_ws
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % token))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username===%s" % json.dumps(expect_user)) is True:
            break
    await asyncio.sleep(1.2)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191d')
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
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)}
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
    page = (send, ev, None)

    # ① admin
    await login_and(page, make_token('admin'), 'admin')
    r1 = await ev("""(function(){
      const b=document.getElementById('staffBtn');
      return {visible:!!b&&getComputedStyle(b).display!=='none',
        hint:(ME.can_manage_staff===true&&ME.staff_scope_all===true)?'ok':'bad'};})()""")
    print('  admin:', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('visible') and r1.get('hint') == 'ok',
       'admin：入口可见、能力位 can_manage_staff/staff_scope_all 正确')
    await ev("openStaffModal()")
    await asyncio.sleep(1.0)
    r1b = await ev("""(function(){
      return {hint:document.getElementById('staffScopeHint').textContent,
        n:document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length};})()""")
    print('  admin modal:', json.dumps(r1b, ensure_ascii=True), flush=True)
    ok(isinstance(r1b, dict) and r1b.get('hint') == '范围：全部部门', 'admin：范围提示「全部部门」')
    await ev("closeModal('staffModal')")

    # ② wwn（核算部部长）
    await login_and(page, make_token('wwn'), 'wwn')
    r2 = await ev("""(function(){
      const b=document.getElementById('staffBtn');
      return {visible:!!b&&getComputedStyle(b).display!=='none',
        cap:ME.can_manage_staff, all:ME.staff_scope_all};})()""")
    print('  wwn:', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('visible') and r2.get('cap') is True and r2.get('all') is False,
       '部门负责人（wwn）：入口可见、scope=dept')
    await ev("openStaffModal()")
    for _ in range(15):
        await asyncio.sleep(0.4)
        if await ev("document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length>0") is True:
            break
    r2b = await ev("""(function(){
      return {hint:document.getElementById('staffScopeHint').textContent,
        n:document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length};})()""")
    print('  wwn modal:', json.dumps(r2b, ensure_ascii=True), flush=True)
    ok(isinstance(r2b, dict) and r2b.get('hint') == '范围：本部门及下属', '部门负责人：范围提示「本部门及下属」')
    ok(isinstance(r2b, dict) and 0 < r2b.get('n', 0) < 72,
       '部门负责人：列表为本部门范围（%s 行 < 全量 72）' % (r2b or {}).get('n'))
    await ev("closeModal('staffModal')")

    # ③ 普通成员（找一个无负责人岗位的账号：zwt/zym 等 editor；选 zwt）
    await login_and(page, make_token('zwt'), 'zwt')
    r3 = await ev("""(function(){
      const b=document.getElementById('staffBtn');
      return {hidden:!b||getComputedStyle(b).display==='none', cap:ME.can_manage_staff};})()""")
    print('  zwt:', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('hidden') and r3.get('cap') is False,
       '普通成员：入口隐藏（can_manage_staff=False）')

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)
