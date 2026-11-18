# -*- coding: utf-8 -*-
"""T-205n 默认状态「进行中」实测：
① CDP：新建事项弹窗初始态（NEW_CARD_STATUS/picker 高亮）
② CDP：新建板块弹窗初始态（COL_COMPLETION）
③ API：POST /api/columns 不带 completion → 落库 progressing（夹具测完删）
④ API：POST /api/cards 不带 status → 落库 progressing（夹具测完删）
⑤ CDP：编辑存量事项 → picker 显示原状态（不受默认影响）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205n')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9637',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9637/json/version', timeout=2); break
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
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9637/json', timeout=5).read())
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

        # ① 新建事项弹窗初始态
        r1 = await ev("""(function(){
          if(typeof openNewModal==='function')openNewModal();
          else if(typeof openCreateModal==='function')openCreateModal();
          else if(typeof openCardCreate==='function')openCardCreate();
          return {fnUsed:1};
        })()""")
        await asyncio.sleep(1.5)
        r1b = await ev("""(function(){
          const m=document.getElementById('newModal')||document.getElementById('createModal');
          const btn=document.querySelector('#n_status_ops .status-btn');
          return {NEW:(typeof NEW_CARD_STATUS!=='undefined')?NEW_CARD_STATUS:null, modalOpen:!!(m&&m.style.display!=='none'),
                  pickerOn:btn?btn.textContent.trim():''};
        })()""")
        ok(r1b and r1b.get('NEW') == 'progressing' and '进行中' in (r1b.get('pickerOn') or ''),
           "① 新建事项弹窗：默认状态=进行中（NEW_CARD_STATUS=%s，picker 高亮=%r）"
           % (r1b.get('NEW'), r1b.get('pickerOn')))
        await ev("closeModal('newModal');closeModal('createModal');")

        # ② 新建板块弹窗初始态
        r2 = await ev("""(function(){
          if(typeof openColumnModal==='function')openColumnModal();
          return {ok:1};
        })()""")
        await asyncio.sleep(1.5)
        r2b = await ev("""(function(){
          const m=document.getElementById('columnModal');
          const btn=document.querySelector('#c_status_ops .status-btn');
          return {COL:window.COL_COMPLETION, modalOpen:!!(m&&m.style.display!=='none'),
                  pickerOn:btn?btn.textContent.trim():''};
        })()""")
        ok(r2b and r2b.get('COL') == 'progressing' and '进行中' in (r2b.get('pickerOn') or ''),
           "② 新建板块弹窗：完成情况默认=进行中（COL_COMPLETION=%s，picker 高亮=%r）"
           % (r2b.get('COL'), r2b.get('pickerOn')))
        await ev("closeModal('columnModal')")

        # ③ API：新建板块不带 completion → progressing（夹具 __t205n 测完删）
        col_name = '__t205n_默认状态板块'
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': col_name,
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
        if st not in (200, 201):
            print('   ③ 建板块响应:', st, json.dumps(d, ensure_ascii=False)[:160], flush=True)
        ck = (d or {}).get('col_key')
        st2, d2 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        cols = (d2.get('columns') or [])
        meta = next((c for c in cols if c.get('col_key') == ck), {})
        ok(meta.get('completion') == 'progressing',
           "③ API 新建板块（不带 completion）→ 落库 completion=%r（预期 progressing）" % meta.get('completion'))

        # ④ API：新建事项不带 status → progressing
        card_name = '__t205n_默认状态事项'
        st3, d3 = api('/api/cards', 'POST', {'board_id': BOARD, 'column_name': col_name,
                                             'card_name': card_name, 'nature': '日常',
                                             'created': '2026-11-18'})
        if st3 not in (200, 201):
            print('   ④ 建事项响应:', st3, json.dumps(d3, ensure_ascii=False)[:160], flush=True)
        cid = (d3 or {}).get('card_id') or ((d3 or {}).get('card') or {}).get('card_id')
        st4, d4 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        card = next((c for c in (d4.get('cards') or []) if c.get('card_id') == cid), {})
        ok(card.get('status') == 'progressing',
           "④ API 新建事项（不带 status）→ 落库 status=%r（预期 progressing）" % card.get('status'))

        # ⑤ 编辑存量事项 → picker 显示原状态
        r5 = await ev("""(function(){
          const ids=CHK_CURRENT_CARDS||[];
          const meta=CHK_CURRENT_CARDS_META||{};
          const done=ids.find(function(id){return (meta[id]||{});});
          return {n:ids.length};
        })()""")
        st5, d5 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        existing = [c for c in (d5.get('cards') or []) if c.get('status') == 'done']
        if existing:
            c0 = existing[0]
            await ev("closeModal('columnModal')")
            r5b = await ev("""(async function(){
              openDetail('%s');
              await new Promise(function(r){setTimeout(r,1500);});
              openDetailEdit();
              await new Promise(function(r){setTimeout(r,1500);});
              const btn=document.querySelector('#e_status_ops .status-btn');
              return {pickerOn:btn?btn.textContent.trim():''};
            })()""" % c0['card_id'], aw=True)
            ok('已完成' in (r5b.get('pickerOn') or ''),
               "⑤ 编辑存量事项（status=done）→ picker 显示原状态「已完成」（%r，默认不影响存量）"
               % r5b.get('pickerOn'))
        else:
            print('SKIP ⑤ 当前看板无已完成事项，跳过存量编辑检查', flush=True)

        # 夹具清理：删夹具事项 + 夹具板块（D5 自清理）
        if cid:
            api('/api/cards/' + cid, 'DELETE')
        if ck:
            api('/api/columns/' + urllib.parse.quote(ck, safe=''), 'DELETE')
        st6, d6 = api('/api/cards?size=1000000&board_ids=' + BOARD)
        left_col = any(c.get('col_key') == ck for c in (d6.get('columns') or []))
        left_card = any(c.get('card_id') == cid for c in (d6.get('cards') or []))
        ok(not left_col and not left_card, "⑥ 夹具清理：测试板块/事项已删除（零残留）")
        print('---- 结果: %d PASS / %d FAIL ----' % (ok_n, fail_n), flush=True)
    finally:
        # 兜底清理
        try:
            st, d = api('/api/cards?size=1000000&board_ids=' + BOARD)
            for c in (d.get('cards') or []):
                if (c.get('card_name') or '').startswith('__t205n_'):
                    api('/api/cards/' + c['card_id'], 'DELETE')
            for c in (d.get('columns') or []):
                if (c.get('column_name') or '').startswith('__t205n_'):
                    api('/api/columns/' + urllib.parse.quote(c['col_key'], safe=''), 'DELETE')
        except Exception:
            pass
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205n')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
