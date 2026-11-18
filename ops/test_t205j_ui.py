# -*- coding: utf-8 -*-
"""T-205j 界面改动 CDP 实测（零写库，只读真实数据）：
① 板块预览（截图区域）：参与人名单单行 + 末尾「…」截断（m1l 类生效）
② 事项预览：负责人名单 m1l 同款
③ 筛选栏：新「🏷️ 专项/日常」框位于状态与负责人之间；选日常→只显日常板块；
   选专项→只显专项板块；计数徽标；清空恢复；筛选明细行文案
④ 宽度压缩断言：常规筛选框宽度 ≈138px（167→138 ≈ 1/5）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = '1162069797001000238'   # 综合工作事项（测试）：参与人名单 70+ 人（最坏样本）

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205j')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9621',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9621/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    w = None
    ok_n = fail_n = 0
    def ok(cond, msg):
        nonlocal ok_n, fail_n
        print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
        if cond: ok_n += 1
        else: fail_n += 1
    try:
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9621/json', timeout=5).read())
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
        await ev('''window.__errs=[];window.onerror=function(m,s,l,c){window.__errs.push(m+'@'+l+':'+c);return false};''')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)

        # ── ③ 前置：进入测试看板 ──
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        # ③ 新框位置与结构
        r0 = await ev("""(function(){
          const ids=['colStatusWrap','attrFilterWrap','personFilterWrap','ccFilterWrap','yearFilter','weekFilterWrap'];
          const order=ids.map(id=>document.getElementById(id)).filter(Boolean)
            .map(el=>el.getBoundingClientRect());
          const af=document.getElementById('attrFilterWrap');
          if(!af)return {err:'attrFilterWrap 不存在'};
          const ar=af.getBoundingClientRect();
          const st=document.getElementById('colStatusWrap').getBoundingClientRect();
          const pr=document.getElementById('personFilterWrap').getBoundingClientRect();
          const lbl=af.querySelector('.cf-label');
          return {afterStatus:ar.left>=st.right-2, beforePerson:ar.right<=pr.left+2,
                  lblText:lbl.textContent.trim(),
                  w:Math.round(ar.width),
                  wStatus:Math.round(st.width), wPerson:Math.round(pr.width),
                  drop:!!document.getElementById('attrFilterDrop')};
        })()""")
        ok(r0 and r0.get('afterStatus') and r0.get('beforePerson'),
           "③ 新框位于【状态】与【负责人】之间（left≥状态右缘、right≤负责人左缘）")
        ok(r0 and '🏷️' in (r0.get('lblText') or '') and '专项/日常' in (r0.get('lblText') or ''),
           "③ label = 一个 emoji +「专项/日常」（实际：%r）" % (r0 or {}).get('lblText'))
        ws_ = (r0 or {}).get('wStatus'); wp = (r0 or {}).get('wPerson')
        ok(ws_ and wp and 120 <= ws_ <= 155 and 120 <= wp <= 155,
           "④ 常规筛选框压缩后 ≈138px（状态 %s / 负责人 %s，原 167 ≈ −1/5）" % (ws_, wp))

        # ③ 选「日常」→ 板块行只剩日常看板的板块
        await ev("toggleAttrPick('日常')")
        # 轮询等待 reload→renderBoard 完成（COLS_META 重建非空）
        for _ in range(20):
            await asyncio.sleep(0.5)
            if await ev("(window.COLS_META||[]).length>0") is True: break
        await asyncio.sleep(1)
        r1 = await ev("""(function(){
          const attrs=Array.from(new Set((window.COLS_META||[]).map(x=>x.attr||'')));
          return {selN:ATTR_SEL.size, attrsInCols:attrs,
                  active:document.getElementById('attrFilterWrap').classList.contains('active'),
                  count:(document.getElementById('attrFilterCount')||{}).textContent||''};
        })()""")
        ok(r1 and r1.get('selN') == 1 and (r1.get('attrsInCols') or []) == ['日常'],
           "③ 选「日常」→ 渲染的板块全部来自日常看板（cols attr=%s，计数=%r）"
           % (r1.get('attrsInCols'), r1.get('count')))
        # 切「专项」→ 空态
        await ev("ATTR_SEL=new Set(['专项']);paintAttr();reload(1);")
        await asyncio.sleep(2)
        r2 = await ev("""(function(){
          const emp=document.querySelector('#boardContent .empty');
          return {empty:emp?emp.textContent.trim():'', n:(window.COLS_META||[]).length};
        })()""")
        ok(r2 and '性质' in (r2.get('empty') or ''),
           "③ 选「专项」（该看板全为日常）→ 空态提示「没有符合性质条件的板块」（实际：%r）"
           % (r2 or {}).get('empty'))
        # 清空恢复 + 明细行文案
        await ev("clearAllRowFilters()")
        await asyncio.sleep(2)
        r3 = await ev("""(function(){
          return {selN:ATTR_SEL.size, hint:(document.getElementById('filterHint')||{}).textContent||''};
        })()""")
        ok(r3 and r3.get('selN') == 0, "③ 清空筛选后 ATTR_SEL 复位")
        # 明细行文案：勾一个性质看 hint
        await ev("toggleAttrPick('专项');")
        await asyncio.sleep(1.5)
        r4 = await ev("""(function(){
          const h=(document.getElementById('filterHint')||{}).textContent||'';
          ATTR_SEL.clear();paintAttr();reload(1);
          return {hint:h};
        })()""")
        ok(r4 and '专项/日常：专项' in (r4.get('hint') or ''),
           "③ 筛选明细行含「专项/日常：专项」（实际：%r）" % ((r4 or {}).get('hint')))

        # ── ① 板块预览：参与人单行省略 ──
        # 先恢复全池并等待重绘完成（r4 里 reload 未等待 → 页面可能仍是空态无 .week-title）
        await ev("ATTR_SEL.clear();paintAttr();reload(1);")
        await asyncio.sleep(2.5)
        r5 = await ev("""(async function(){
          const el=document.querySelector('.week-title');
          if(!el)return {err:'无板块标题'};
          await openColumnDetail(el);
          return {col:(el.dataset.colkey||'').split('::')[1]||el.textContent.trim(),
                  metaLen:document.getElementById('cd_meta').innerHTML.length};
        })()""", aw=True)
        print('① 打开板块预览:', json.dumps(r5, ensure_ascii=False), flush=True)
        r6 = await ev("""(function(){
          const m=document.getElementById('cd_meta');
          if(!m)return {err:'cd_meta 不存在'};
          if(!m.innerHTML.trim())return {err:'cd_meta 空', errs:window.__errs||[]};
          const spans=[].slice.call(m.querySelectorAll('.m1l'));
          if(!spans.length)return {err:'无 .m1l', head:m.innerHTML.slice(0,160), errs:window.__errs||[]};
          const s=spans[0];
          const st=getComputedStyle(s);
          return {n:spans.length, textLen:s.textContent.length,
                  nowrap:st.whiteSpace==='nowrap', ellipsis:st.textOverflow==='ellipsis',
                  h:Math.round(s.getBoundingClientRect().height),
                  clipped:s.scrollWidth>s.clientWidth};
        })()""")
        ok(r6 and not r6.get('err') and r6.get('nowrap') and r6.get('ellipsis'),
           "① 板块预览参与人 .m1l：nowrap+ellipsis 生效（%s）" % json.dumps(r6, ensure_ascii=False))
        # 若该板块参与人足够多 → 应真的截断（单行高度 + 溢出）
        if r6 and not r6.get('err') and (r6.get('textLen') or 0) > 60:
            ok(r6.get('h', 0) <= 30 and r6.get('clamped') is not False and r6.get('clipped'),
               "① 参与人名单 70+ 人：单行高 %spx、内容溢出被截断（scrollWidth>clientWidth）"
               % r6.get('h'))
        await ev("closeModal('columnDetailModal')")
        await asyncio.sleep(0.5)

        # ── ② 事项预览：负责人 m1l ──
        r7 = await ev("""(async function(){
          const ids=CHK_CURRENT_CARDS||[];
          if(!ids.length)return {err:'无事项'};
          openDetail(ids[0]);
          return {card:ids[0]};
        })()""", aw=True)
        await asyncio.sleep(2.5)
        r8 = await ev("""(function(){
          const m=document.getElementById('d_meta');
          if(!m)return {err:'d_meta 不存在'};
          const spans=[].slice.call(m.querySelectorAll('.m1l'));
          return {n:spans.length,
                  st:spans.length?getComputedStyle(spans[0]).textOverflow:''};
        })()""")
        ok(r8 and not r8.get('err') and r8.get('n', 0) >= 1 and r8.get('st') == 'ellipsis',
           "② 事项预览负责人 .m1l 存在且 ellipsis（%s）" % json.dumps(r8, ensure_ascii=False))
        print('---- 结果: %d PASS / %d FAIL ----' % (ok_n, fail_n), flush=True)
    finally:
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205j')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
