# -*- coding: utf-8 -*-
"""T-205u：排序选项 / 架构取消联动 / 进度条压缩对齐 / 架构徽标位置 CDP 实测（2026-11-18）
① 事项排序下拉：个人置顶优先（默认）/开始时间/截止时间/创建时间，按账号记忆；
③ 取消架构选择 → 该架构下已选看板联动取消、板块 tab 不再显示；
④ 板块进度条：前缀 n/N 移入格内、整体宽度=204px 周数列宽、文案去「完成」；
⑤ 架构节点看板数徽标移到「主页」左侧、形态与看板行徽标一致。
API 夹具（__t205u_ 前缀）测完即删。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'
TK = make_token('admin')
_n = {'ok': 0, 'fail': 0}
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    _n['ok' if cond else 'fail'] += 1

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TK)
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    import websockets
    # ── 夹具：排序板块 + 3 张卡（due/begin 各异，第 3 张无日期）；进度条板块 + 1 完成 1 未完成 ──
    col_key = None; prog_key = None; card_ids = []
    st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205u_排序板块',
                                        'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
    if st in (200, 201): col_key = d.get('col_key')
    cards = [
        {'name': '__t205u_卡A', 'begin': '2026-11-01', 'due': '2026-12-20'},
        {'name': '__t205u_卡B', 'begin': '2026-11-05', 'due': '2026-12-10'},
        {'name': '__t205u_卡C', 'begin': '', 'due': ''},
    ]
    for c in cards:
        stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': c['name'],
                                            'fields': {'column_name': '__t205u_排序板块',
                                                       'begin': c['begin'], 'due': c['due']}})
        if stc in (200, 201): card_ids.append(dc.get('card_id'))
        time.sleep(1.1)   # created 秒级精度 → 间隔 1s 保证「创建时间降序」断言确定性
    stp, dp = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205u_进度板块',
                                          'nature': '日常', 'year': '2026', 'created_at': '2026-11-17'})
    if stp in (200, 201): prog_key = dp.get('col_key')
    api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205u_进度未完成',
                              'fields': {'column_name': '__t205u_进度板块'}})
    stx, dx = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205u_进度已完成',
                                        'fields': {'column_name': '__t205u_进度板块', 'status': 'done',
                                                   'status_name': '已完成', 'completed': '2026-11-18'}})
    print('fixture:', st, stp, len(card_ids), flush=True)

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205u')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                      '--remote-debugging-port=9641', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9641/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9641/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        seq = [0]
        async def send(mm, p=None):
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        await ev("expandAll()")
        await asyncio.sleep(2)

        async def fixture_order():
            return await ev("""(function(){
              const hs=[].slice.call(document.querySelectorAll('.week-header'))
                .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205u_排序板块')>=0;});
              if(!hs.length)return {err:'板块不可见'};
              const body=hs[0].parentElement.querySelector('.week-body');
              return {order:[].slice.call(body.querySelectorAll('.item-title')).map(function(x){return x.textContent;})};
            })()""")

        # ── ① 排序选项 ──
        r1 = await ev("""(function(){
          const sel=document.getElementById('cardSortSel');
          return {exists:!!sel, n:sel?sel.options.length:0,
                  opts:sel?[].slice.call(sel.options).map(function(o){return o.value;}):[],
                  val:sel?sel.value:''};
        })()""")
        ok(r1 and r1.get('exists') and (r1.get('opts') or []) == ['created', 'begin', 'due'] and r1.get('val') == 'created',
           "① 排序下拉三档（置顶为公共首级不再是选项），默认「创建时间」（%s）" % (r1 or {}).get('opts'))
        # 创建时间降序（默认创建顺序 A→B→C）
        await ev("setCardSort('created')")
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or []) == ['__t205u_卡C', '__t205u_卡B', '__t205u_卡A'],
           "① 创建时间降序：新的在前（%s）" % (o or {}).get('order'))
        # 截止时间升序：12-10 → 12-20 → 无截止最后
        await ev("setCardSort('due')")
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or []) == ['__t205u_卡B', '__t205u_卡A', '__t205u_卡C'],
           "① 截止时间升序：最近到期在前、无截止排最后（%s）" % (o or {}).get('order'))
        # 开始时间升序：11-01 → 11-05 → 无开始最后
        await ev("setCardSort('begin')")
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or []) == ['__t205u_卡A', '__t205u_卡B', '__t205u_卡C'],
           "① 开始时间升序：早的在前、无开始排最后（%s）" % (o or {}).get('order'))
        # 持久化：模拟重进（重新 loadCardSort）
        rp = await ev("(function(){loadCardSort();return {v:document.getElementById('cardSortSel').value,ls:localStorage.getItem('tapd.cardSort_'+ME.username)};})()")
        ok(rp and rp.get('v') == 'begin' and rp.get('ls') == 'begin',
           "① 排序选项按账号持久化（localStorage=%s，回显=%s）" % ((rp or {}).get('ls'), (rp or {}).get('v')))
        await ev("setCardSort('created')")
        await asyncio.sleep(1.5)

        # ── ④ 进度条压缩对齐 + 文案 ──
        r4 = await ev("""(function(){
          const hs=[].slice.call(document.querySelectorAll('.week-header'))
            .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205u_进度板块')>=0;});
          if(!hs.length)return {err:'进度板块不可见'};
          const bar=hs[0].querySelector('.fcol-bar');
          const cnt=bar.querySelector('.bar-count');
          const wb=bar.querySelector('.week-bar');
          const meta=hs[0].querySelector('.week-meta');
          return {cntText:cnt?cnt.textContent.trim():'',
                  barW:Math.round(bar.getBoundingClientRect().width),
                  cntW:Math.round(cnt.getBoundingClientRect().width),
                  wbW:Math.round(wb.getBoundingClientRect().width),
                  metaGone:!meta,
                  tip:bar.getAttribute('title')||''};
        })()""")
        ok(r4 and not r4.get('err') and (r4.get('cntText') or '') == '1/2',
           "④ 前缀移入进度条格且无「完成」二字（实际 %r）" % (r4 or {}).get('cntText'))
        ok(r4 and (r4.get('metaGone') is True),
           "④ 原 week-meta 独立前缀 span 已移除")
        ok(r4 and abs((r4.get('barW') or 0) - 204) <= 2,
           "④ 进度条组合整体宽度 = 周数列宽 204px（实际 %spx）" % (r4 or {}).get('barW'))
        ok(r4 and (r4.get('wbW') or 0) + (r4.get('cntW') or 0) + 6 <= (r4.get('barW') or 0) + 2,
           "④ 进度条被压缩：bar %spx + 前缀 %spx + 间距 = 组合宽（前缀外全部让给条）" % ((r4 or {}).get('wbW'), (r4.get('cntW') or 0) if r4 else None))
        ok(r4 and '完成' not in ((r4.get('tip') or '').split('：')[-1] or '') and '自动统计' in (r4.get('tip') or ''),
           "④ 悬停提示其余文案不变（%r）" % (r4 or {}).get('tip'))

        # ── ⑤ 架构徽标位置（先展开核算部，让看板行徽标可见作形态对照）──
        await ev("if(!DEPT_OPEN['核算部'])toggleDept('核算部')")
        await asyncio.sleep(1.5)
        r5 = await ev("""(function(){
          const node=[].slice.call(document.querySelectorAll('.tree-dept'))
            .find(function(x){return x.offsetParent!==null && x.textContent.indexOf('财务中心')>=0;});
          if(!node)return {err:'架构节点不可见'};
          const name=node.querySelector('.dept-name');
          const cnt=node.querySelector('.dept-count');
          const home=node.querySelector('.dept-home');
          const nr=name.getBoundingClientRect(), cr=cnt.getBoundingClientRect(), hr=home.getBoundingClientRect();
          // 看板行徽标（对照形态）
          const bcnt=document.querySelector('.tab-btn .tab-col-count');
          const bs=bcnt?getComputedStyle(bcnt):null, cs=getComputedStyle(cnt);
          return {nameLeft:Math.round(nr.left), cntLeft:Math.round(cr.left), cntRight:Math.round(cr.right),
                  homeLeft:Math.round(hr.left),
                  between:cr.right<=hr.left+1,
                  afterName:cr.left>=nr.right-2,
                  fontSame:bs?cs.fontSize===bs.fontSize:false,
                  padSame:bs?cs.paddingLeft===bs.paddingLeft:false,
                  hasBoardBadge:!!bcnt};
        })()""")
        ok(r5 and not r5.get('err') and r5.get('hasBoardBadge') and r5.get('between') and r5.get('afterName'),
           "⑤ 架构数量徽标位于名称之后、「主页」按钮左侧（%s/%s/%s）" % ((r5 or {}).get('nameLeft'), (r5 or {}).get('cntLeft'), (r5 or {}).get('homeLeft')))
        ok(r5 and r5.get('fontSame') and r5.get('padSame'),
           "⑤ 徽标形态与看板行板块数徽标一致（字号/内边距同值）")

        # ── ③ 取消架构联动（综合工作事项归属「核算部」）──
        await ev("if(ARCH_SEL.has('核算部'))toggleDept('核算部')")   # 状态归零
        await asyncio.sleep(1)
        await ev("toggleDept('核算部')")
        await asyncio.sleep(1.5)
        await ev("if(curBoards.has('%s'))pickBoard('%s')" % (BOARD, BOARD))   # 先清掉已有选择（pickBoard 是 toggle）
        await asyncio.sleep(1)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2)
        pre = await ev("({n:curBoards.size,has:curBoards.has('%s'),open:!!DEPT_OPEN['核算部']})" % BOARD)
        ok(pre and pre.get('has') is True and pre.get('n') == 1,
           "③ 前置：架构下看板已选中（curBoards=%s）" % (pre or {}).get('n'))
        await ev("toggleDept('核算部')")
        await asyncio.sleep(2)
        post = await ev("""(function(){
          const tabs=[].slice.call(document.querySelectorAll('.tab-btn'))
            .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('综合工作事项')>=0;});
          return {n:curBoards.size, has:curBoards.has('%s'), open:!!DEPT_OPEN['核算部'],
                  tabVisible:tabs.length>0, curBoard:curBoard};
        })()""" % BOARD)
        ok(post and post.get('has') is False and post.get('n') == 0,
           "③ 取消架构 → 该架构下已选看板自动取消（curBoards=%s）" % (post or {}).get('n'))
        ok(post and post.get('open') is False and post.get('tabVisible') is False,
           "③ 取消架构 → 该架构的看板 tab 不再显示（open=%s）" % (post or {}).get('open'))

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            for cid in card_ids: api('/api/cards/' + cid, 'DELETE')
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
            if prog_key: api('/api/columns/' + urllib.parse.quote(prog_key, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205u')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
