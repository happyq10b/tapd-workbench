# -*- coding: utf-8 -*-
"""T-205aa：负责人/参与人选人树追加板块数量计数 CDP 实测（2026-11-18）
负责人/参与人选人树每个人员行右侧追加「当前筛选范围内该人员担任负责人/参与人的板块数」
（样式与逻辑参照 #205v 状态/性质下拉的 .opt-count）。
① 计数与 /api/cards cols 载荷分布一致（含「无负责人」行）；
② 分面联动：计入年份/状态/性质/**另一人员维度**的已选，排除自身维度；
③ 徽标右对齐在面板内、其他 openTreePick 使用方不受影响。
API 夹具（__t205aa_ 前缀）测完即删。"""
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

def expected_counts(rows, exclude_dim='', status_sel=None, cc_sel_names=None, person_sel_names=None):
    """Python 侧按前端同款分面口径计算期望计数（owner: {姓名:n, '__no_owner__':n} / cc: {姓名:n}）"""
    out = {}
    for m in rows:
        if status_sel and (m.get('completion') or 'open') not in status_sel: continue
        # 另一人员维度计入（排除自身维度由调用方控制 exclude_dim）
        if exclude_dim != 'person' and person_sel_names:
            names = [a.strip() for a in String_owner_accounts(m)]
            hit = False
            for v in person_sel_names:
                if v in names: hit = True
            if not hit: continue
        if exclude_dim != 'cc' and cc_sel_names:
            accts = [a.strip() for a in (m.get('participants') or '').split(',') if a.strip()]
            if not any(v in accts for v in cc_sel_names): continue
        if exclude_dim == 'cc':
            for a in [a.strip() for a in (m.get('participants') or '').split(',') if a.strip()]:
                nm = ACC2NAME.get(a, a)
                out[nm] = out.get(nm, 0) + 1
        else:  # owner 维度
            o = (m.get('owner') or '').strip()
            if not o:
                out['__no_owner__'] = out.get('__no_owner__', 0) + 1
                continue
            nm = ACC2NAME.get(o, o)
            out[nm] = out.get(nm, 0) + 1
    return out

def String_owner_accounts(m):
    return [(m.get('owner') or '').split(',')]

ACC2NAME = {}

