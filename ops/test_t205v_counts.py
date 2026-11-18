# -*- coding: utf-8 -*-
"""T-205v：筛选下拉选项计数（#205v 2026-11-18）CDP 实测
状态/性质下拉每个选项行右侧追加当前筛选范围内的板块数量（分面统计）；
数字与 /api/cards cols 载荷分布一致、随另一维度筛选联动刷新、布局/筛选逻辑不受影响。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error

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
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

CS = ['notstarted', 'progressing', 'done', 'open']
CS_LBL = {'notstarted': '未开始', 'progressing': '进行中', 'done': '已完成', 'open': '未完成'}

def dist(rows, key, dim=None, val=None):
    """cols 载荷分布：dim/val 给定时先按另一维度过滤"""
    out = {}
    for r in rows:
        if dim and (r.get(dim) or ('nature' == dim and '日常')) != val: continue
        k = r.get(key) or ('completion' if key == 'completion' else '日常')
        out[k] = out.get(k, 0) + 1
    return out

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205v')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                      '--remote-debugging-port=9649', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9649/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9649/json', timeout=5).read())
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
        # API 口径基准（当前看板 cols 载荷）
        stq, dq = api('/api/cards?board_id=' + BOARD + '&size=1')
        rows = dq.get('columns') or []
        stq == 200 or ok(False, 'API 口径获取失败')

        async def read_drop(drop_id):
            return await ev("""(function(){
              const drop=document.getElementById('%s');
              if(!drop||drop.hidden)return {err:'下拉未展开'};
              return {rows:[].slice.call(drop.querySelectorAll('.cf-opt')).map(function(x){
                const c=x.querySelector('.opt-count');
                const r=x.getBoundingClientRect(), dr=drop.getBoundingClientRect();
                return {label:x.querySelector('span').textContent.trim(),
                        count:c?c.textContent.trim():null,
                        inPanel:c?(dr.right-8)>=c.getBoundingClientRect().right:false};
              })};
            })()""" % drop_id)

        # ── ① 状态下拉：无筛选时计数 = 全板块按 completion 分布 ──
        await ev("toggleColStatusDrop()")
        await asyncio.sleep(0.5)
        r1 = await read_drop('colStatusDrop')
        exp1 = dist(rows, 'completion')
        ok(r1 and not r1.get('err') and all(r.get('count') is not None for r in r1.get('rows', [])),
           "① 状态下拉每个选项都带计数（%s）" % [(r.get('label'), r.get('count')) for r in (r1 or {}).get('rows', [])])
        got1 = {r['label']: int(r['count']) for r in (r1 or {}).get('rows', []) if r.get('count') is not None}
        exp1_full = {CS_LBL[k]: exp1.get(k, 0) for k in CS}   # 无该状态的选项显示 0
        ok(got1 == exp1_full, "① 无筛选时状态计数与载荷分布一致（%s vs %s）" % (got1, exp1_full))
        ok(r1 and all(r.get('inPanel') for r in r1.get('rows', [])),
           "① 计数右对齐在面板内不出界")
        # 筛选逻辑不受影响：点「未完成」行 → 板块行只剩 open
        await ev("toggleColStatusPick('open')")
        await asyncio.sleep(2)
        vis = await ev("[].slice.call(document.querySelectorAll('.week-title')).filter(function(x){return x.offsetParent!==null;}).length")
        ok(vis == exp1.get('open', 0), "① 筛选逻辑不受影响：选「未完成」→ 可见板块数 = 计数 %s（实际 %s）" % (exp1.get('open', 0), vis))
        await ev("toggleColStatusPick('open');closeColStatusDrop()")
        await asyncio.sleep(1)

        # ── ② 性质下拉：无筛选时计数 = 全板块按 nature 分布 ──
        await ev("toggleAttrDrop()")
        await asyncio.sleep(0.5)
        r2 = await read_drop('attrFilterDrop')
        exp2 = dist(rows, 'nature')
        got2 = {r['label']: int(r['count']) for r in (r2 or {}).get('rows', []) if r.get('count') is not None}
        ok(got2 == {'专项': exp2.get('专项', 0), '日常': exp2.get('日常', 0)},
           "② 性质下拉计数与载荷分布一致（%s vs %s）" % (got2, exp2))
        await ev("closeAttrDrop()")
        await asyncio.sleep(0.5)

        # ── ③ 分面联动：勾「日常」性质 → 状态计数只统计日常板块 ──
        await ev("toggleAttrPick('日常')")
        await asyncio.sleep(2)
        await ev("toggleColStatusDrop()")
        await asyncio.sleep(0.5)
        r3 = await read_drop('colStatusDrop')
        exp3 = dist(rows, 'completion', dim='nature', val='日常')
        got3 = {r['label']: int(r['count']) for r in (r3 or {}).get('rows', []) if r.get('count') is not None}
        ok(got3 == {CS_LBL[k]: exp3.get(k, 0) for k in CS},
           "③ 勾「日常」后状态计数只统计日常板块（%s vs %s）" % (got3, exp3))
        await ev("closeColStatusDrop()")
        # 性质自身勾选不清零（排除自身维度）：勾选后仍显示全量性质分布
        await ev("toggleColStatusDrop();closeColStatusDrop()")
        r3b = await ev("(function(){toggleAttrDrop();const d=document.getElementById('attrFilterDrop');"
                       "return [].slice.call(d.querySelectorAll('.cf-opt')).map(function(x){return x.querySelector('.opt-count').textContent;});})()")
        ok(r3b == [str(exp2.get('专项', 0)), str(exp2.get('日常', 0))],
           "③ 性质自身已选不把自己的计数清零（%s）" % r3b)
        await ev("closeAttrDrop();toggleAttrPick('日常')")
        await asyncio.sleep(1.5)

        # ── ③-bis 勾「进行中」状态 → 性质计数只统计进行中板块 ──
        await ev("toggleColStatusPick('progressing')")
        await asyncio.sleep(2)
        await ev("toggleAttrDrop()")
        await asyncio.sleep(0.5)
        r4 = await read_drop('attrFilterDrop')
        exp4 = dist(rows, 'nature', dim='completion', val='progressing')
        got4 = {r['label']: int(r['count']) for r in (r4 or {}).get('rows', []) if r.get('count') is not None}
        ok(got4 == {'专项': exp4.get('专项', 0), '日常': exp4.get('日常', 0)},
           "③-bis 勾「进行中」后性质计数只统计进行中板块（%s vs %s）" % (got4, exp4))
        await ev("closeAttrDrop();toggleColStatusPick('progressing')")
        await asyncio.sleep(1.5)

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205v')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
