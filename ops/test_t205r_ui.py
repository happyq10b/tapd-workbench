# -*- coding: utf-8 -*-
"""T-205r：7 项界面修改 CDP 实测（2026-11-18）
① 周数列最早2周+…；② 目录创建→开始；③ 预览末行五字段；④ 统计卡5张等宽一行；
⑤ 看板tab板块数徽标；⑥ 新建看板按钮无阴影；⑦ 登录按钮下移一行。
API 夹具（__t205r_ 前缀）测完即删。"""
import asyncio, io, json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

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
    # ── 夹具：板块 + 3 周事项 ──
    col_key = None; card_id = None
    st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205r_周数板块',
                                        'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
    if st in (200, 201): col_key = d.get('col_key')
    st3, d3 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205r_跨周事项',
                                        'fields': {'column_name': '__t205r_周数板块',
                                                   'week_no': '2026年第47周;2026年第46周;2026-48',
                                                   'nature': '日常', 'created': '2026-11-18'}})
    if st3 in (200, 201): card_id = d3.get('card_id')
    print('fixture:', st, st3, card_id, flush=True)

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205r')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1440,960',
                      '--remote-debugging-port=9631', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9631/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9631/json', timeout=5).read())
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

        # 登录
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)

        # ── ⑦ 登录按钮下移（独立页面量） ──
        await ev("location.href='/login'")
        await asyncio.sleep(2)
        r7 = await ev("""(function(){
          const b=document.getElementById('btn');
          return {mt:getComputedStyle(b).marginTop, w:Math.round(b.getBoundingClientRect().width)};
        })()""")
        ok(r7 and r7.get('mt') == '20px' and (r7.get('w') or 0) > 200,
           "⑦ 登录按钮 margin-top=20px（下移约一行）")
        await ev("location.href='/'")
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)

        # ── ⑤ 看板 tab 板块数徽标（带 2 只渲染已展开部门的看板 → 先展开夹具看板所属部门） ──
        await ev("""(function(){
          const b=(ME.boards||[]).find(function(x){return x.board_id==='BCP1793717004248';});
          if(b&&b.dept&&!DEPT_OPEN[b.dept])toggleDept(b.dept);
          return {dept:b?b.dept:''};
        })()""")
        await asyncio.sleep(1.5)
        r5 = await ev("""(function(){
          const badges=[].slice.call(document.querySelectorAll('.tab-btn .tab-col-count'));
          return {n:badges.length, samples:badges.slice(0,4).map(function(x){return x.textContent.trim();})};
        })()""")
        ok(r5 and (r5.get('n') or 0) >= 1 and all(str(x).isdigit() for x in (r5.get('samples') or [])),
           "⑤ 看板 tab 标题后板块数徽标（%s 个，样例 %s）" % (r5.get('n'), r5.get('samples')))

        # ── ⑥ 新建看板按钮无阴影 ──
        r6 = await ev("""(function(){
          const b=document.getElementById('bandNewBoardBtn');
          if(!b)return {err:'按钮不存在'};
          const st=getComputedStyle(b);
          return {shadow:st.boxShadow, hov:'(hover 由 CSS 覆盖断言)'};
        })()""")
        ok(r6 and r6.get('shadow') in ('none', ''),
           "⑥ 新建看板按钮 box-shadow=none（实际 %r）" % (r6 or {}).get('shadow'))

        # ── ④ 统计卡 5 张等宽一行 ──
        r4 = await ev("""(function(){
          const cards=[].slice.call(document.querySelectorAll('#progressOverview .stat-card'));
          const ws=cards.map(function(c){return Math.round(c.getBoundingClientRect().width);});
          const tops=cards.map(function(c){return Math.round(c.getBoundingClientRect().top);});
          return {n:cards.length, ws:ws, topSet:[...new Set(tops)].length,
                  sameW:ws.length&&Math.max.apply(null,ws)-Math.min.apply(null,ws)<=2};
        })()""")
        ok(r4 and r4.get('n') == 5 and r4.get('sameW') and r4.get('topSet') == 1,
           "④ 统计卡 5 张等宽一行（宽度 %s，行数 %s）" % (r4.get('ws'), r4.get('topSet')))

        # ── 进入看板（夹具板块/事项所在） ──
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        await ev("expandAll()")
        await asyncio.sleep(2)

        # ── ① 板块目录：周数列最早 2 周 + …（事项行）＋ ② 目录开始列 ──
        r1 = await ev("""(function(){
          const rows=[].slice.call(document.querySelectorAll('.item-wrap')).filter(function(x){return x.offsetParent!==null;});
          const row=rows.find(function(x){return x.textContent.indexOf('__t205r_跨周事项')>=0;});
          if(!row)return {err:'夹具事项行不可见'};
          const wk=row.querySelector('.fcol-week_no');
          const cr=row.querySelector('.fcol-created');
          return {weekText:wk?wk.textContent.trim():'', created:cr?cr.textContent.trim():'',
                  weekTip:wk?wk.getAttribute('title'):''};
        })()""")
        _wt = (r1.get('weekText') or '') if r1 else ''
        # #205s（2026-11-18 需求5）口径更新：周数列改为两个**完整周数**（非压缩形态）
        ok(_wt.startswith('周数 2026年第46周、2026年第47周') and _wt.endswith('…'),
           "① 事项行周数列 = 最早 2 周 + …（实际 %r）" % _wt)
        ok(r1 and r1.get('weekTip') and '2026年第46周' in r1.get('weekTip') and '2026年第48周' in r1.get('weekTip'),
           "① 悬停提示仍展示全部周数")
        ok(r1 and (r1.get('created') or '').startswith('开始 '),
           "② 事项目录「创建」列改为「开始」（实际 %r）" % (r1 or {}).get('created'))

        # 板块行：开始列 + 周数列不适用（板块无周数）
        r2 = await ev("""(function(){
          const hs=[].slice.call(document.querySelectorAll('.week-header .fcol-created'))
            .filter(function(x){return x.offsetParent!==null;});
          return {n:hs.length, sample:hs.length?hs[0].textContent.trim():'',
                  title:hs.length?hs[0].getAttribute('title'):''};
        })()""")
        ok(r2 and (r2.get('n') or 0) >= 1 and (r2.get('sample') or '').startswith('开始 '),
           "② 板块目录「创建」列改为「开始」（实际 %r）" % (r2 or {}).get('sample'))

        # ── ③ 板块预览：末行五字段顺序 ──
        r3 = await ev("""(async function(){
          const el=[].slice.call(document.querySelectorAll('.week-title'))
            .find(function(x){return x.textContent.indexOf('__t205r_周数板块')>=0;});
          if(!el)return {err:'夹具板块标题不可见'};
          await openColumnDetail(el);
          await new Promise(function(r){setTimeout(r,1500);});
          const m=document.getElementById('cd_meta');
          const txt=m.textContent;
          const order=['创建人','创建时间','开始时间','截止时间','倒计时'];
          const idx=order.map(function(k){return txt.indexOf(k);});
          return {text:txt.slice(0,200), idx:idx,
                  ordered:idx.every(function(v,i){return v>=0&&(i===0||v>idx[i-1]);})};
        })()""", aw=True)
        ok(r3 and not r3.get('err') and r3.get('ordered'),
           "③ 板块预览末行 = 创建人→创建时间→开始时间→截止时间→倒计时（索引 %s）" % (r3 or {}).get('idx'))
        await ev("document.querySelectorAll('.modal-overlay').forEach(function(m){m.style.display='none';})")
        await asyncio.sleep(0.8)

        # ── ③ 事项预览：追加创建人 + 开始时间，末行五字段顺序 ──
        r3b = await ev("""(async function(){
          openDetail('%s');
          await new Promise(function(r){setTimeout(r,2000);});
          const m=document.getElementById('d_meta');
          const txt=m.textContent;
          const order=['创建人','创建时间','开始时间','截止时间','倒计时'];
          const idx=order.map(function(k){return txt.indexOf(k);});
          return {hasCreator:txt.indexOf('创建人')>=0, hasBegin:txt.indexOf('开始时间')>=0,
                  idx:idx, ordered:idx.every(function(v,i){return v>=0&&(i===0||v>idx[i-1]);})};
        })()""" % card_id, aw=True)
        ok(r3b and r3b.get('hasCreator') and r3b.get('hasBegin') and r3b.get('ordered'),
           "③ 事项预览追加创建人+开始时间，末行五字段有序（索引 %s）" % (r3b or {}).get('idx'))

        # ── API 口径核对：/api/me col_count ──
        st9, d9 = api('/api/me')
        b9 = [b for b in (d9.get('boards') or []) if b.get('board_id') == BOARD]
        ok(st9 == 200 and b9 and isinstance(b9[0].get('col_count'), int),
           "⑤-bis /api/me 每看板下发 col_count（%s）" % (b9[0].get('col_count') if b9 else None))

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            if card_id: api('/api/cards/' + card_id, 'DELETE')
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205r')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
