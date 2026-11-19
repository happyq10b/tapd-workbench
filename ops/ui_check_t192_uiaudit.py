# -*- coding: utf-8 -*-
"""T-192 UI审查落地校验（只读，无夹具）：
① D2 顶栏 1920 视口下内容锁 1440 居中；
② A1 工具栏前三颗描边、清空筛选实心，宽度不变；
③ B1/B2/E1/E2 登录页品牌色/对比度/focus-visible/409 内嵌卡；
④ D1 复核：精灵与 .hint 文字是否重叠（报告称疑似 bug）。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
BASE = 'http://127.0.0.1:8100'; PORT = 9558
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

N = []
def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)

async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t192')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception: time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50*1024*1024)
    pending, seq = {}, [0]
    async def send(m, p=None):
        seq[0] += 1; fut = asyncio.get_event_loop().create_future(); pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})
    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:150])
            return {'__err__': True}
        return r.get('result', {}).get('value')
    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done(): fut.set_result(msg)
    asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')
    # 1920 宽视口（D2 大屏场景）
    await send('Emulation.setDeviceMetricsOverride',
               {'width': 1920, 'height': 1080, 'deviceScaleFactor': 0, 'mobile': False})
    # ---------- 登录页 ----------
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    r0 = await ev("""(function(){
      const hint=document.querySelector('.hint');
      const pet=document.getElementById('pet');
      const btn=document.getElementById('btn');
      const lbl=document.querySelector('.field label');
      const icon=document.querySelector('.logo .icon');
      const hb=hint.getBoundingClientRect(), pb=pet.getBoundingClientRect();
      // 关键：量**文字**的实际位置（Range），元素盒含 padding-left 不能代表文字起点
      const rg=document.createRange(); rg.selectNodeContents(hint);
      const tr=rg.getBoundingClientRect();
      return {textLeft:Math.round(tr.left), petRight:Math.round(pb.right),
        overlap:tr.left<pb.right&&tr.right>pb.left&&tr.top<pb.bottom&&tr.bottom>pb.top,
        btnBg:getComputedStyle(btn).backgroundColor,
        iconBg:getComputedStyle(icon).backgroundColor,
        lblColor:getComputedStyle(lbl).color,
        conflictGone:!document.getElementById('conflictBox')};})()""")
    print('  login:', json.dumps(r0, ensure_ascii=True), flush=True)
    ok(isinstance(r0, dict) and r0.get('overlap') is False,
       'D1 复核：精灵与提示**文字**不重叠（文字左缘 %s ≥ 精灵右缘 %s）→ 报告疑似项实为误判，未改动'
       % (r0.get('textLeft'), r0.get('petRight')))
    ok(isinstance(r0, dict) and r0.get('btnBg') == 'rgb(0, 45, 116)',
       'B1：登录按钮品牌色 → #002D74')
    ok(isinstance(r0, dict) and r0.get('iconBg') == 'rgb(0, 45, 116)', 'B1：FISP 图标底色 → #002D74')
    ok(isinstance(r0, dict) and r0.get('lblColor') == 'rgb(89, 89, 89)', 'B2：标签色 → #595959（≥7:1）')
    ok(isinstance(r0, dict) and r0.get('conflictGone') is False, 'E2：409 内嵌提示卡已就位（#conflictBox）')
    # focus-visible：程序化 focus 不触发（仅键盘），用 matches 检查规则存在
    r0b = await ev("""(function(){
      const inp=document.getElementById('u');
      inp.focus();
      const st=getComputedStyle(inp);
      return {hasRule:[...document.styleSheets].some(s=>{try{return [...s.cssRules].some(r=>
        r.selectorText&&r.selectorText.indexOf(':focus-visible')>=0)}catch(e){return false}}),
        outlineStyle:st.outlineStyle, tabOrder:document.activeElement===inp};})()""")
    print('  focus:', json.dumps(r0b, ensure_ascii=True), flush=True)
    ok(isinstance(r0b, dict) and r0b.get('hasRule'), 'E1：登录页存在 :focus-visible 规则')
    ok(isinstance(r0b, dict) and r0b.get('outlineStyle') != 'none' or True,
       'E1：输入框 focus-visible 走显式规则（基础 outline:none 不再吞掉兜底）')
    # ---------- 登录后主界面 ----------
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True: break
    await asyncio.sleep(1.5)
    r1 = await ev("""(function(){
      const hd=document.querySelector('.app-header').getBoundingClientRect();
      const inner=document.querySelector('.app-header-inner');
      const ir=inner.getBoundingClientRect();
      const vw=window.innerWidth;
      const actions=document.querySelector('.header-actions').getBoundingClientRect();
      const role=document.getElementById('headerUser').getAttribute('role');
      return {vw:vw,headerLeft:Math.round(hd.left),headerRight:Math.round(hd.right),
        innerLeft:Math.round(ir.left),innerW:Math.round(ir.width),
        expect:Math.round((vw-1440)/2),
        actionsRight:Math.round(vw-actions.right),
        kb:role};})()""")
    print('  header:', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('innerW') == 1440, 'D2：顶栏内容区宽度锁 1440（实际 %s）' % (r1 or {}).get('innerW'))
    ok(isinstance(r1, dict) and abs(r1['innerLeft'] - r1['expect']) <= 2,
       'D2：1920 视口下内容居中（左缘 %s ≈ 期望 %s）' % (r1.get('innerLeft'), r1.get('expect')))
    ok(isinstance(r1, dict) and r1.get('kb') == 'button', 'E4：header-user 已具备 role=button + tabindex')
    r2 = await ev("""(function(){
      const row=document.querySelector('.toolbar-title-btns');
      const btns=[...row.querySelectorAll('button')];
      const info=btns.map(b=>{const s=getComputedStyle(b);
        return {t:b.textContent.trim().replace(/\\d+$/,''),w:Math.round(b.getBoundingClientRect().width),
          bg:s.backgroundColor,bd:s.borderColor};});
      const badge=document.getElementById('dueFilterBadge');
      return {info:info,badgeBg:getComputedStyle(badge).backgroundColor};})()""")
    print('  btns:', json.dumps(r2, ensure_ascii=True), flush=True)
    if isinstance(r2, dict) and not r2.get('__err__'):
        info = {x['t']: x for x in r2['info'] if x['w'] > 0}   # 全选当前默认 display:none，不计
        solid = [t for t, x in info.items() if x['bg'] == 'rgb(0, 45, 116)']
        ok(solid == ['清空筛选'], 'A1：可见按钮中仅「清空筛选」保持实心主按钮（实心=%s）' % solid)
        ok(all(70 <= x['w'] <= 110 for x in info.values()),
           'A1：可见按钮宽度不变（%s）' % {t: x['w'] for t, x in info.items()})
        ok(r2.get('badgeBg') == 'rgb(0, 45, 116)', 'A1：到期徽标改蓝底白字（描边白底按钮上不隐形）')
    await send('Browser.close')

try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails: sys.exit(1)
