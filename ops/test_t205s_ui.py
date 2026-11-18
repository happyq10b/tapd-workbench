# -*- coding: utf-8 -*-
"""T-205s：事项模块 5 项修改 CDP 实测（2026-11-18）
① 目录「开始」列用真实 begin 字段（非创建时间）；② 自动回填起始周取开始日期；
③ 自动回填勾选移入「周数」标题行（同行不换行）；④ 新建勾选不回显、保存时按日期回填；
⑤ 周数列左对齐 + 两个完整周数 + 父子一致（列宽 204px）。
API 夹具（__t205s_ 前缀）测完即删。"""
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
    # ── 夹具：板块 + 主事项（3 周、begin=2026-11-09=W46 周一）+ 子事项 ──
    col_key = None; card_id = None; sub_id = None
    st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205s_板块',
                                        'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
    if st in (200, 201): col_key = d.get('col_key')
    st3, d3 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205s_跨周事项',
                                        'fields': {'column_name': '__t205s_板块',
                                                   'week_no': '2026年第46周;2026年第47周;2026-48',
                                                   'begin': '2026-11-09', 'due': '2026-11-22'}})
    if st3 in (200, 201): card_id = d3.get('card_id')
    # 确保 begin 落库（若 POST 未落地则 PUT 补）
    if card_id:
        stc, dc = api('/api/cards?card_id=' + card_id)
        row = (dc.get('cards') or [{}])[0]
        if (row.get('begin') or '')[:10] != '2026-11-09':
            api('/api/cards/' + card_id, 'PUT', {'fields': {'begin': '2026-11-09', 'due': '2026-11-22'}})
    sts, ds = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205s_子事项', 'parent_id': card_id,
                                        'fields': {'column_name': '__t205s_板块',
                                                   'week_no': '2026年第46周;2026-47',
                                                   'begin': '2026-11-09', 'due': '2026-11-15'}})
    if sts in (200, 201): sub_id = ds.get('card_id')
    print('fixture:', st, st3, sts, card_id, sub_id, flush=True)

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205s')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--window-size=1600,960',
                      '--remote-debugging-port=9633', '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9633/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9633/json', timeout=5).read())
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

        # 进入看板并展开
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        await ev("expandAll()")
        await asyncio.sleep(2)

        # ── ①+⑤ 主事项行：开始列用 begin；周数列两个完整周数、左对齐、204px ──
        r1 = await ev("""(function(){
          const rows=[].slice.call(document.querySelectorAll('.item-wrap')).filter(function(x){return x.offsetParent!==null;});
          const row=rows.find(function(x){return x.textContent.indexOf('__t205s_跨周事项')>=0;});
          if(!row)return {err:'主事项行不可见'};
          const wk=row.querySelector('.fcol-week_no');
          const bg=row.querySelector('.fcol-created');
          const fc=row.querySelector('.fcols');
          const gcol=getComputedStyle(fc).gridTemplateColumns.split(' ')[0];
          return {begin:bg?bg.textContent.trim():'', week:wk?wk.textContent.trim():'',
                  align:wk?getComputedStyle(wk).textAlign:'', gcol:gcol,
                  wkFull:!/W\\d/.test(wk?wk.textContent:'')};
        })()""")
        ok(r1 and (r1.get('begin') or '') == '开始 2026-11-09',
           "① 目录「开始」列显示事项 begin 字段（实际 %r，非创建时间）" % (r1 or {}).get('begin'))
        ok(r1 and (r1.get('week') or '').startswith('周数 2026年第46周、2026年第47周') and (r1.get('week') or '').endswith('…'),
           "⑤ 周数列 = 两个完整周数 + …（实际 %r）" % (r1 or {}).get('week'))
        ok(r1 and r1.get('align') == 'left' and (r1.get('gcol') or '').startswith('204'),
           "⑤ 周数列左对齐 + 首列 204px（align=%s gcol=%s）" % ((r1 or {}).get('align'), (r1 or {}).get('gcol')))

        # ── ⑤ 子事项行：与父行同格式同列宽 ──
        await ev("toggleSubTree('%s',true)" % card_id)
        await asyncio.sleep(2)
        r1b = await ev("""(function(){
          const nodes=[].slice.call(document.querySelectorAll('.sub-node')).filter(function(x){return x.offsetParent!==null;});
          const node=nodes.find(function(x){return x.textContent.indexOf('__t205s_子事项')>=0;});
          if(!node)return {err:'子事项行不可见'};
          const wk=node.querySelector('.fcol-week_no');
          const bg=node.querySelector('.fcol-created');
          const fc=node.querySelector('.fcols');
          const gcol=getComputedStyle(fc).gridTemplateColumns.split(' ')[0];
          return {begin:bg?bg.textContent.trim():'', week:wk?wk.textContent.trim():'', gcol:gcol};
        })()""")
        ok(r1b and (r1b.get('begin') or '') == '开始 2026-11-09',
           "① 子事项「开始」列同样用 begin（实际 %r）" % (r1b or {}).get('begin'))
        ok(r1b and (r1b.get('week') or '').startswith('周数 2026年第46周、2026年第47周'),
           "⑤ 子事项周数列与父行同格式（实际 %r）" % (r1b or {}).get('week'))
        ok(r1b and (r1b.get('gcol') or '').startswith('204'),
           "⑤ 子事项首列宽与父行一致 204px（实际 %s）" % (r1b or {}).get('gcol'))

        # ── ③ 新建弹窗：勾选与「周数」标题同行、不换行 ──
        await ev("openNewModal('%s')" % BOARD)
        await asyncio.sleep(1.5)
        r3 = await ev("""(function(){
          const g=document.getElementById('n_week_group');
          const lab=g.querySelector('.week-label-row>label');
          const auto=g.querySelector('.week-auto-line');
          if(!lab||!auto)return {err:'结构缺失'};
          const a=lab.getBoundingClientRect(), b=auto.getBoundingClientRect();
          const gr=g.getBoundingClientRect();
          return {sameLine:Math.abs(a.top-b.top)<4, noWrap:auto.scrollWidth<=auto.clientWidth+1,
                   autoRight:b.right<=gr.right+1, gap:Math.round(b.left-a.right)};
        })()""")
        ok(r3 and not r3.get('err') and r3.get('sameLine') and r3.get('noWrap') and r3.get('autoRight'),
           "③ 自动回填勾选在「周数」标题行内、同行不换行不溢出（%s 间距 %spx）" % ((r3 or {}), (r3 or {}).get('gap')))
        ok(r3 and isinstance(r3.get('gap'), int) and 4 <= r3.get('gap') <= 24,
           "③ 按钮与标题保留适当间距（%spx）" % (r3 or {}).get('gap'))

        # ── ④ 新建：勾选不回显；保存时刻按表单日期计算（weekGather('n')） ──
        r4 = await ev("""(function(){
          document.getElementById('n_begin').value='2026-11-09';
          document.getElementById('n_due').value='2026-11-22';
          const cb=document.getElementById('n_week_auto');
          cb.checked=true; cb.dispatchEvent(new Event('change'));
          const inp=document.getElementById('n_week');
          const shown=inp.value;
          const disWhenChecked=inp.disabled;      // 勾选态当场取（取消勾选前）
          const list=weekGather('n');
          cb.checked=false; cb.dispatchEvent(new Event('change'));
          return {shown:shown, disabledWhenChecked:disWhenChecked, list:list,
                  reEnabled:!inp.disabled};
        })()""")
        ok(r4 and (r4.get('shown') or '') == '' and r4.get('disabledWhenChecked') is True,
           "④ 新建勾选自动回填后输入框不立即显示周数（实际 %r）" % (r4 or {}).get('shown'))
        ok(r4 and (r4.get('list') or []) == ['2026年第46周', '2026年第47周'],
           "④ 保存时刻按开始～截止日期回填（%s，起始取开始日期）" % (r4 or {}).get('list'))
        ok(r4 and r4.get('reEnabled') is True, "④ 取消勾选后输入框恢复可用")
        await ev("closeModal('newModal')")
        await asyncio.sleep(0.5)

        # ── ② 编辑弹窗：自动回填预览按开始日期（而非创建日期/今天） ──
        r2 = await ev("""(async function(){
          await openEdit('%s');
          await new Promise(function(r){setTimeout(r,1200);});
          const cb=document.getElementById('e_week_auto');
          cb.checked=true; cb.dispatchEvent(new Event('change'));
          const v1=document.getElementById('e_week').value;
          // 改开始日期 → 预览跟随
          const bg=document.getElementById('e_begin');
          bg.value='2026-11-16'; bg.dispatchEvent(new Event('input'));
          const v2=document.getElementById('e_week').value;
          const list=weekGather('e');
          cb.checked=false; cb.dispatchEvent(new Event('change'));
          return {v1:v1, v2:v2, list:list};
        })()""" % card_id, aw=True)
        ok(r2 and (r2.get('v1') or '') == '2026年第46周、2026年第47周',
           "② 编辑自动回填预览按开始日期计算（实际 %r，若按创建日期会是今天所在 W47）" % (r2 or {}).get('v1'))
        ok(r2 and (r2.get('v2') or '') == '2026年第47周',
           "② 开始日期变更后预览跟随（实际 %r）" % (r2 or {}).get('v2'))
        ok(r2 and (r2.get('list') or []) == ['2026年第47周'],
           "② 保存时收集口径 = 开始日期起算（%s）" % (r2 or {}).get('list'))
        await ev("document.querySelectorAll('.modal-overlay').forEach(function(m){m.style.display='none';})")
        await asyncio.sleep(0.5)

        # ── ②-bis 后端默认周口径：清空周数 → 回落开始日期所在周 ──
        stp, dp = api('/api/cards/' + card_id, 'PUT', {'fields': {'week_no': ''}})
        stq, dq = api('/api/cards?card_id=' + card_id)
        wq = ((dq.get('cards') or [{}])[0].get('week_no') or '')
        ok(stp == 200 and wq == '2026年第46周',
           "② 后端周数清空回落 = 开始日期所在周（实际 %r）" % wq)

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            if sub_id: api('/api/cards/' + sub_id, 'DELETE')
            if card_id: api('/api/cards/' + card_id, 'DELETE')
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205s')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
