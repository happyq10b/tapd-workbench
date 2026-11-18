# -*- coding: utf-8 -*-
"""T-205w：排序选项修订（#205w 2026-11-18）CDP 实测
① 置顶改为**公共首级**（不再作为选项）：下拉三档 created/begin/due，置顶卡在任何档位都浮顶；
② 同一选项同步作用板块（cmpColumn）与子事项（renderSubTree）。
API 夹具（__t205w_ 前缀）测完即删。"""
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
    # ── 夹具：排序板块 + 3 主卡 + 1 主卡挂 2 子卡 ──
    col_key = None; sub_key = None; ids = {}
    st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205w_排序板块',
                                        'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
    if st in (200, 201): col_key = d.get('col_key')
    for name, begin, due in [('__t205w_卡A', '2026-11-01', '2026-12-20'),
                             ('__t205w_卡B', '2026-11-05', '2026-12-10'),
                             ('__t205w_卡C', '', '')]:
        stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': name,
                                            'fields': {'column_name': '__t205w_排序板块',
                                                       'begin': begin, 'due': due}})
        if stc in (200, 201): ids[name] = dc.get('card_id')
        time.sleep(1.1)   # created 秒级精度 → 间隔保证「创建时间降序」断言确定性
    # 子事项父卡（无日期）+ 2 子卡（due 各异）
    stp, dpp = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205w_父卡',
                                         'fields': {'column_name': '__t205w_排序板块'}})
    if stp in (200, 201): ids['__t205w_父卡'] = dpp.get('card_id')
    parent = ids.get('__t205w_父卡')
    for name, due in [('__t205w_子1', '2026-12-10'), ('__t205w_子2', '2026-12-20')]:
        sts, dss = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': name, 'parent_id': parent,
                                             'fields': {'column_name': '__t205w_排序板块', 'due': due}})
        if sts in (200, 201): ids[name] = dss.get('card_id')
        time.sleep(1.1)
    print('fixture:', st, stp, len(ids), flush=True)

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205w')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                      '--remote-debugging-port=9651', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9651/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9651/json', timeout=5).read())
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
                .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205w_排序板块')>=0;});
              if(!hs.length)return {err:'板块不可见'};
              const body=hs[0].parentElement.querySelector('.week-body');
              return {order:[].slice.call(body.querySelectorAll('.item-title')).map(function(x){return x.textContent;})};
            })()""")

        # ── ① 排序配置（#205y 起：下拉已移除，改由排序设定弹窗的多级配置驱动） ──
        async def set_card_cfg(order):
            # dir 默认：begin/due 升序、created 降序（与排序设定弹窗默认一致）
            # ⚠️ reload 会 loadSortCfg() 从 localStorage 恢复 → 改配置必须同步落盘
            d = {f: ('desc' if f == 'created' else 'asc') for f in order}
            return await ev("SORT_CFG.card={order:%s,dir:%s};"
                            "localStorage.setItem('tapd.sortCfg_'+ME.username,JSON.stringify(SORT_CFG));reload(1)"
                            % (json.dumps(order), json.dumps(d)))
        r1 = await ev("({selGone:!document.getElementById('cardSortSel'),cfg:!!(window.SORT_CFG&&SORT_CFG.card)})")
        ok(r1 and r1.get('selGone') and r1.get('cfg'),
           "① 筛选栏排序下拉已移除（#205y），排序由 SORT_CFG 配置驱动")
        # 创建时间降序（父卡创建最晚 → 第一）
        await set_card_cfg(['created'])
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or [])[:2] == ['__t205w_父卡', '__t205w_卡C'],
           "① 创建时间降序：新的在前（%s）" % (o or {}).get('order', [])[:2])
        # 截止升序：B(12-10) → A(12-20) → 无日期者最后（父卡比卡C 新 → 父卡在前）
        await set_card_cfg(['due'])
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or [])[:3] == ['__t205w_卡B', '__t205w_卡A', '__t205w_父卡'],
           "① 截止升序：最近到期在前、无截止排最后（%s）" % (o or {}).get('order', [])[:3])
        # 置顶浮顶：钉住卡C（无日期，本应最后）→ 任何配置下都在最前
        await ev("toggleCardPin('%s',1)" % ids['__t205w_卡C'])
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or [None])[0] == '__t205w_卡C',
           "① 置顶为公共首级：无日期的置顶卡在「截止」配置下也浮顶（%s）" % (o or {}).get('order', [])[:3])
        # 开始升序（卡C 保持置顶在最前；未置顶的 A(11-01) → B(11-05)）
        await set_card_cfg(['begin'])
        await asyncio.sleep(2)
        o = await fixture_order()
        ok(not o.get('err') and (o.get('order') or [])[:3] == ['__t205w_卡C', '__t205w_卡A', '__t205w_卡B'],
           "① 开始升序 + 置顶浮顶（%s）" % (o or {}).get('order', [])[:3])
        await ev("toggleCardPin('%s',0)" % ids['__t205w_卡C'])
        await asyncio.sleep(1.5)
        # 配置持久化：localStorage tapd.sortCfg → loadSortCfg 恢复
        rm = await ev("(function(){localStorage.setItem('tapd.sortCfg_'+ME.username,"
                      "JSON.stringify({card:{order:['begin'],dir:{begin:'asc',due:'asc',created:'desc'}},"
                      "col:{order:['created'],dir:{begin:'asc',due:'asc',created:'desc'}}}));"
                      "SORT_CFG={card:{order:[],dir:{}},col:{order:[],dir:{}}};loadSortCfg();"
                      "return {v:SORT_CFG.card.order.slice()};})()")
        ok(rm and rm.get('v') == ['begin'],
           "① 排序配置按账号持久化（loadSortCfg 恢复 %s）" % (rm or {}).get('v'))

        # ── ② 板块同步：cmpColumn 用板块分区配置（板块开始=created_at）──
        rc = await ev("""(function(){
          const m1={created_at:'2026-01-01',due_date:'',col_key:'b::甲',year:'2026'};
          const m2={created_at:'2026-02-01',due_date:'2026-03-01',col_key:'b::乙',year:'2026'};
          const D={begin:'asc',due:'asc',created:'desc'};
          SORT_CFG.col={order:['begin'],dir:D};
          const beginNeg=cmpColumn('甲','乙',{甲:m1,乙:m2},null)<0;   // begin：甲(1月) 在前
          SORT_CFG.col={order:['created'],dir:D};
          const createdPos=cmpColumn('甲','乙',{甲:m1,乙:m2},null)>0; // created 降序：乙(2月) 在前
          SORT_CFG.col={order:['due'],dir:D};
          const dueNeg=cmpColumn('乙','甲',{甲:m1,乙:m2},null)<0;     // due：乙有截止在前
          SORT_CFG.col={order:['begin'],dir:D};
          return {beginNeg:beginNeg, createdPos:createdPos, dueNeg:dueNeg, now:SORT_CFG.col.order.slice()};
        })()""")
        ok(rc and not rc.get('__error__') and rc.get('beginNeg') and rc.get('createdPos') and rc.get('dueNeg'),
           "② 板块排序独立配置：开始/创建/截止档均生效（%s）" % (rc or {}))
        ok(rc and rc.get('now') == ['begin'], "② 当前板块档位恢复 begin")

        # ── ②-bis 子事项同步：切「截止」配置 → 子1(12-10)在前；钉住子2(12-20) → 浮顶 ──
        await set_card_cfg(['due'])
        await asyncio.sleep(1.5)
        await ev("toggleSubTree('%s',true)" % parent)
        await asyncio.sleep(2)
        async def sub_order():
            return await ev("""(function(){
              const wrap=[].slice.call(document.querySelectorAll('.item-wrap'))
                .find(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205w_父卡')>=0;});
              const tree=wrap?wrap.querySelector('.sub-tree'):null;
              if(!tree||tree.style.display==='none')return {err:'子树未展开'};
              return {order:[].slice.call(tree.querySelectorAll('.sub-node .s-title'))
                .map(function(x){return x.textContent;}).filter(function(s){return s.indexOf('__t205w_子')>=0;})};
            })()""")
        o = await sub_order()
        ok(not o.get('err') and (o.get('order') or []) == ['__t205w_子1', '__t205w_子2'],
           "②-bis 子事项随「截止」档排序（%s）" % (o or {}).get('order'))
        await ev("toggleCardPin('%s',1)" % ids['__t205w_子2'])
        await asyncio.sleep(2)
        o = await sub_order()
        ok(not o.get('err') and (o.get('order') or [None])[0] == '__t205w_子2',
           "②-bis 子事项置顶浮顶（%s）" % (o or {}).get('order'))
        await ev("toggleCardPin('%s',0)" % ids['__t205w_子2'])
        await set_card_cfg(['created'])
        await asyncio.sleep(1)

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            for cid in ids.values(): api('/api/cards/' + cid, 'DELETE')
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205w')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
