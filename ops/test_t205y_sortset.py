# -*- coding: utf-8 -*-
"""T-205y：排序设定弹窗（#205y 2026-11-18）CDP + API 实测
① 筛选栏排序下拉移除（样式回滚）+【排序设定】按钮就位（到期筛选/清空筛选之间、同形态）；
② 弹窗：板块/事项分区独立配置，勾选顺序=优先级，各字段独立升降序，取消还原快照；
③ 排序应用：事项多级（DOM 实测）+ 板块多级（DOM 实测）+ 置顶恒浮顶；
④ 导出 xlsx 同步排序（sort_keys/sort_dirs/pin_ids）。
API 夹具（__t205y_ 前缀）测完即删。

⚠️ T-015（2026-11-18）：#205z 之后排序配置的真源=服务端 user_prefs.sort_cfg（按 username
行隔离），localStorage 只是本地缓存。本测试驱动 sortSetApply 会经 _prefPush（800ms 防抖）
把 admin 的配置 PUT 到服务端且**跨运行残留** → 下一轮登录时 loadUserPrefs 拉服务端值
覆盖内存 SORT_CFG，测试假设的「默认态」不复存在（历史实测 14/23 的根因）。
因此：① 每轮启动前精确清掉 admin 的 sort_cfg 行（key 精确匹配，非宽匹配）；
② finally 等 1.2s 防抖落地后二删并断言零残留；③ 持久化断言=服务端真源（GET /api/prefs）
+ localStorage 缓存双口径。"""
import asyncio, io, json, os, shutil, sqlite3, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'
TK = make_token('admin')
DB = 'src/app.db'

def db_del_sort_cfg(accts):
    """精确清理某账号的 sort_cfg 偏好行（username+key 双主键精确匹配，非宽匹配）。
    同 t205z 的 db_del_sort_cfg —— #205z 之后必须先清服务端行，测试的「默认态」才成立。"""
    conn = sqlite3.connect(DB)
    for a in accts:
        conn.execute("DELETE FROM user_prefs WHERE username=? AND key='sort_cfg'", (a,))
    conn.commit()
    left = {a: conn.execute("SELECT COUNT(*) FROM user_prefs WHERE username=? AND key='sort_cfg'",
                            (a,)).fetchone()[0] for a in accts}
    conn.close()
    return left

_n = {'ok': 0, 'fail': 0}
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    _n['ok' if cond else 'fail'] += 1

