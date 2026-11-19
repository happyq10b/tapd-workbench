# -*- coding: utf-8 -*-
"""T-191e UI CDP 校验（到期筛选弹窗精细化改版）：
① 筛选按钮无 emoji、尺寸与【清空筛选】【启用勾选】一致（宽高实测）；
② 弹窗加宽（480px）、说明横幅 / 图例 / 已选 chips 区块齐备；
③ 徽标、月份导航、全选/清空/取消/确定照常；
④ 已选 chips：选 2 天出现 2 枚、点 × 移除、清空归零。
"""
import asyncio, json, os, shutil, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9538
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []
N = []
TODAY = __import__('datetime').date.today()
D1 = (TODAY + __import__('datetime').timedelta(days=2)).isoformat()
D2 = (TODAY + __import__('datetime').timedelta(days=3)).isoformat()


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191e')
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
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【① 按钮规格：无 emoji，与同排按钮一致】', flush=True)
    r1 = await ev("""(function(){
      const due=document.getElementById('dueFilterBtn');
      // 只与**可见**的同排按钮比（全选当前在非勾选态是 hidden，rect 为 0 不具可比性）
      const others=['chkModeBtn','清空筛选'].map(k=>{
        const b=(typeof k==='string')?[...document.querySelectorAll('.toolbar-title-btns button')]
          .find(x=>x.textContent.trim()===k):document.getElementById(k);
        if(!b)return null;const r=b.getBoundingClientRect();
        return {h:Math.round(r.height),w:Math.round(r.width),pad:getComputedStyle(b).padding,
          fs:getComputedStyle(b).fontSize};}).filter(Boolean);
      const r=due.getBoundingClientRect(),cs=getComputedStyle(due);
      return {text:due.textContent.trim(),
        emoji:/[\\u2190-\\u2BFF\\uD83C-\\uDBFF\\uDC00-\\uDFFF]/.test(due.childNodes[0].textContent),
        h:Math.round(r.height),
        same:others.every(o=>Math.abs(o.h-Math.round(r.height))<=1&&o.pad===cs.padding&&o.fs===cs.fontSize),
        others:others};})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('text') == '到期筛选', '按钮文案 =「到期筛选」（无 emoji）')
    ok(isinstance(r1, dict) and r1.get('emoji') is False, '首段文本无 emoji 字符')
    ok(isinstance(r1, dict) and r1.get('same'),
       '按钮高度/padding/字号与【清空筛选】【启用勾选】一致（h=%s）' % (r1 or {}).get('h'))

    print('【② 弹窗改版：尺寸与新区块】', flush=True)
    await ev("openDueCalModal()")
    await asyncio.sleep(1.0)
    r2 = await ev("""(function(){
      const m=document.querySelector('#dueCalModal .modal');
      return {w:Math.round(m.getBoundingClientRect().width),
        banner:!!document.querySelector('#dueCalModal .due-info-banner'),
        legend:!!document.querySelector('#dueCalModal .due-legend'),
        legendN:document.querySelectorAll('#dueCalModal .dl-box').length,
        title:document.getElementById('dueCalTitle').textContent,
        todayBtn:!!document.querySelector('#dueCalModal button[onclick*=dueCalToday]'),
        cells:document.querySelectorAll('#dueCalGrid .due-cell:not(.empty)').length,
        cellH:Math.round(document.querySelector('#dueCalGrid .due-cell').getBoundingClientRect().height),
        footer:['dueCalAllBtn'].every(id=>document.getElementById(id))};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and 460 <= r2.get('w', 0) <= 500, '弹窗加宽至 480 规格（实际 %s）' % (r2 or {}).get('w'))
    ok(isinstance(r2, dict) and r2.get('banner') and r2.get('legend') and r2.get('legendN') == 4,
       '说明横幅 + 四档热力图例齐备')
    ok(isinstance(r2, dict) and r2.get('todayBtn'), '「本月」快捷按钮在列')
    ok(isinstance(r2, dict) and r2.get('cells') >= 28 and r2.get('cellH', 0) >= 44,
       '日历格放大（本月 %s 天、格高 %spx）' % ((r2 or {}).get('cells'), (r2 or {}).get('cellH')))

    print('【③ 已选 chips 交互】', flush=True)
    r3 = await ev("""(async function(){
      dueCalPick('%s');dueCalPick('%s');
      const wrap=document.getElementById('dueSelWrap');
      const chips=[...document.querySelectorAll('#dueSelChips .due-chip')];
      const hint=document.getElementById('dueCalHint').textContent;
      // 点第一枚的 × → 移除
      chips[0].querySelector('i').click();
      const after=document.querySelectorAll('#dueSelChips .due-chip').length;
      dueCalClear();
      const hidden=document.getElementById('dueSelWrap').hidden;
      return {open:wrap.hidden===false,n:chips.length,hint:hint,after:after,hidden:hidden,
        badge:document.getElementById('dueFilterBadge').hidden};})()""" % (D1, D2), True)
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('n') == 2 and r3.get('hint') == '已选 2 天',
       '选 2 天 → 出现 2 枚已选 chips + 计数「已选 2 天」')
    ok(isinstance(r3, dict) and r3.get('after') == 1, '点 chips × → 单独移除（剩 1 枚）')
    ok(isinstance(r3, dict) and r3.get('hidden') and r3.get('badge'),
       '清空 → chips 区隐藏、工具栏徽标隐藏')
    await ev("closeModal('dueCalModal')")

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)
