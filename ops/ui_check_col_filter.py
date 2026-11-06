#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#81 板块筛选栏改造 UI 实测（2026-11-06 用户需求）：

① 布局：搜索 → 🚦板块状态 → 🗓️归属年份 → 👤人员 → 📅周数 → 日期，同行不换行；
   四个下拉框等宽；搜索框宽度 ≥165px（提示词完整）
② 板块状态：面板 3 选项 + 全选/清空；勾选「进行中」→ COL_STATUS_SEL 生效 +
   请求发出（reload）；再勾「已完成」→ chips 两枚
③ 归属年份：面板含 全选/清空 + 年份列表；勾选 → curYears 生效 + years 参数随请求
④ 旧位置移除：【可选看板】带头不再有 .year-picker
⑤ 清空筛选：COL_STATUS_SEL 与 curYears 一并清空
⑥ 截图（状态面板展开 + 勾选后）
无夹具（生产数据只读）。
"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9398
BASE = 'http://127.0.0.1:8100'
U, PWD = 'admin', 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'col_filter.png')

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_s2%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1
                mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1760, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            # 先选中一个看板（真实路径：主列表页未选看板时空状态，renderBoard 不跑、
            # 年份选项不填充 —— 与旧 chips 行为一致；选板后才可测年份/状态过滤）
            r = await ev("(function(){const b=(ME.boards||[])[0];if(!b)return 'no board';"
                         "pickBoard(b.board_id);return b.board_name;})()")
            print('选中看板:', r)
            await asyncio.sleep(3)   # 等 renderBoard + 年份选项填充

            # ① 布局
            r = await ev("""(function(){
              const left=document.querySelector('.toolbar-left');
              const kids=[...left.children].map(x=>x.id||x.className.split(' ')[0]);
              const sr=left.getBoundingClientRect();
              const w4=['colStatusWrap','yearFilter','personFilterWrap','weekFilterWrap']
                .map(id=>{const el=document.getElementById(id);const b=el.getBoundingClientRect();
                          return {id,w:Math.round(b.width),top:Math.round(b.top)}});
              const sinp=document.getElementById('searchInput').getBoundingClientRect();
              return {kids:kids.join('|'),rowH:Math.round(sr.height),
                      widths:w4,searchW:Math.round(sinp.width),
                      ph:document.getElementById('searchInput').placeholder};
            })()""")
            print('布局探针:', json.dumps(r, ensure_ascii=False))
            ok('searchInput|colStatusWrap|yearFilter|personFilterWrap|weekFilterWrap|dateFilterBox' in r.get('kids', ''),
               '控件顺序 = 搜索→板块状态→归属年份→人员→周数→日期')
            ok(r.get('rowH', 999) <= 46, '筛选行单行不换行（toolbar-left 高 %s）' % r.get('rowH'))
            wlist = r.get('widths') or []
            ok(len(wlist) == 4 and max(x['w'] for x in wlist) - min(x['w'] for x in wlist) <= 2,
               '四个下拉框等宽（%s）' % [x['w'] for x in wlist])
            ok(all(x['top'] == wlist[0]['top'] for x in wlist), '四框同一行（top 一致）')
            ok(r.get('searchW', 0) >= 165, '搜索框 ≥165px，提示词完整（实际 %s）' % r.get('searchW'))

            # ② 板块状态面板
            await ev("toggleColStatusDrop({stopPropagation(){}});")
            r = await ev("""(function(){
              const d=document.getElementById('colStatusDrop');
              return {open:!d.hidden,opts:[...d.querySelectorAll('[data-pick-cs]')].map(x=>x.getAttribute('data-pick-cs')),
                      hasAll:!!d.querySelector('[data-cs-all]'),hasClear:!!d.querySelector('[data-cs-clear]')};
            })()""")
            ok(r.get('open') is True, '状态面板展开')
            ok(r.get('opts') == ['open', 'progressing', 'done'], '三个状态选项')
            ok(r.get('hasAll') and r.get('hasClear'), '含全选/清空')
            await ev("toggleColStatusPick('progressing');")
            await asyncio.sleep(1)
            r = await ev("(function(){return {sel:[...COL_STATUS_SEL],chips:document.getElementById('colStatusChips').children.length}})()")
            ok(r.get('sel') == ['progressing'] and r.get('chips') == 1, '勾选「进行中」生效（chips 1 枚）')
            await ev("toggleColStatusPick('done');")
            await asyncio.sleep(1)
            r = await ev("(function(){return {sel:[...COL_STATUS_SEL],cnt:document.getElementById('colStatusCount').textContent}})()")
            ok(r.get('sel') == ['progressing', 'done'] and '已选 2' in (r.get('cnt') or ''), '多选生效 + 计数')

            # ③ 归属年份面板
            await ev("toggleYearDrop({stopPropagation(){}});")
            r = await ev("""(function(){
              const d=document.getElementById('yearDrop');
              return {open:!d.hidden,opts:[...d.querySelectorAll('[data-pick-year]')].map(x=>x.getAttribute('data-pick-year')),
                      hasAll:!!d.querySelector('[data-year-all]'),hasClear:!!d.querySelector('[data-year-clear]')};
            })()""")
            ok(r.get('open') is True and r.get('opts'), '年份面板展开（选项 %s）' % r.get('opts'))
            ok(r.get('hasAll') and r.get('hasClear'), '含全选/清空')
            # 勾选一个年份 → reload 请求带 years 参数（拦截 fetch 断言）
            # ⚠️ curYears 默认已含当前年份 → 先清空再勾，避免 toggle 成「取消」
            await ev("""window.__cap=null;
              const of=window.fetch;window.__of=of;window.fetch=function(u,o){
                if(String(u).indexOf('/api/cards')>=0){window.__cap=String(u);}
                return of.apply(this,arguments);};
              curYears=new Set();toggleYearPick(_yearOptions[0]);0;""")
            await asyncio.sleep(1.5)
            r = await ev("(function(){if(!window.__cap)return null;const m=window.__cap.match(/years=([^&]+)/);return m?decodeURIComponent(m[1]):'(无 years 参数)';})()")
            ok(r and r != '(无 years 参数)', 'years 参数随请求下发（实际 %r）' % r)
            await ev("window.fetch=window.__of;")

            # ④ 旧位置移除
            r = await ev("(function(){return {old:!!document.querySelector('.year-picker'),"
                         "bandChips:!!document.querySelector('.tb-board-band .year-chip')}})()")
            ok(r.get('old') is False and r.get('bandChips') is False, '【可选看板】带头旧年份筛选已移除')

            # ⑤ 清空筛选
            await ev("clearAllRowFilters();")
            r = await ev("(function(){return {cs:COL_STATUS_SEL.size,y:curYears.size}})()")
            ok(r.get('cs') == 0 and r.get('y') == 0, '清空筛选 → 板块状态与归属年份一并清空')

            # ⑥ 截图：勾选状态 + 面板展开
            await ev("toggleColStatusPick('progressing');toggleYearDrop===0;")
            await ev("toggleColStatusDrop({stopPropagation(){}});")
            await asyncio.sleep(0.5)
            shot = await send('Page.captureScreenshot', {'format': 'png'})
            data = shot.get('data')
            if data:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, 'wb') as f:
                    f.write(base64.b64decode(data))
                print('截图已保存：%s' % OUT)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

asyncio.run(main())