def api(path, method='GET', body=None, raw=False):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TK)
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            b = r.read()
            return (r.status, b if raw else json.loads(b.decode()))
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    import websockets
    col_card = col_a = col_b = None
    ids = {}
    try:
        # ── 夹具：3 个板块（供板块排序断言）+ 3 张卡（供事项排序断言） ──
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205y_排序板块',
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-19 10:00:00'})
        if st in (200, 201): col_card = d.get('col_key')
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205y_甲',
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18 10:00:00',
                                            'due_date': '2026-12-20'})
        if st in (200, 201): col_a = d.get('col_key')
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205y_乙',
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-17 10:00:00',
                                            'due_date': '2026-12-10'})
        if st in (200, 201): col_b = d.get('col_key')
        for name, begin, due in [('__t205y_卡甲', '2026-11-10', '2026-12-20'),
                                 ('__t205y_卡乙', '', '2026-12-10'),
                                 ('__t205y_卡丙', '2026-11-05', '')]:
            stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': name,
                                                'fields': {'column_name': '__t205y_排序板块',
                                                           'begin': begin, 'due': due}})
            if stc in (200, 201): ids[name] = dc.get('card_id')
            time.sleep(1.1)
        print('fixture:', st, len(ids), flush=True)

        # T-015：启动浏览器前清掉 admin 的服务端 sort_cfg（上一轮运行的残留会经
        # 登录时 loadUserPrefs 覆盖内存 SORT_CFG，令「默认态」断言全部失真）
        left = db_del_sort_cfg(['admin'])
        ok(left.get('admin') == 0, '⓪ 前置：admin 服务端 sort_cfg 行已清零（残留=%s）' % left.get('admin'))

        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205y')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                          '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                          '--remote-debugging-port=9657', '--user-data-dir=' + profile,
                          'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9657/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        w = None
        try:
            t = json.loads(urllib.request.urlopen('http://127.0.0.1:9657/json', timeout=5).read())
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
                    return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:300]}
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

            LBL = json.dumps({'begin': '开始时间', 'due': '截止时间', 'created': '创建时间'}, ensure_ascii=False)
            async def ss_row(kind, f):
                return await ev("""(function(){
                  const L=%s; const sec=document.querySelectorAll('#sortSetBody .ss-section')[%s===0?0:1];
                  if(!sec)return {err:'section不可见'};
                  const row=[].slice.call(sec.querySelectorAll('.ss-row'))
                    .find(function(r){return r.querySelector('.ss-check span').textContent===L[%s];});
                  if(!row)return {err:'row不可见'};
                  const badge=row.querySelector('.ss-pri');
                  const btns=row.querySelectorAll('.ss-dir-btn');
                  return {checked:row.querySelector('input').checked,
                          badge:badge.textContent, off:badge.classList.contains('ss-pri-off'),
                          dirOn:[].map.call(btns,function(b){return b.classList.contains('on');}),
                          dis:btns[0].disabled};
                })()""" % (LBL, 0 if kind == 'card' else 1, json.dumps(f, ensure_ascii=False)))
            async def ss_toggle(kind, f, on):
                return await ev("""(function(){
                  const L=%s; const sec=document.querySelectorAll('#sortSetBody .ss-section')[%s];
                  const row=[].slice.call(sec.querySelectorAll('.ss-row'))
                    .find(function(r){return r.querySelector('.ss-check span').textContent===L[%s];});
                  const cb=row.querySelector('input'); cb.checked=%s; cb.dispatchEvent(new Event('change'));
                  return {order:SORT_CFG[%s].order.slice()};})()"""
                        % (LBL, 0 if kind == 'card' else 1, json.dumps(f, ensure_ascii=False),
                           'true' if on else 'false', json.dumps(kind)))
            async def ss_dir(kind, f, asc):
                return await ev("""(function(){
                  const L=%s; const sec=document.querySelectorAll('#sortSetBody .ss-section')[%s];
                  const row=[].slice.call(sec.querySelectorAll('.ss-row'))
                    .find(function(r){return r.querySelector('.ss-check span').textContent===L[%s];});
                  row.querySelectorAll('.ss-dir-btn')[%s].click();
                  return SORT_CFG[%s].dir[%s];})()"""
                        % (LBL, 0 if kind == 'card' else 1, json.dumps(f, ensure_ascii=False),
                           0 if asc else 1, json.dumps(kind), json.dumps(f, ensure_ascii=False)))
            async def card_order():
                return await ev("""(function(){
                  const hs=[].slice.call(document.querySelectorAll('.week-header'))
                    .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205y_排序板块')>=0;});
                  if(!hs.length)return {err:'板块不可见'};
                  const body=hs[0].parentElement.querySelector('.week-body');
                  return {order:[].slice.call(body.querySelectorAll('.item-title')).map(function(x){return x.textContent;})
                    .filter(function(s){return s.indexOf('__t205y_')>=0;})};})()""")
            async def col_order():
                return await ev("""[].slice.call(document.querySelectorAll('.week-title'))
                  .filter(function(x){return x.offsetParent!==null && x.textContent.indexOf('__t205y_')>=0;})
                  .map(function(x){return x.textContent;}).join(',')""")

            # ── ① 筛选栏回滚 + 排序设定按钮 ──
            r1 = await ev("""(function(){
              const sel=document.getElementById('cardSortSel');
              const wrap=document.getElementById('cardSortWrap');
              const btn=document.getElementById('sortSetBtn');
              const due=document.getElementById('dueFilterBtn');
              const clr=document.getElementById('clearFilterBtn');
              const order=due&&btn&&clr ? (due.compareDocumentPosition(btn)&Node.DOCUMENT_POSITION_FOLLOWING)
                && (btn.compareDocumentPosition(clr)&Node.DOCUMENT_POSITION_FOLLOWING) : false;
              const sd=due?getComputedStyle(due):null, sb=btn?getComputedStyle(btn):null;
              return {selGone:!sel, wrapGone:!wrap, btn:!!btn, between:order,
                      sameCls:sd&&sb?sb.className===sd.className:false,
                      samePad:sd&&sb?sb.paddingLeft===sd.paddingLeft&&sb.paddingRight===sd.paddingRight:false,
                      sameFont:sd&&sb?sb.fontSize===sd.fontSize:false};})()""")
            ok(r1 and not r1.get('__error__') and r1.get('selGone') and r1.get('wrapGone'),
               "① 筛选栏排序下拉已移除（cardSortSel/sort-filter 不存在）")
            ok(r1 and r1.get('btn') and r1.get('between'),
               "①【排序设定】位于【到期筛选】与【清空筛选】之间")
            ok(r1 and r1.get('sameCls') and r1.get('samePad') and r1.get('sameFont'),
               "①【排序设定】与【到期筛选】同形态（class/内边距/字号一致）")

            # ── ② 弹窗默认态 ──
            await ev("openSortSetModal()")
            await asyncio.sleep(0.5)
            r2 = await ev("""(function(){
              const m=document.getElementById('sortSetModal');
              const secs=[].slice.call(document.querySelectorAll('#sortSetBody .ss-section'));
              return {visible:m.style.display!=='none', n:secs.length,
                      t1:secs[0]?secs[0].querySelector('.ss-title').textContent:'',
                      t2:secs[1]?secs[1].querySelector('.ss-title').textContent:'',
                      cardCfg:JSON.parse(JSON.stringify(SORT_CFG.card)),
                      colCfg:JSON.parse(JSON.stringify(SORT_CFG.col))};})()""")
            ok(r2 and r2.get('visible') and r2.get('n') == 2,
               "② 弹窗打开，板块/事项两个独立分区（%s / %s）" % ((r2 or {}).get('t1'), (r2 or {}).get('t2')))
            ok(r2 and r2.get('cardCfg', {}).get('order') == ['begin', 'due', 'created']
               and r2.get('colCfg', {}).get('order') == ['begin', 'due', 'created'],
               "② 默认配置：三字段全参与（开始/截止/创建 优先级 1/2/3，#205y 用户指定）")
            cc2 = r2.get('cardCfg') or {}
            ok(cc2.get('dir', {}).get('begin') == 'asc' and cc2.get('dir', {}).get('created') == 'asc',
               "② 事项默认全升序")
            cl2 = r2.get('colCfg') or {}
            ok(cl2.get('dir', {}).get('begin') == 'desc' and cl2.get('dir', {}).get('created') == 'desc',
               "② 板块默认全降序")
            rowC = await ss_row('card', 'created')
            rowB = await ss_row('card', 'begin')
            ok(rowC and rowC.get('checked') and rowC.get('badge') == '第3优先' and rowC.get('dirOn') == [True, False],
               "② 事项「创建时间」默认：第3优先 + 升序")
            ok(rowB and rowB.get('checked') and rowB.get('badge') == '第1优先',
               "② 事项「开始时间」默认：第1优先")

            # ── ③ 勾选顺序 = 优先级 + 取消还原（默认三字段已勾选） ──
            r3 = await ss_toggle('card', 'created', False)   # 取消创建 → 后续前移
            r3b = await ss_toggle('card', 'created', True)   # 再勾选 → 追加到末尾（勾选先后=优先级）
            ok(r3 and r3.get('order') == ['begin', 'due']
               and r3b and r3b.get('order') == ['begin', 'due', 'created'],
               "③ 再勾选的字段排末尾（勾选先后=优先级，实际 %s）" % (r3b or {}).get('order'))
            rowD = await ss_row('card', 'due')
            rowBg = await ss_row('card', 'begin')
            ok(rowBg and rowBg.get('badge') == '第1优先' and rowD and rowD.get('badge') == '第2优先',
               "③ 优先级徽标实时编号（begin 第1 / due 第2）")
            r3c = await ss_toggle('card', 'begin', False)
            ok(r3c and r3c.get('order') == ['due', 'created'],
               "③ 取消勾选 → 后续字段优先级前移（实际 %s）" % (r3c or {}).get('order'))
            rowD2 = await ss_row('card', 'due')
            ok(rowD2 and rowD2.get('badge') == '第1优先', "③ 取消后徽标重新编号（due 变第1优先）")
            # 取消 = 还原打开时快照
            await ev("sortSetCancel()")
            await asyncio.sleep(0.3)
            r3x = await ev("JSON.parse(JSON.stringify(SORT_CFG.card)).order")
            ok(r3x == ['begin', 'due', 'created'], "④ 取消 → 还原打开时快照（order=%s）" % r3x)

            # ── ⑤ 应用：事项/板块均只留「截止」升序 → DOM 实测 ──
            await ev("openSortSetModal()")
            await asyncio.sleep(0.3)
            await ss_toggle('card', 'begin', False)
            await ss_toggle('card', 'created', False)
            await ss_toggle('col', 'begin', False)
            await ss_toggle('col', 'created', False)
            await ss_dir('card', 'due', True)    # 板块默认降序（新默认）→ 测试切升序验证
            await ss_dir('col', 'due', True)
            await ev("sortSetApply()")
            await asyncio.sleep(2.5)
            await ev("expandAll()")
            await asyncio.sleep(1.5)
            o = await card_order()
            ok(o and not o.get('err') and o.get('order') == ['__t205y_卡乙', '__t205y_卡甲', '__t205y_卡丙'],
               "⑤ 事项按截止时间升序：乙(12-10)→甲(12-20)→丙(无日期排最后)（%s）" % (o or {}).get('order'))
            co = await col_order()
            ok(co == '__t205y_乙,__t205y_甲,__t205y_排序板块',
               "⑤ 板块按截止时间升序：乙(12-10)→甲(12-20)→排序板块(无截止排最后)（%s）" % co)
            ls = await ev("localStorage.getItem('tapd.sortCfg_'+ME.username)")
            ok(ls and json.loads(ls).get('card', {}).get('order') == ['due'],
               "⑤ 配置持久化·本地缓存（localStorage tapd.sortCfg_<user>）")
            # T-015：#205z 之后真源在服务端 —— sortSetApply 经 _prefPush（800ms 防抖）上传，
            # 上面的 DOM 断言已耗时 >2s，防抖必然已落地，此处直接读服务端核验
            stp, dp = api('/api/prefs')
            srv_card = ((dp.get('prefs') or {}).get('sort_cfg') or {}).get('card', {}).get('order')
            ok(srv_card == ['due'],
               "⑤ 配置持久化·服务端真源（GET /api/prefs sort_cfg.card.order=['due']，实际 %s）" % srv_card)

            # ── ⑥ 置顶恒浮顶（不受排序配置影响） ──
            await ev("MY_PINS.card[%s]=1;reload(curPage)" % json.dumps(ids.get('__t205y_卡丙')))
            await asyncio.sleep(2.5)
            await ev("expandAll()")
            await asyncio.sleep(1.5)
            o6 = await card_order()
            ok(o6 and o6.get('order') == ['__t205y_卡丙', '__t205y_卡乙', '__t205y_卡甲'],
               "⑥ 置顶（丙，本应因无截止排最后）恒浮顶（%s）" % (o6 or {}).get('order'))
            await ev("delete MY_PINS.card[%s];reload(curPage)" % json.dumps(ids.get('__t205y_卡丙')))
            await asyncio.sleep(2.5)

            # ── ⑦ 板块/事项互不影响：事项 begin 升序，板块仍 due 升序 ──
            await ev("openSortSetModal()")
            await asyncio.sleep(0.3)
            await ss_toggle('card', 'due', False)
            await ss_toggle('card', 'begin', True)
            await ev("sortSetApply()")
            await asyncio.sleep(2.5)
            await ev("expandAll()")
            await asyncio.sleep(1.5)
            o7 = await card_order()
            co7 = await col_order()
            ok(o7 and o7.get('order') == ['__t205y_卡丙', '__t205y_卡甲', '__t205y_卡乙'],
               "⑦ 事项改按开始时间升序：丙(11-05)→甲(11-10)→乙(无开始排最后)（%s）" % (o7 or {}).get('order'))
            ok(co7 == '__t205y_乙,__t205y_甲,__t205y_排序板块',
               "⑦ 板块配置不受事项修改影响（仍按截止升序，%s）" % co7)

            # ── ⑧ 导出 xlsx 同步排序 ──
            cids = ','.join(ids[x] for x in ['__t205y_卡甲', '__t205y_卡乙', '__t205y_卡丙'])
            from openpyxl import load_workbook
            def export_rows(qs):
                stx, bx = api('/api/export/xlsx?' + qs, raw=True)
                if stx != 200: return {'err': 'HTTP %s' % stx}
                wb = load_workbook(io.BytesIO(bx))
                wsx = wb.active
                rows = list(wsx.iter_rows(values_only=True))
                hdr = rows[0]
                name_i = next((i for i, h in enumerate(hdr) if h and '名称' in str(h)), 0)
                return [r[name_i] for r in rows[1:] if r[name_i] and '__t205y_' in str(r[name_i])]
            # due 升序 + 丙置顶 → 丙,乙,甲
            q = 'card_ids=%s&sort_keys=due&sort_dirs=asc&pin_ids=%s' % (cids, ids.get('__t205y_卡丙'))
            ex1 = export_rows(q)
            ok(ex1 == ['__t205y_卡丙', '__t205y_卡乙', '__t205y_卡甲'],
               "⑧ 导出同步排序：置顶丙恒最前 + 截止升序（%s）" % ex1)
            # begin 降序 → 甲(11-10),丙(11-05),乙(空排最后)
            q2 = 'card_ids=%s&sort_keys=begin&sort_dirs=desc' % cids
            ex2 = export_rows(q2)
            ok(ex2 == ['__t205y_卡甲', '__t205y_卡丙', '__t205y_卡乙'],
               "⑧ 导出同步排序：开始时间降序 + 空值排最后（%s）" % ex2)
            # 未传排序 → 兜底（begin,名称 稳定排序；空 begin 字典序最小 → 乙最前）
            q3 = 'card_ids=%s' % cids
            ex3 = export_rows(q3)
            ok(ex3 == ['__t205y_卡乙', '__t205y_卡丙', '__t205y_卡甲'],
               "⑧ 未配置排序 → 后端兜底稳定排序不受影响（%s）" % ex3)
            # 清理测试配置（本地 localStorage 是临时 profile，无需还原）
        finally:
            try:
                if w: await w.close()
            except Exception: pass
            from cdp_test_helper import kill_profile_chrome
            kill_profile_chrome('cdp_t205y')
            shutil.rmtree(profile, ignore_errors=True)
    finally:
        # ── 夹具清理 ──
        stc, dc = api('/api/cards?board_id=%s&size=500' % BOARD)
        for c in (dc.get('cards') or dc.get('columns') or []):
            pass
        for name, cid in ids.items():
            if cid: api('/api/cards/' + cid, 'DELETE')
        for k in (col_card, col_a, col_b):
            if k: api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
        print('fixture cleaned', flush=True)
        # ── T-015：服务端 sort_cfg 收尾清理 ──
        # ⑦ 的 sortSetApply 经 _prefPush 800ms 防抖上传，DELETE 后飞行中的 PUT 会把行
        # 「复活」（t205z 坑①同款）→ 等 1.2s 再删、0.8s 后二删并断言零残留
        time.sleep(1.2)
        db_del_sort_cfg(['admin'])
        time.sleep(0.8)
        left = db_del_sort_cfg(['admin'])
        ok(left.get('admin') == 0, '⑨ 收尾：admin 服务端 sort_cfg 行二删后零残留（残留=%s）' % left.get('admin'))

asyncio.run(main())
print('结果: %d PASS / %d FAIL' % (_n['ok'], _n['fail']))
if _n['fail']: sys.exit(1)
