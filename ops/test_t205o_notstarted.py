# -*- coding: utf-8 -*-
"""T-205o 状态「未开始」实测：
① CDP 状态选择器菜单四态且按用户口径排序（未开始/进行中/已完成/未完成）
② CDP 顶部统计卡五张（含未开始）且和=总事项
③ CDP 板块状态下拉四项同序
④ API 新建事项 status=notstarted → 落库+读回（夹具自清理）
⑤ API status 筛选：notstarted 命中仅未开始；open 不含未开始（口径互斥）
⑥ CDP 板块完成情况设为未开始 → 落库（夹具板块，测完删）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205o')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9639',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9639/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    w = None
    ok_n = fail_n = 0
    def ok(cond, msg):
        nonlocal ok_n, fail_n
        print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
        if cond: ok_n += 1
        else: fail_n += 1
    def api(path, method='GET', body=None):
        req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
        req.add_header('Authorization', 'Bearer ' + tk)
        if body is not None:
            req.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=20, data=json.dumps(body).encode() if body is not None else None) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read().decode())
            except Exception: return e.code, {}
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9639/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50*1024*1024)
        pending = {}
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        seq = [0]
        async def send(mm, p=None):
            seq[0] += 1
            f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
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
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2)

        # ① 状态选择器菜单（新建事项弹窗）
        await ev("openNewModal()")
        await asyncio.sleep(1.5)
        r1 = await ev("""(function(){
          document.querySelector('#n_status_ops .status-btn').click();
          const opts=[].slice.call(document.querySelectorAll('#n_status_menu button'))
            .map(function(b){return b.textContent.trim();});
          document.body.click();
          return {opts:opts};
        })()""")
        ok(r1 and r1.get('opts') == ['未开始', '进行中', '已完成', '未完成'],
           "① 状态选择器菜单四态且排序=未开始/进行中/已完成/未完成（%s）" % r1.get('opts'))
        await ev("closeModal('newModal')")

        # ② 顶部统计卡五张 + 和=总事项
        r2 = await ev("""(function(){
          const cards=[].slice.call(document.querySelectorAll('#progressOverview .stat-card'))
            .map(function(c){return {label:c.querySelector('.stat-label').textContent.trim(),
                                     v:Number(c.querySelector('.stat-value').textContent)||0};});
          const sum=cards.slice(1).reduce(function(a,c){return a+c.v;},0);
          const total=(cards[0]||{}).v||0;
          return {labels:cards.map(function(c){return c.label;}), sum:sum, total:total};
        })()""")
        ok(r2 and r2.get('labels') == ['总事项', '未开始', '进行中', '已完成', '未完成']
           and r2.get('sum') == r2.get('total'),
           "② 统计卡五张且排序符合口径、和=总事项（labels=%s，%s=%s）"
           % (r2.get('labels'), r2.get('sum'), r2.get('total')))

        # ③ 板块状态下拉四项同序
        r3 = await ev("""(function(){
          if(typeof COL_STATUS_OPTS==='undefined')return {err:'no opts'};
          return {opts:COL_STATUS_OPTS.map(function(o){return o[1];})};
        })()""")
        ok(r3 and r3.get('opts') == ['未开始', '进行中', '已完成', '未完成'],
           "③ 板块状态下拉四项同序（%s）" % r3.get('opts'))

        # ④ API 新建事项 notstarted → 落库（夹具）
        col_name = '__t205o_状态板块'
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': col_name,
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18',
                                            'completion': 'notstarted'})
        ck = (d or {}).get('col_key')
        st2, d2 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        meta = next((c for c in (d2.get('columns') or []) if c.get('col_key') == ck), {})
        ok(meta.get('completion') == 'notstarted',
           "⑥ 板块完成情况=未开始 → 落库 %r" % meta.get('completion'))
        st3, d3 = api('/api/cards', 'POST', {'board_id': BOARD,
                                            'card_name': '__t205o_未开始事项',
                                            'column_name': col_name,
                                            'fields': {'status': 'notstarted',
                                                       'status_name': '未开始',
                                                       'nature': '日常',
                                                       'created': '2026-11-18'}})
        cid = (d3 or {}).get('card_id') or ((d3 or {}).get('card') or {}).get('card_id')
        st4, d4 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        card = next((c for c in (d4.get('cards') or []) if c.get('card_id') == cid), {})
        ok(card.get('status') == 'notstarted',
           "④ 新建事项 status=notstarted → 落库 %r" % card.get('status'))

        # ⑤ status 筛选口径：notstarted 命中仅未开始；open 不含未开始
        st5, d5 = api('/api/cards?size=1000000&board_ids=%s&status=notstarted' % BOARD)
        hit_ns = [c for c in (d5.get('cards') or []) if c.get('status') == 'notstarted']
        miss = [c for c in (d5.get('cards') or []) if c.get('status') != 'notstarted']
        ok(len((d5.get('cards') or [])) == len(hit_ns) and len(hit_ns) >= 1,
           "⑤a status=notstarted 筛选：命中 %d 项且全部为未开始（无其他状态混入）" % len(hit_ns))
        st6, d6 = api('/api/cards?size=1000000&board_ids=%s&status=open' % BOARD)
        ns_in_open = [c for c in (d6.get('cards') or []) if c.get('status') == 'notstarted']
        ok(len(ns_in_open) == 0,
           "⑤b status=open 筛选：不含未开始项（口径互斥，混入 %d 项）" % len(ns_in_open))

        # 夹具清理
        if cid: api('/api/cards/' + cid, 'DELETE')
        if ck: api('/api/columns/' + urllib.parse.quote(ck, safe=''), 'DELETE')
        st7, d7 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        left = any(c.get('col_key') == ck or c.get('card_id') == cid
                   for c in ((d7.get('columns') or []) + (d7.get('cards') or [])))
        ok(not left, "⑦ 夹具清理零残留")
        print('---- 结果: %d PASS / %d FAIL ----' % (ok_n, fail_n), flush=True)
    finally:
        try:
            st, d = api('/api/cards?size=1000000&board_ids=' + BOARD)
            for c in (d.get('cards') or []):
                if (c.get('card_name') or '').startswith('__t205o_'):
                    api('/api/cards/' + c['card_id'], 'DELETE')
            for c in (d.get('columns') or []):
                if (c.get('column_name') or '').startswith('__t205o_'):
                    api('/api/columns/' + urllib.parse.quote(c['col_key'], safe=''), 'DELETE')
        except Exception:
            pass
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205o')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
