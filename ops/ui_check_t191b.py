# -*- coding: utf-8 -*-
"""T-191b UI CDP 校验（人员管理四项修改）：
① 遗留账号（zhangsan/lisi/testerB/accB/accC）不再出现在人员表格；
② 「更多」菜单【人员管理】按钮只有一个人头 emoji 👤；
③ admin 行头像/照片为占位图（走系统默认图，无 /api/staff/img 直出地址）；
④ 头像/照片管理页签无「创建快照 / 快照与回滚」入口，仅保留「变更历史」。
"""
import asyncio, json, os, shutil, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9533
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []
LEGACY = ['zhangsan', 'lisi', 'testerB', 'accB', 'accC']


def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191b')
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

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev('document.cookie=%s;location.href="/";' % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【② 按钮图标：只有一个人头 👤】', flush=True)
    r2 = await ev("""(function(){
      const b=document.getElementById('staffBtn');
      return {text:b.textContent.trim(),glyphs:[...b.textContent.trim()][0]};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('glyphs') == '👤', '按钮首字符 = 单个人头 👤（%s）' % (r2 or {}).get('text'))
    ok(isinstance(r2, dict) and (r2.get('text') or '').startswith('👤 人员管理'),
       '按钮文案 =「👤 人员管理」（无第二 emoji）')

    print('【① 遗留账号不再出现 + 表格行数】', flush=True)
    await ev("openStaffModal()")
    for _ in range(20):
        await asyncio.sleep(0.4)
        if await ev("document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length>0") is True:
            break
    r1 = await ev("""(function(){
      const txt=document.getElementById('staffTableWrap').textContent;
      const legacy=%s;
      return {n:document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length,
        found:legacy.filter(u=>txt.indexOf('>'+u+'<')>=0||txt.indexOf(u)>=0)};})()"""
             % json.dumps(LEGACY))
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('n') == 72, '表格 72 行（删除 5 个遗留账号后，实际 %s）' % (r1 or {}).get('n'))
    ok(isinstance(r1, dict) and not r1.get('found'), 'zhangsan/lisi/testerB/accB/accC 均未出现')

    print('【③ admin 头像/照片走系统默认占位图】', flush=True)
    r3 = await ev("""(function(){
      const si=document.getElementById('staffSearch');si.value='admin';renderStaffTable();
      const row=document.querySelector('#staffTableWrap .staff-table tbody tr');
      const av=row.querySelector('img.staff-av');
      return {avImg:!!av,avDefault:!!(av&&av.src.indexOf('/static/default-photo.jpg')>=0),
        avDirect:!!(av&&av.src.indexOf('/api/staff/img/')>=0),
        photoPh:row.querySelectorAll('.staff-photo-ph').length};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('avImg') and r3.get('avDefault') and not r3.get('avDirect'),
       'admin 头像列 = 系统默认占位图（default-photo.jpg，非直出地址）')
    ok(isinstance(r3, dict) and (r3.get('photoPh') or 0) >= 1, 'admin 照片列 = —（未上传）')
    await ev("si=document.getElementById('staffSearch');si.value='';renderStaffTable();")

    print('【④ 头像/照片管理页签：无快照入口】', flush=True)
    r4 = await ev("""(function(){
      staffShowTab('media');
      const box=document.getElementById('staffViewMedia');
      return {snapBtn:!!box.querySelector('button[onclick*=staffMediaSnapshot]'),
        snapListBtn:!!box.querySelector('button[onclick*=staffMediaSnapList]'),
        histBtn:!!box.querySelector('button[onclick*=staffMediaHist]'),
        fns:{snap:typeof staffMediaSnapshot,snapList:typeof staffMediaSnapList,
             snapRestore:typeof staffMediaSnapRestore,hist:typeof staffMediaHist},
        cards:document.querySelectorAll('#staffMediaGrid .staff-media-card').length};})()""")
    print('  ', json.dumps(r4, ensure_ascii=True), flush=True)
    ok(isinstance(r4, dict) and not r4.get('snapBtn') and not r4.get('snapListBtn'),
       '「📸 创建快照」「🕘 快照与回滚」按钮已移除')
    ok(isinstance(r4, dict) and r4.get('histBtn'), '「🗒 变更历史」入口保留')
    ok(isinstance(r4, dict) and r4.get('fns', {}).get('snap') == 'undefined'
       and r4.get('fns', {}).get('snapList') == 'undefined'
       and r4.get('fns', {}).get('snapRestore') == 'undefined'
       and r4.get('fns', {}).get('hist') == 'function',
       '快照 JS 函数已移除、历史函数保留')
    ok(isinstance(r4, dict) and r4.get('cards', 0) == 72, '管理页签仍按账号出卡（72 张，功能保留）')
    await ev("closeModal('staffModal')")

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in PASS if not c]
    print('结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)