async def main():
    import websockets
    # ── 夹具：甲（负责人=hly+参与人=hqx）乙（无负责人+参与人=hqx）丙（负责人=hly）──
    stq, dq = api('/api/team')
    for m in (dq.get('members') or []):
        if m.get('account') in ('hly', 'hqx'):
            ACC2NAME[m['account']] = m.get('name') or m['account']
    NAME_HLY, NAME_HQX = ACC2NAME.get('hly', 'hly'), ACC2NAME.get('hqx', 'hqx')
    keys, cids = {}, []
    for name, owner, parts in [('__t205aa_甲', 'hly', 'hqx'), ('__t205aa_乙', '', 'hqx'), ('__t205aa_丙', 'hly', '')]:
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': name,
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18',
                                            'owner': owner, 'participants': parts})
        if st in (200, 201): keys[name] = d.get('col_key')
        stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': name + '内事项',
                                            'fields': {'column_name': name}})
        if stc in (200, 201): cids.append(dc.get('card_id'))
    stv, dv = api('/api/cards?board_id=' + BOARD + '&size=500')
    rows_all = dv.get('columns') or []
    fx = {c['column_name']: c for c in rows_all if c['column_name'].startswith('__t205aa_')}
    print('fixture:', keys, ACC2NAME, [(k, r.get('owner'), r.get('participants'))
          for k, r in sorted(fx.items())], flush=True)
    ok(len(keys) == 3 and len(fx) == 3
       and (fx['__t205aa_甲'].get('owner') == 'hly' and fx['__t205aa_甲'].get('participants') == 'hqx')
       and (not (fx['__t205aa_乙'].get('owner') or '').strip() and fx['__t205aa_乙'].get('participants') == 'hqx')
       and fx['__t205aa_丙'].get('owner') == 'hly',
       '夹具 3 板块 owner/participants 落库正确')

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205aa')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                      '--remote-debugging-port=9655', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9655/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9655/json', timeout=5).read())
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
        await asyncio.sleep(3)

        async def open_owner_picker():
            await ev("closeTreePick();openPersonFilterPicker(document.getElementById('personFilterInput'))")
            for _ in range(30):
                await asyncio.sleep(0.4)
                if await ev("!!document.querySelector('.tree-pick')") is True: break
            await asyncio.sleep(1)
            return await read_people()

        async def open_cc_picker():
            await ev("closeTreePick();openCcFilterPicker(document.getElementById('ccFilterInput'))")
            for _ in range(30):
                await asyncio.sleep(0.4)
                if await ev("!!document.querySelector('.tree-pick')") is True: break
            await asyncio.sleep(1)
            return await read_people()

        async def read_people():
            return await ev("""(function(){
              const p=document.querySelector('.tree-pick');
              if(!p)return {err:'面板未打开'};
              const pr=p.getBoundingClientRect();
              const rows=[].slice.call(p.querySelectorAll('.tp-node.tp-person')).map(function(row){
                const box=row.querySelector('[data-pbox]');
                const c=row.querySelector('.tp-cnt');
                const cr=c?c.getBoundingClientRect():null;
                return {name:box?box.getAttribute('data-pbox'):null,
                        count:c?c.textContent.trim():null,
                        inPanel:cr?(pr.right-8)>=cr.right&&cr.left>=pr.left:false};
              });
              const nn=p.querySelector('.tp-none-node .tp-cnt');
              return {rows:rows, none:nn?nn.textContent.trim():null};
            })()""")

        def close_and(label, cond, detail=''):
            ok(label and not label.get('__error__') and cond, detail)

        # ── ① 负责人树：每个人员行带计数，数字 = 载荷分布（含夹具 3 板块）──
        # 候选 = colOwnerNames()（有负责板块的人才出现）→ 何巧娴（夹具中只参与不负责）
        # 在负责人树里没有行，属既有口径，非缺陷。
        exp_owner = expected_counts(rows_all)
        r1 = await open_owner_picker()
        got1 = {r['name']: int(r['count']) for r in (r1 or {}).get('rows', []) if r.get('count') is not None}
        close_and(r1, got1.get(NAME_HLY) == exp_owner.get(NAME_HLY, 0) and NAME_HQX not in got1,
                  "① 负责人树计数与载荷分布一致：何兰英=%s（期望 %s）；何巧娴无负责板块 → 无行（%s）"
                  % (got1.get(NAME_HLY), exp_owner.get(NAME_HLY, 0), '不在树中' if NAME_HQX not in got1 else got1.get(NAME_HQX)))
        # 夹具使何兰英至少 +2（甲/丙）、参与人树里何巧娴 +2（甲/乙）
        close_and(r1, got1.get(NAME_HLY, 0) >= 2,
                  "① 夹具生效：何兰英计数 ≥ 2（实际 %s）" % got1.get(NAME_HLY))
        close_and(r1, all(r.get('inPanel') for r in (r1 or {}).get('rows', []) if r.get('count') is not None),
                  "① 计数徽标右对齐在面板内不出界")
        ok(got1 != {} and (r1 or {}).get('rows'), "① 负责人树每个人员行都带计数徽标")

        # ── ② 「无负责人」行计数 = 负责人为空的板块数 ──
        await ev("tpToggleNoneOwner()")
        await asyncio.sleep(0.5)
        r2 = await ev("""(function(){const p=document.querySelector('.tree-pick');
              const nn=p&&p.querySelector('.tp-none-node .tp-cnt');
              return nn?nn.textContent.trim():null;})()""")
        ok(r2 is not None and int(r2) == exp_owner.get('__no_owner__', 0),
           "② 「无负责人」行计数 = 负责人为空的板块数（实际 %s / 期望 %s）" % (r2, exp_owner.get('__no_owner__', 0)))
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)

        # ── ③ 参与人树：何巧娴计数 = 其参与的板块数（夹具甲乙 → ≥2）──
        exp_cc = expected_counts(rows_all, exclude_dim='cc')
        r3 = await open_cc_picker()
        got3 = {r['name']: int(r['count']) for r in (r3 or {}).get('rows', []) if r.get('count') is not None}
        close_and(r3, got3.get(NAME_HQX) == exp_cc.get(NAME_HQX, 0) and got3.get(NAME_HQX, 0) >= 2,
                  "③ 参与人树计数与载荷分布一致：何巧娴=%s（期望 %s）" % (got3.get(NAME_HQX), exp_cc.get(NAME_HQX, 0)))
        ok(r3 is not None and not r3.get('none'), "③ 参与人树无「无负责人」节点行（该弹窗不提供该选项）")
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)

        # ── ④ 分面联动：勾状态「进行中」→ 负责人计数只统计进行中板块 ──
        await ev("COL_STATUS_SEL=new Set(['progressing']);paintColStatus();reload(1)")
        await asyncio.sleep(2.5)
        stv2, dv2 = api('/api/cards?board_id=' + BOARD + '&size=500')
        rows_prog = [m for m in (dv2.get('columns') or []) if (m.get('completion') or 'open') == 'progressing']
        exp4 = expected_counts(dv2.get('columns') or [])
        r4 = await open_owner_picker()
        got4 = {r['name']: int(r['count']) for r in (r4 or {}).get('rows', []) if r.get('count') is not None}
        close_and(r4, got4.get(NAME_HLY) == exp4.get(NAME_HLY, 0) and NAME_HQX not in got4,
                  "④ 勾「进行中」后负责人计数只统计进行中板块（何兰英 %s，期望 %s；进行中板块 %d 个）"
                  % (got4.get(NAME_HLY), exp4.get(NAME_HLY, 0), len(rows_prog)))
        await ev("closeTreePick();COL_STATUS_SEL=new Set();paintColStatus();reload(1)")
        await asyncio.sleep(2)

        # ── ⑤ 排除自身维度：勾选「何兰英」为负责人筛选后，她自己计数不清零 ──
        await ev("PERSON_SEL=new Set([%s]);paintFilterCombos();reload(1)" % json.dumps(NAME_HLY, ensure_ascii=False))
        await asyncio.sleep(2.5)
        exp5 = expected_counts(rows_all, person_sel_names=[])  # 自身维度排除 → 基线不变
        r5 = await open_owner_picker()
        got5 = {r['name']: int(r['count']) for r in (r5 or {}).get('rows', []) if r.get('count') is not None}
        close_and(r5, got5.get(NAME_HLY) == exp5.get(NAME_HLY, 0) and got5.get(NAME_HLY, 0) > 0,
                  "⑤ 自身已选不清零：已选「何兰英」后她的计数仍 %s（期望 %s）" % (got5.get(NAME_HLY), exp5.get(NAME_HLY, 0)))
        await ev("closeTreePick()")

        # ── ⑥ 计入另一人员维度：参与人已选「何巧娴」→ 负责人计数只统计 hqx 参与的板块 ──
        await ev("PERSON_SEL=new Set();CC_SEL=new Set([%s]);paintFilterCombos();reload(1)" % json.dumps(NAME_HQX, ensure_ascii=False))
        await asyncio.sleep(2.5)
        exp6 = expected_counts(rows_all, cc_sel_names=['hqx'])
        r6 = await open_owner_picker()
        got6 = {r['name']: int(r['count']) for r in (r6 or {}).get('rows', []) if r.get('count') is not None}
        close_and(r6, got6.get(NAME_HLY) == exp6.get(NAME_HLY, 0),
                  "⑥ 参与人已选「何巧娴」后负责人计数=其参与的板块数：何兰英 %s（期望 %s，= 夹具甲 1 个）"
                  % (got6.get(NAME_HLY), exp6.get(NAME_HLY, 0)))
        # 参与人自身维度排除：参与人树里何巧娴计数不清零
        r6b = await open_cc_picker()
        got6b = {r['name']: int(r['count']) for r in (r6b or {}).get('rows', []) if r.get('count') is not None}
        exp6b = expected_counts(rows_all, exclude_dim='cc')   # 自身维度排除 → 参与人基线不变
        close_and(r6b, got6b.get(NAME_HQX) == exp6b.get(NAME_HQX, 0),
                  "⑥-bis 参与人树自身已选不清零：何巧娴仍 %s（期望 %s）" % (got6b.get(NAME_HQX), exp6b.get(NAME_HQX, 0)))
        await ev("closeTreePick();PERSON_SEL=new Set();CC_SEL=new Set();paintFilterCombos();reload(1)")
        await asyncio.sleep(1.5)

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            for cid in cids:
                if cid: api('/api/cards/' + cid, 'DELETE')
            for k in keys.values():
                api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205aa')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
