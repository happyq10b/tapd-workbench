# -*- coding: utf-8 -*-
"""T-205p 周数多选/自动回填/列表多周展示 CDP 实测（零写库 DOM 注入 + API 夹具）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error, urllib.parse

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'   # 综合工作事项（真实看板）
_okN = _failN = 0
def ok(cond, msg):
    global _okN, _failN
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if cond: _okN += 1
    else: _failN += 1

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + make_token('admin'))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=25, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205p')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9625',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9625/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    col_name = '__t205p_周数板块'
    card_id = None
    col_key = None
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9625/json', timeout=5).read())
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
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)

        # ── API 夹具：建板块 + 一张跨多周事项（测完即删）──
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': col_name,
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
        assert st in (200, 201), d
        col_key = d.get('col_key')
        st3, d3 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205p_跨周事项',
                                            'fields': {'column_name': col_name,
                                                       'week_no': '2026年第47周;2026年第46周;2026-48',
                                                       'nature': '日常', 'created': '2026-11-18'}})
        assert st3 in (200, 201), d3
        card_id = d3.get('card_id')

        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        await ev("expandAll()")   # 展开全部板块（新板块默认折叠，行宽测量需要可见）
        await asyncio.sleep(2)

        # ── ② API 落库：多周归一（去重+升序+「2026-48」→标准标签）──
        st4, d4 = api('/api/cards?card_id=' + card_id)
        row = (d4.get('cards') or [{}])[0]
        ok(st4 == 200 and row.get('week_no') == '2026年第46周;2026年第47周;2026年第48周',
           "② API 直传乱序+简写周数 → 落库归一升序「;」连接（实际 %r）" % row.get('week_no'))

        # ── ④ 列表展示：多周 → 只显示最早一周 +「…」，悬停提示全部，列宽加宽，父/子同规则 ──
        r5 = await ev("""(function(){
          const row=[].slice.call(document.querySelectorAll('.item-wrap .fcols[style]'))
            .find(function(x){return x.offsetParent!==null;});
          if(!row)return {err:'无动态列宽行'};
          const wk=row.querySelector('.fcol-week_no');
          const st=getComputedStyle(row);
          return {style:row.getAttribute('style'),
                  text:wk.textContent.trim(),
                  tip:wk.getAttribute('title')||'',
                  width:Math.round(row.getBoundingClientRect().width)};
        })()""")
        # #205r 口径更新：目录周数列展示最早 2 周（+…仅当 >2 周）；列宽 2 周 128 / ≥3 周 144
        ok(r5 and not r5.get('err') and (r5.get('text') or '').replace('周数 ', '').startswith('2026·W46、2026·W47')
           and (r5.get('text') or '').endswith('…'),
           "④ 父事项周数列显最早 2 周+「…」（#205r 口径，实际 %r）" % (r5 or {}).get('text'))
        ok(r5 and 'W47' in (r5.get('tip') or '') and 'W48' in (r5.get('tip') or ''),
           "④ 悬停提示含全部周数（%r）" % (r5 or {}).get('tip'))
        ok(r5 and (r5.get('width') or 0) >= 574,
           "④ 多周行 fcols 加宽（%spx ≥ 574px = 144+398列+32间距，#205r 口径，标题随之压缩）" % r5.get('width'))
        # 子事项：建一张子事项带多周 → 同规则
        st5, d5 = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t205p_子事项',
                                            'parent_id': card_id,
                                            'fields': {'column_name': col_name, 'week_no': '2026年第2周;2026-3',
                                                       'nature': '日常', 'created': '2026-11-18'}})
        if st5 not in (200, 201):
            print('   子事项创建失败:', st5, json.dumps(d5, ensure_ascii=False)[:160], flush=True)
        sub_id = d5.get('card_id') if st5 in (200, 201) else None
        await asyncio.sleep(2)
        await ev("toggleSubTree('%s')" % card_id)   # 展开父事项的子事项目录
        await asyncio.sleep(2)
        r5b = await ev("""(function(){
          const sub=[].slice.call(document.querySelectorAll('.sub-node .fcols[style]'))
            .find(function(x){return x.offsetParent!==null;});
          if(!sub)return {err:'子事项无动态列宽',
                          subsN:document.querySelectorAll('.sub-node').length};
          const wk=sub.querySelector('.fcol-week_no');
          return {text:wk.textContent.trim(), tip:wk.getAttribute('title')||''};
        })()""")
        # #205r 口径：2 周全显、无 …（>2 周才收尾省略）
        ok(r5b and not r5b.get('err') and (r5b.get('text') or '').replace('周数 ', '').startswith('2026·W2、2026·W3')
           and not (r5b.get('text') or '').endswith('…'),
           "④-bis 子事项周数列同规则（2 周全显无…，实际 %r）" % (r5b or {}).get('text'))
        # 清理子事项
        if sub_id: api('/api/cards/' + sub_id, 'DELETE')

        # ── ①③ 新建弹窗：下拉显示全年全部周数 + 多选勾选 + 自动回填 ──
        r6 = await ev("""(function(){
          openNewModal();
          return {opened:!!document.getElementById('newModal')};
        })()""")
        await asyncio.sleep(0.5)
        r7 = await ev("""(function(){
          openWeekCombo('n');
          const drop=document.getElementById('n_week_drop');
          const opts=drop.querySelectorAll('[data-wk-pick]');
          return {open:!drop.hidden, n:opts.length,
                  first:opts.length?opts[0].getAttribute('data-wk-pick'):'',
                  hasCheckbox:opts.length?!!opts[0].querySelector('input[type=checkbox]'):false,
                  inpVal:document.getElementById('n_week').value};
        })()""")
        ok(r7 and r7.get('open') and (r7.get('n') or 0) >= 52,
           "① 新建弹窗周数下拉显示全年全部周数（%s 项 ≥52）" % r7.get('n'))
        ok(r7 and r7.get('hasCheckbox') and r7.get('inpVal'),
           "①-bis 选项为 checkbox、输入框预填当前周（%r）" % r7.get('inpVal'))
        # 勾选另外两周（面板保持打开）
        r8 = await ev("""(function(){
          const drop=document.getElementById('n_week_drop');
          const picks=['2026年第2周','2026年第5周'];
          picks.forEach(function(wk){
            const lab=[].slice.call(drop.querySelectorAll('[data-wk-pick]'))
              .find(function(x){return x.getAttribute('data-wk-pick')===wk;});
            const cb=lab.querySelector('input[type=checkbox]');
            cb.click();
          });
          return {dropStillOpen:!drop.hidden, selN:N_WEEK_SEL.size,
                  inpVal:document.getElementById('n_week').value,
                  checkedN:drop.querySelectorAll('input:checked').length};
        })()""")
        ok(r8 and r8.get('dropStillOpen') and r8.get('selN') == 3,
           "② UI 勾选多周：面板保持打开、选中集 3 项（勾选框 %s 个）" % r8.get('checkedN'))
        ok(r8 and '2026年第2周' in (r8.get('inpVal') or '') and '2026年第5周' in (r8.get('inpVal') or ''),
           "②-bis 输入框显示多周「、」连接（%r）" % r8.get('inpVal'))
        # 自动回填：勾选 → 输入框禁用+按创建~截止计算
        r9 = await ev("""(function(){
          const cbx=document.getElementById('n_week_auto');
          cbx.checked=true;onWeekAutoToggle('n');
          const inp=document.getElementById('n_week');
          const before={disabled:inp.disabled, val:inp.value};
          // 改截止日期 → 自动重算
          document.getElementById('n_due').value='2027-01-15';
          weekAutoRefresh('n');
          const after={val:inp.value};
          cbx.checked=false;onWeekAutoToggle('n');
          return {before:before, after:after, reEnabled:!inp.disabled};
        })()""")
        ok(r9 and r9.get('before', {}).get('disabled') and (r9.get('before', {}).get('val') or '').startswith('2026年第'),
           "③ 勾选自动回填 → 手动选择禁用、按创建~截止回填（%r）" % r9.get('before', {}).get('val'))
        ok(r9 and '2027年第' in (r9.get('after', {}).get('val') or ''),
           "③-bis 截止日期跨年 → 回填覆盖 2027 年周（%r）" % r9.get('after', {}).get('val'))
        ok(r9 and r9.get('reEnabled'), "③-ter 取消勾选 → 手动选择恢复可用")
        # 关闭弹窗
        await ev("closeModal('newModal')")
        await asyncio.sleep(0.5)

        # ── ①-bis 编辑场景：下拉显示全部周数（旧 bug：输入值过滤后只剩 1 项）──
        rA = await ev("""(async function(){
          openEdit('%s');
          await new Promise(function(r){setTimeout(r,800);});
          openWeekCombo('e');
          const drop=document.getElementById('e_week_drop');
          return {n:drop.querySelectorAll('[data-wk-pick]').length,
                  inpVal:document.getElementById('e_week').value};
        })()""" % card_id, aw=True)
        ok(rA and (rA.get('n') or 0) >= 52,
           "①-ter 编辑弹窗周数下拉同样显示全年全部周数（%s 项）" % rA.get('n'))
        ok(rA and '、' in (rA.get('inpVal') or ''),
           "①-ter-bis 编辑回显多周「、」连接（%r）" % rA.get('inpVal'))
        await ev("closeEdit()")

    finally:
        # 清理夹具
        try:
            if card_id: api('/api/cards/' + card_id, 'DELETE')
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception: pass
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205p')
        shutil.rmtree(profile, ignore_errors=True)

    print('---- 结果: %d PASS / %d FAIL ----' % (_okN, _failN), flush=True)

asyncio.run(main())
