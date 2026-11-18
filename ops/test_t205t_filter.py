# -*- coding: utf-8 -*-
"""T-205t：板块筛选与状态颜色三项修复 CDP 实测（2026-11-18）
① 专项/日常筛选改用板块级 nature（原误用看板级 attr → 行为颠倒）；
② 状态筛选四种状态逐一验证 + 隐式建板块（新建事项带新板块名）默认「进行中」；
③ 「未开始」颜色统一：目录列表 status-tag 与预览 status-btn 同为灰色系。
API 夹具（__t205t_ 前缀）测完即删。"""
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
    # ── 夹具：四状态板块（专项×2 + 日常×2）+ 未开始事项 ──
    fx = {}
    for name, nature, comp in [('__t205t_专项进行中', '专项', 'progressing'),
                               ('__t205t_专项未开始', '专项', 'notstarted'),
                               ('__t205t_日常未完成', '日常', 'open'),
                               ('__t205t_日常进行中', '日常', 'progressing')]:
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': name,
                                            'nature': nature, 'year': '2026', 'completion': comp,
                                            'created_at': '2026-11-18'})
        if st in (200, 201): fx[name] = d.get('col_key')
    # 未开始事项（验证 ③ 目录标签颜色）
    stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205t_未开始事项',
                                        'fields': {'column_name': '__t205t_专项未开始',
                                                   'status': 'notstarted', 'status_name': '未开始'}})
    card_id = dc.get('card_id') if stc in (200, 201) else None
    # ②-bis 隐式建板块路径：新建事项带**新板块名** → 板块元信息默认 progressing
    stc2, dc2 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205t_隐式板块事项',
                                          'fields': {'column_name': '__t205t_隐式新板块'}})
    implicit_card = dc2.get('card_id') if stc2 in (200, 201) else None
    stq, dq = api('/api/cards?board_id=' + BOARD + '&size=500')
    _imp = [c for c in (dq.get('columns') or []) if c['column_name'] == '__t205t_隐式新板块']
    ok(stq == 200 and _imp and (_imp[0].get('completion') or '') == 'progressing',
       "②-bis 隐式建板块（事项带新板块名）默认「进行中」（实际 %r）" % (_imp[0].get('completion') if _imp else None))
    print('fixture:', len(fx), card_id, implicit_card, flush=True)

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205t2')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1600,960',
                      '--remote-debugging-port=9639', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9639/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9639/json', timeout=5).read())
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

        async def visible_fixtures():
            return await ev("""[].slice.call(document.querySelectorAll('.week-title'))
              .filter(function(x){return x.offsetParent!==null;})
              .map(function(x){return x.textContent;})
              .filter(function(s){return s.indexOf('__t205t_')>=0;}).sort().join(',')""")

        # ── ① 性质筛选：选「专项」→ 只剩 2 个专项夹具板块；选「日常」→ 2 个日常 + 隐式板块（默认日常） ──
        await ev("toggleAttrPick('专项')")
        await asyncio.sleep(2)
        v1 = await visible_fixtures()
        ok(v1 == '__t205t_专项未开始,__t205t_专项进行中',
           "① 选「专项」→ 只显示板块级 nature=专项 的板块（实际 %r）" % v1)
        await ev("toggleAttrPick('专项');toggleAttrPick('日常')")
        await asyncio.sleep(2)
        v2 = await visible_fixtures()
        ok(v2 == '__t205t_日常未完成,__t205t_日常进行中,__t205t_隐式新板块',
           "① 选「日常」→ 只显示 nature=日常 的板块，专项板块不再混入（实际 %r）" % v2)
        await ev("toggleAttrPick('日常')")
        await asyncio.sleep(1.5)

        # ── ② 状态筛选：四态逐一验证（隐式板块=进行中） ──
        for val, expect in [('progressing', '__t205t_专项进行中,__t205t_日常进行中,__t205t_隐式新板块'),
                            ('notstarted', '__t205t_专项未开始'),
                            ('open', '__t205t_日常未完成')]:
            await ev("toggleColStatusPick('%s')" % val)
            await asyncio.sleep(2)
            v = await visible_fixtures()
            ok(v == expect, "② 状态筛选「%s」→ %s（实际 %r）" % (col_lbl(val), expect, v))
            await ev("toggleColStatusPick('%s')" % val)
            await asyncio.sleep(1.5)
        # 「已完成」：无夹具（done 需全部事项完成）→ 断言筛后不含任何夹具板块
        await ev("toggleColStatusPick('done')")
        await asyncio.sleep(2)
        v = await visible_fixtures()
        ok(v == '', "② 状态筛选「已完成」→ 无已完成板块（实际 %r）" % v)
        await ev("toggleColStatusPick('done')")
        await asyncio.sleep(1.5)

        # ── ③ 「未开始」颜色统一（先展开全部板块：折叠板块里的行 offsetParent 为 null）──
        await ev("expandAll()")
        await asyncio.sleep(2)
        # 目录列表：事项行 status-tag 的 class 与背景色
        r3 = await ev("""(function(){
          const row=[].slice.call(document.querySelectorAll('.item-wrap'))
            .find(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205t_未开始事项')>=0;});
          if(!row)return {err:'事项行不可见'};
          const tag=row.querySelector('.slot-status .status-tag');
          const bg=getComputedStyle(tag).backgroundColor;
          return {cls:tag.className, bg:bg};
        })()""")
        ok(r3 and not r3.get('err') and 'notstarted' in (r3.get('cls') or ''),
           "③ 目录列表「未开始」标签用独立 notstarted class（实际 %r）" % (r3 or {}).get('cls'))
        ok(r3 and (r3.get('bg') or '').replace(' ', '') == 'rgb(240,242,245)',
           "③ 目录列表「未开始」标签灰色底 #f0f2f5（实际 %r）" % (r3 or {}).get('bg'))
        # 板块行完成情况标签（未开始板块）
        r3b = await ev("""(function(){
          const hs=[].slice.call(document.querySelectorAll('.week-header'))
            .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205t_专项未开始')>=0;});
          if(!hs.length)return {err:'板块行不可见'};
          const tag=hs[0].querySelector('.slot-status .status-tag');
          return {cls:tag.className, text:tag.textContent.trim()};
        })()""")
        ok(r3b and not r3b.get('err') and 'notstarted' in (r3b.get('cls') or '') and (r3b.get('text') or '') == '未开始',
           "③ 板块行完成情况「未开始」同为灰色 notstarted（实际 %r）" % (r3b or {}).get('cls'))
        # 预览界面：事项详情状态按钮
        r3c = await ev("""(async function(){
          openDetail('%s');
          await new Promise(function(r){setTimeout(r,1800);});
          const btn=document.querySelector('#d_ops .status-btn');
          const dot=btn?btn.querySelector('.status-dot'):null;
          return {cls:btn?btn.className:'', dot:dot?getComputedStyle(dot).backgroundColor:''};
        })()""" % card_id, aw=True)
        ok(r3c and not r3c.get('__error__') and 'notstarted' in (r3c.get('cls') or ''),
           "③ 预览界面状态按钮「未开始」同样 notstarted class（实际 %r）" % (r3c or {}).get('cls'))
        ok(r3c and (r3c.get('dot') or '') == 'rgb(138, 147, 166)',
           "③ 预览状态按钮圆点灰色 #8a93a6（实际 %r）" % (r3c or {}).get('dot'))
        await ev("document.querySelectorAll('.modal-overlay').forEach(function(m){m.style.display='none';})")

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            if card_id: api('/api/cards/' + card_id, 'DELETE')
            if implicit_card: api('/api/cards/' + implicit_card, 'DELETE')
            for k in fx.values():
                api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
            # 隐式板块没有夹具登记 → 按名删
            stq, dq = api('/api/cards?board_id=' + BOARD + '&size=500')
            for c in (dq.get('columns') or []):
                if c['column_name'] == '__t205t_隐式新板块':
                    api('/api/columns/' + urllib.parse.quote(c['col_key'], safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205t2')
        shutil.rmtree(profile, ignore_errors=True)

def col_lbl(v):
    return {'progressing': '进行中', 'notstarted': '未开始', 'open': '未完成', 'done': '已完成'}.get(v, v)

asyncio.run(main())
