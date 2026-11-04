# -*- coding: utf-8 -*-
"""#51 UI 实测：统计卡片点击筛选 / 状态下拉移除 / 周数倒序 / 看板单击多选。
⚠️ 夹具看板的 tab 在未展开的部门组里不在 DOM → 用直接调 pickBoard() 验证交互逻辑。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9463
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__mb_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 14:30:00'
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    bid1, bid2 = PREFIX + 'B1', PREFIX + 'B2'
    for bid, name in ((bid1, PREFIX + '看板一'), (bid2, PREFIX + '看板二')):
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, name, '', 'admin', now))
        c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,0,'日常','启用','',?)", (bid, PREFIX + '部门', now))
        for i, cname in enumerate(('C早', 'C晚')):
            c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned) VALUES (?,?,?,?,?,'x','日常','2026',0)",
                      (bid + '::' + cname, PREFIX + 'col%d_%d' % (i, 1 if bid == bid1 else 2), bid, cname, now))
    def ins(cid, bid, i, cname, st, csort, wk):
        c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,creator,created,modified,week_no,deleted,parent_id,column_sort)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'',?)""",
                  (cid, bid, PREFIX + ('看板一' if bid == bid1 else '看板二'), PREFIX + 'col%d_%d' % (i, 1 if bid == bid1 else 2),
                   cname, PREFIX + cid, st, 'admin', now, now, wk, csort))
    # B1：C早(done 5) + C早(progressing 5) + C晚(open 9)；两个周数（验证倒序）
    ins(PREFIX + 'K1', bid1, 0, 'C早', 'done', '5', '2026年第45周')
    ins(PREFIX + 'K2', bid1, 0, 'C早', 'progressing', '5', '2026年第2周')
    ins(PREFIX + 'K3', bid1, 1, 'C晚', 'open', '9', '2026年第45周')
    ins(PREFIX + 'K4', bid2, 0, 'C早', 'done', '3', '2026年第45周')
    c.commit(); c.close()
    return {'b1': bid1, 'b2': bid2}

def cleanup():
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.commit(); c.close()

