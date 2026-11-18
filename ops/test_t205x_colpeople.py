# -*- coding: utf-8 -*-
"""T-205x：板块筛选栏【负责人】【参与人】改板块维度 CDP 实测（2026-11-18）
① 负责人筛选 → 按 board_columns.owner（账号，姓名比对）过滤板块行；
② 参与人筛选 → 按 participants 过滤；③「无负责人/无参与人」= 字段为空；
④ 板块内全部事项照常渲染（不再按事项 owner 过滤）。
API 夹具（__t205x_ 前缀）测完即删。"""
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
    # ── 夹具：甲（负责人=hly 何兰英）+ 乙（参与人=hqx 何巧娴，无负责人）+ 各 1 张无主卡 ──
    stq, dq = api('/api/team')
    mem = (dq.get('members') or dq or [])
    acc = {}
    for m in mem:
        if m.get('account') == 'hly': acc['hly'] = m.get('name')
        if m.get('account') == 'hqx': acc['hqx'] = m.get('name')
    keys = {}
    for name, owner, parts in [('__t205x_甲', 'hly', ''), ('__t205x_乙', '', 'hqx')]:
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': name,
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18',
                                            'owner': owner, 'participants': parts})
        if st in (200, 201): keys[name] = d.get('col_key')
    cid = None
    stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205x_甲内事项',
                                        'fields': {'column_name': '__t205x_甲'}})
    if stc in (200, 201): cid = dc.get('card_id')
    # 落库核对 owner/participants 确实写入
    stv, dv = api('/api/cards?board_id=' + BOARD + '&size=500')
    rows = {c['column_name']: c for c in (dv.get('columns') or []) if c['column_name'].startswith('__t205x_')}
    print('fixture:', keys, acc, [(k, r.get('owner'), r.get('participants')) for k, r in rows.items()], flush=True)
    ok(len(keys) == 2 and len(rows) == 2 and rows['__t205x_甲'].get('owner') == 'hly'
       and rows['__t205x_乙'].get('participants') == 'hqx',
       '夹具 owner/participants 落库正确')

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205x')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                      '--remote-debugging-port=9653', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9653/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9653/json', timeout=5).read())
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

        async def visible_fx():
            return await ev("""[].slice.call(document.querySelectorAll('.week-title'))
              .filter(function(x){return x.offsetParent!==null;})
              .map(function(x){return x.textContent;})
              .filter(function(s){return s.indexOf('__t205x_')>=0;}).sort().join(',')""")

        # 候选池：负责人候选含 何兰英、参与人候选含 何巧娴
        r0 = await ev("(function(){return {own:colOwnerNames().filter(function(n){return n==='%s'}),"
                      "part:colParticipantNames().filter(function(n){return n==='%s'})};})()"
                      % (acc.get('hly'), acc.get('hqx')))
        print('候选池实际值:', json.dumps(r0, ensure_ascii=False), flush=True)
        ok(r0 and not r0.get('__error__') and (r0.get('own') or [None])[0] == acc['hly']
           and (r0.get('part') or [None])[0] == acc['hqx'],
           "候选池 = 板块名单（负责人候选含 %s、参与人候选含 %s）" % (acc.get('hly'), acc.get('hqx')))

        # ── ① 负责人筛选：选「何兰英」→ 只剩甲，且甲内事项全部照常渲染 ──
        await ev("PERSON_SEL=new Set([%s]);paintFilterCombos();reload(1)" % json.dumps(acc['hly'], ensure_ascii=False))
        await asyncio.sleep(2.5)
        v = await visible_fx()
        ok(v == '__t205x_甲', "① 负责人筛选「%s」→ 只显示其负责的板块（实际 %r）" % (acc.get('hly'), v))
        cardVis = await ev("document.body.textContent.indexOf('__t205x_甲内事项')>=0")
        ok(cardVis is True, "① 板块内事项全部照常渲染（不再按事项负责人过滤）")

        # ── ② 「无负责人」→ 只显示无负责人的板块 ──
        await ev("PERSON_SEL=new Set([OWNER_NONE]);paintFilterCombos();reload(1)")
        await asyncio.sleep(2.5)
        v = await visible_fx()
        ok(v == '__t205x_乙', "①-bis 「无负责人」→ 只显示负责人为空的板块（实际 %r）" % v)

        # ── ③ 参与人筛选：选「何巧娴」→ 只剩乙 ──
        await ev("PERSON_SEL=new Set();CC_SEL=new Set([%s]);paintFilterCombos();reload(1)" % json.dumps(acc['hqx'], ensure_ascii=False))
        await asyncio.sleep(2.5)
        v = await visible_fx()
        ok(v == '__t205x_乙', "③ 参与人筛选「%s」→ 只显示其参与的板块（实际 %r）" % (acc.get('hqx'), v))
        # 「无参与人」→ 只剩甲
        await ev("CC_SEL=new Set([OWNER_NONE]);paintFilterCombos();reload(1)")
        await asyncio.sleep(2.5)
        v = await visible_fx()
        ok(v == '__t205x_甲', "③-bis 「无参与人」→ 只显示参与人为空的板块（实际 %r）" % v)

        # 清理选择状态
        await ev("PERSON_SEL=new Set();CC_SEL=new Set();paintFilterCombos();reload(1)")
        await asyncio.sleep(1.5)

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            if cid: api('/api/cards/' + cid, 'DELETE')
            for k in keys.values():
                api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205x')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
