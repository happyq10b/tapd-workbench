#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#81 板块筛选栏改造 UI 实测（2026-11-06 用户需求）：

① 布局：搜索 → 🚦板块状态 → 🗓️归属年份 → 👤人员 → 📅周数 → 日期，同行不换行；
   四个下拉框等宽；搜索框宽度 ≥186px（🔍 占位完整）
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
                      };
            })()""")
            print('布局探针:', json.dumps(r, ensure_ascii=False))
            ok('searchInput|colStatusWrap|personFilterWrap|yearFilter|weekFilterWrap|dateFilterBox' in r.get('kids', ''),
               '控件顺序 = 搜索→状态→人员→年份→周数→日期（#84 人员/年份对调）')
            ok(r.get('rowH', 999) <= 46, '筛选行单行不换行（toolbar-left 高 %s）' % r.get('rowH'))
            wlist = r.get('widths') or []
            ok(len(wlist) == 4 and max(x['w'] for x in wlist) - min(x['w'] for x in wlist) <= 2,
               '四个下拉框等宽（%s）' % [x['w'] for x in wlist])
            ok(all(x['top'] == wlist[0]['top'] for x in wlist), '四框同一行（top 一致）')
            ok(r.get('searchW', 0) >= 186, '搜索框 ≥186px（🔍 占位完整，实际 %s）' % r.get('searchW'))
            # #83：占位提示移除 + 标签改两字
            r = await ev("""(function(){
              return {stPh:document.getElementById('colStatusInput').placeholder,
                      yrPh:document.getElementById('yearFilterInput').placeholder,
                      searchPh:document.getElementById('searchInput').placeholder,
                      labels:[...document.querySelectorAll('.toolbar-left .cf-label')].map(x=>x.textContent.trim())};
            })()""")
            ok(r.get('stPh') == '' and r.get('yrPh') == '', '状态/年份输入框无占位提示')
            ok(r.get('labels') == ['🚦 状态', '👤 人员', '🗓️ 年份', '📅 周数'],
               '标签两字、顺序 = 状态/人员/年份/周数（实际 %s）' % r.get('labels'))
            ok((r.get('searchPh') or '').find(chr(0x1F50D))>=0, '搜索栏占位带 🔍 emoji（实际 %s）' % r.get('searchPh'))
            # #83：清空筛选/操作 恒定贴行右端，且右缘与日期框对齐（margin-left:auto，
            #      不依赖明细有无）；max-width 放开后两行右缘恒对齐
            await ev("document.getElementById('filterHint').textContent='人员：测试 | 周数：2026 · 第41周';")
            r = await ev("""(function(){
              function R(sel){const b=document.querySelector(sel).getBoundingClientRect();return Math.round(b.right);}
              return {withTextDiff:R('#toolbarOpsBtn')-R('#dateFilterBox'),opsTop:Math.round(document.getElementById('toolbarOpsBtn').getBoundingClientRect().top)};
            })()""")
            await ev("document.getElementById('filterHint').textContent='';")
            r2 = await ev("""(function(){
              function R(sel){const b=document.querySelector(sel).getBoundingClientRect();return Math.round(b.right);}
              return {emptyDiff:R('#toolbarOpsBtn')-R('#dateFilterBox'),
                      opsRight:R('#toolbarOpsBtn'),opsTop:Math.round(document.getElementById('toolbarOpsBtn').getBoundingClientRect().top),
                      rowTop:Math.round(document.getElementById('filterHint').parentElement.getBoundingClientRect().top)};
            })()""")
            ok(abs(r.get('withTextDiff', 999)) <= 2, '有明细时操作按钮右缘 = 日期框右缘（差 %s）' % r.get('withTextDiff'))
            ok(abs(r2.get('emptyDiff', 999)) <= 2, '明细为空时按钮仍贴右缘 = 日期框右缘（差 %s）' % r2.get('emptyDiff'))
            ok(abs(r2.get('opsTop', 0) - r2.get('rowTop', 0)) <= 6, '按钮与明细行同一行（top 差 %s）' % abs(r2.get('opsTop', 0) - r2.get('rowTop', 0)))

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

            # ⑤b #84：提示文案
            await ev("openFilterCombo('week');")
            await asyncio.sleep(0.5)
            r = await ev("(function(){return document.getElementById('weekFilterDrop').textContent.indexOf('可直接输入「2026-41」回车')>=0 && document.getElementById('weekFilterDrop').textContent.indexOf('点击勾选')<0;})()")
            ok(r is True, '周数提示改为「可直接输入「2026-41」回车」')
            await ev("toggleColStatusDrop({stopPropagation(){}});")
            r = await ev("(function(){return document.getElementById('colStatusDrop').textContent.indexOf('板块完成情况')>=0;})()")
            ok(r is True, '状态提示改为「板块完成情况」')
            await ev("closeColStatusDrop();closeFilterCombo();")

            # ⑤c #84：年份手动输入（「2027」非当前看板候选 → _manualYear 保护）
            await ev("toggleYearDrop({stopPropagation(){}});")
            await ev("var yi=document.getElementById('yearFilterInput');yi.value='2027';onYearKey({key:'Enter',preventDefault(){},stopPropagation(){}});")
            await asyncio.sleep(1)
            r = await ev("(function(){return {sel:[...curYears],manual:_manualYear.has('2027'),chip:document.getElementById('yearFilterChips').textContent.indexOf('2027')>=0}})()")
            ok(r.get('sel') == ['2027'] and r.get('manual') is True, '手动输入 2027 回车 → 加入已选（手工年份保护）')
            ok(r.get('chip') is True, 'chip 渲染 2027')
            # 非法输入被拒
            await ev("var yi=document.getElementById('yearFilterInput');yi.value='abc';onYearKey({key:'Enter',preventDefault(){},stopPropagation(){}});")
            r = await ev("(function(){return {sel:[...curYears],toast:document.getElementById('toast').textContent}})()")
            ok(r.get('sel') == ['2027'] and '年份格式' in (r.get('toast') or ''), '非法年份输入被拦截并提示')

            # ⑤d #84：筛选明细包含状态与年份
            await ev("toggleColStatusPick('progressing');")
            await asyncio.sleep(1)
            await ev("syncFilterHint();")
            r = await ev("document.getElementById('filterHint').textContent")
            ok('状态：进行中' in r and '年份：2027 年' in r,
               '筛选明细含状态与年份（实际 %r）' % r)

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

            # ⑦ #83：1200 视口下整栏不溢出（无横向滚动、无换行）
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1200, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(1)
            r = await ev("""(function(){
              const tb=document.querySelector('.toolbar');
              const left=document.querySelector('.toolbar-left');
              const kids=[...left.children].map(x=>{const b=x.getBoundingClientRect();return b.top+b.height/2;});
              const tmin=Math.min.apply(null,kids);
              // emoji 让各控件盒高差 1~2px（flex 居中）→ 用垂直中心 + 4px 容差判「同一行」
              //（真折行的中心差 ≥ 一个行高 ~35px，4px 容差可干净区分）
              return {docOverflow:document.documentElement.scrollWidth>1200,
                      tbScroll:tb.scrollWidth-tb.clientWidth,
                      rowTopSet:[...new Set(kids.map(t=>Math.round((t-tmin)/4)))].length};
            })()""")
            ok(r.get('docOverflow') is False, '1200 视口无横向溢出（docOverflow=%s）' % r.get('docOverflow'))
            ok(r.get('tbScroll', 1) <= 1, '工具栏内部无横向溢出（%spx）' % r.get('tbScroll'))
            ok(r.get('rowTopSet') == 1, '筛选控件单行不折行（top 集合 %s）' % r.get('rowTopSet'))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

asyncio.run(main())