async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_mb%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0
            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid: return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')
            async def wait_cards(timeout=12):
                deadline = time.time() + timeout
                last = None
                while time.time() < deadline:
                    last = await ev("document.querySelectorAll('#boardContent .item-card').length")
                    await asyncio.sleep(0.5)
                return last
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value=%s;document.getElementById('btn').click();" % json.dumps(PWD))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(2)

            # ── ③ 状态下拉移除 + 搜索框加宽 ──
            print('\n【③ 状态下拉移除】')
            r = await ev("(function(){return {sel:!!document.getElementById('statusFilter'),w:document.getElementById('searchInput').getBoundingClientRect().width}})()")
            ok(r.get('sel') is False, '状态下拉已移除')
            ok((r.get('w') or 0) >= 260, '搜索框已加宽（%s px ≥ 260）' % r.get('w'))

            # ── 选中看板一（直接调 pickBoard —— tab 在未展开的部门组里不在 DOM）──
            print('\n【选中看板一】')
            await ev("pickBoard(%s);" % json.dumps(fx['b1']))
            await asyncio.sleep(3)
            r = await ev("(function(){return {sel:[...curBoards],n:document.querySelectorAll('#boardContent .item-card').length}})()")
            ok(r.get('sel') == [fx['b1']], 'pickBoard 选中看板一（%s）' % r.get('sel'))
            ok(r.get('n') == 3, '看板一 3 张卡（实际 %s）' % r.get('n'))

            # ── ①② 统计卡片 ──
            print('\n【①② 统计卡片】')
            r = await ev("""(function(){
              var cards=[].slice.call(document.querySelectorAll('#progressOverview .stat-card'));
              return {count:cards.length,
                      labels:cards.map(function(c){return (c.querySelector('.stat-label')||{}).textContent}),
                      clickable:cards.filter(function(c){return c.classList.contains('stat-click')}).length};
            })()""")
            ok(r.get('count') == 4, '统计带 4 张卡片：%s' % r.get('labels'))
            ok(r.get('clickable') == 3, '除总事项外 3 张可点击')
            await ev("(function(){var cs=document.querySelectorAll('#progressOverview .stat-click');cs[0].click();})()")
            await asyncio.sleep(3)
            r = await ev("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#progressOverview .stat-click'));
              var on=cs.filter(function(c){return c.classList.contains('on')}).map(function(c){return c.querySelector('.stat-label').textContent});
              return {on:on,n:document.querySelectorAll('#boardContent .item-card').length};
            })()""")
            ok(r.get('on') == ['已完成'], '单击「已完成」→ 选中')
            ok(r.get('n') == 1, '筛选后只剩 done 的 1 张（实际 %s）' % r.get('n'))
            await ev("(function(){var cs=document.querySelectorAll('#progressOverview .stat-click');cs[1].click();})()")
            await asyncio.sleep(3)
            r = await ev("""(function(){
              var on=document.querySelectorAll('#progressOverview .stat-click.on').length;
              return {on:on,n:document.querySelectorAll('#boardContent .item-card').length};
            })()""")
            ok(r.get('on') == 2, '再点「进行中」→ 多选组合')
            ok(r.get('n') == 2, '组合 done+progressing → 2 张（实际 %s）' % r.get('n'))
            await ev("(function(){var cs=document.querySelectorAll('#progressOverview .stat-click');cs[0].click();cs[1].click();})()")
            await asyncio.sleep(3)
            r = await ev("(function(){return {on:document.querySelectorAll('#progressOverview .stat-click.on').length,n:document.querySelectorAll('#boardContent .item-card').length}})()")
            ok(r.get('on') == 0 and r.get('n') == 3, '全部取消 → 恢复 3 张（on=%s n=%s）' % (r.get('on'), r.get('n')))

            # ── ④ 周数倒序 ──
            print('\n【④ 周数倒序】')
            r = await ev("""(function(){
              var opts=(typeof WEEK_OPTIONS!=='undefined')?WEEK_OPTIONS.slice():[];
              function key(w){var m=w.match(/(\\d{4})[^\\d]*(\\d+)/);return m?(+m[1])*100+(+m[2]):0}
              var desc=true;
              for(var i=1;i<opts.length;i++){ if(key(opts[i])>key(opts[i-1]))desc=false; }
              return {n:opts.length,desc:desc,first:opts[0],last:opts[opts.length-1]};
            })()""")
            ok(r.get('n', 0) >= 2 and r.get('desc') is True,
               '周数候选倒序（n=%s 首=%s 末=%s）' % (r.get('n'), r.get('first'), r.get('last')))

            # ── ⑤ 看板单击多选 ──
            print('\n【⑤ 看板多选】')
            await ev("pickBoard(%s);" % json.dumps(fx['b2']))
            await asyncio.sleep(3)
            r = await ev("(function(){return {sel:[...curBoards].sort(),n:document.querySelectorAll('#boardContent .item-card').length}})()")
            ok(r.get('sel') == sorted([fx['b1'], fx['b2']]),
               '点第二个看板 → 两看板同时选中（%s）' % r.get('sel'))
            ok(r.get('n') == 4, '内容合并展示 4 张卡（实际 %s）' % r.get('n'))
            await ev("pickBoard(%s);" % json.dumps(fx['b1']))
            await asyncio.sleep(3)
            r = await ev("(function(){return {sel:[...curBoards],n:document.querySelectorAll('#boardContent .item-card').length}})()")
            ok(r.get('sel') == [fx['b2']], '再点已选中的看板一 → 单击取消（剩 %s）' % r.get('sel'))
            ok(r.get('n') == 1, '内容只剩看板二的 1 张卡（实际 %s）' % r.get('n'))
            await ev("pickBoard(%s);" % json.dumps(fx['b2']))
            await asyncio.sleep(2)
            r = await ev("(function(){return {sel:[...curBoards],empty:document.querySelector('#boardContent .empty')?1:0}})()")
            ok(r.get('sel') == [] and r.get('empty') == 1, '全部取消 → 回到「已取消选择」空状态')
    finally:
        cleanup()
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
