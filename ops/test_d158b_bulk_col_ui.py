# -*- coding: utf-8 -*-
"""#158b CDP（队列化收发版）：复选框位置/持久化、批量删除菜单与流程、无勾选防护
单 reader 协程读所有消息 → 按 id 分发响应、按 method 事件入队；confirm 自动接受。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9452
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m, flush=True)

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM cards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_ck_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_ck_b'")
    c.execute("INSERT INTO boards (board_id,board_name,sort,created_at) VALUES ('__t_ck_b','__t_勾选测试看板',0,datetime('now'))")
    for i, nm in enumerate(('__t_板块甲', '__t_板块乙'), 1):
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
                  " VALUES ('__t_ck_b::%s','COLck%d','__t_ck_b','%s',date('now'),'admin','日常','2026',0,'','','open','')" % (nm, i, nm))
        c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
                  " VALUES ('__t_ck_c%d','__t_ck_b','__t_勾选测试看板','%s','__t_事项%d','open','',datetime('now'),0,0,'')" % (i, nm, i))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_ck_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_ck_b'")
    c.commit(); c.close()

setup()
try:
    async def main():
        import websockets
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d158')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                          '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
            except Exception:
                time.sleep(0.5)
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)

        pending = {}           # id -> Future（响应等待）
        events = asyncio.Queue()  # 事件队列
        done = asyncio.Event()
        async def reader():
            while True:
                raw = await w.recv()
                msg = json.loads(raw)
                if msg.get('id') is not None and msg['id'] in pending:
                    fut = pending.pop(msg['id'])
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif msg.get('method') == 'Page.javascriptDialogOpening':
                    await w.send(json.dumps({'id': 999901, 'method': 'Page.handleJavaScriptDialog',
                                             'params': {'accept': True}}))
                elif msg.get('method'):
                    events.put_nowait(msg)

        seq = [0]
        async def send(m, p=None):
            seq[0] += 1; mid = seq[0]
            fut = asyncio.get_event_loop().create_future()
            pending[mid] = fut
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            res = await asyncio.wait_for(fut, timeout=30)
            return res.get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:200]}
            return r.get('result', {}).get('value')

        reader_task = asyncio.create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"): break
        await asyncio.sleep(1.5)

        async def pick_board():
            await ev("(function(){const g=groupBoardsByDept();const d=g.depts.find(x=>x.boards.some(b=>b.board_id==='__t_ck_b'));if(d){DEPT_OPEN[d.name]=true;}renderTabs();if(!curBoards.has('__t_ck_b'))pickBoard('__t_ck_b');})()")
            await asyncio.sleep(2.5)

        print('【① 选中夹具看板】', flush=True)
        await pick_board()

        print('【② 复选框位置几何】', flush=True)
        r = await ev("""(function(){
          const hd=document.querySelector('#boardContent .week-header');
          if(!hd)return {noHeader:true};
          const chev=hd.querySelector('.chev');
          const chk=hd.querySelector('.col-chk');
          const title=hd.querySelector('.week-title');
          const cr=chev.getBoundingClientRect(), kr=chk.getBoundingClientRect(), tr=title.getBoundingClientRect();
          return {hasChk:!!chk, gapChevChk:Math.round(kr.left-cr.right),
                  gapChkTitle:Math.round(tr.left-kr.right), leftOfTitle:kr.left<tr.left};
        })()""")
        print('  ', json.dumps(r, ensure_ascii=False), flush=True)
        ok(r.get('hasChk'), '每个板块标题前有复选框')
        ok((r.get('gapChevChk') or 0) > 0 and (r.get('gapChkTitle') or 0) > 0,
           '与三角箭头、标题互不重叠（间隔 %s / %s px）' % (r.get('gapChevChk'), r.get('gapChkTitle')))

        print('【③ 勾选板块甲 → 刷新页面后勾选保持】', flush=True)
        await ev("(function(){const chk=document.querySelector('#boardContent .week-header .col-chk');chk.click();})()")
        await asyncio.sleep(0.5)
        r2 = await ev("""(function(){
          const box=document.querySelector('#boardContent .week-header .col-chk');
          return {checked:box.checked, stored:JSON.parse(sessionStorage.getItem('colChk_admin')||'[]')};
        })()""")
        ok(r2.get('checked') and len(r2.get('stored') or []) == 1, '勾选写入本人会话存储：%s' % json.dumps(r2.get('stored'), ensure_ascii=False))
        await ev("location.reload()")
        await asyncio.sleep(4)
        await pick_board()
        r3 = await ev("(function(){const box=document.querySelector('#boardContent .week-header .col-chk');return {checked:!!box&&box.checked};})()")
        ok(r3.get('checked'), '页面刷新后勾选保持')

        print('【④ 无勾选防护】', flush=True)
        await ev("(function(){COL_CHECKED.clear();saveColChecked();})()")
        await asyncio.sleep(0.3)
        await ev("bulkDeleteColumns()")
        await asyncio.sleep(1.2)
        r4 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          return {toast:toasts, rows:document.querySelectorAll('#boardContent .week-group').length};
        })()""")
        ok('未勾选任何板块' in (r4.get('toast') or ''), '无勾选时提示且不执行：%s' % r4.get('toast'))
        ok(r4.get('rows') == 2, '板块数不变（%s）' % r4.get('rows'))

        print('【⑤ 菜单项存在 + 勾选后批量删除生效】', flush=True)
        # ④ 只清了集合未重绘 → 刷新让 DOM 复选框与集合重新同步
        await ev("location.reload()")
        await asyncio.sleep(4)
        await pick_board()
        await ev("document.getElementById('toolbarOpsBtn').click()")
        await asyncio.sleep(1)
        menu = await ev("""(function(){
          const menu=document.getElementById('rowOpsMenu');
          if(!menu)return {found:false, reason:'no menu'};
          const item=[...menu.querySelectorAll('.row-ops-item')].find(function(el){return el.textContent.indexOf('批量删除')>=0;});
          return {found:!!item, txt:menu.textContent.slice(0,160)};
        })()""")
        print('  ', json.dumps(menu, ensure_ascii=False), flush=True)
        ok(menu.get('found'), '「操作 ▾」菜单含「批量删除勾选板块」项')
        await ev("closeRowOps()")
        # 勾选并直接走产品保存/删除链路（confirm 自动接受由 reader 处理）
        await ev("(function(){const chk=document.querySelector('#boardContent .week-header .col-chk');if(!chk.checked)chk.click();})()")
        await asyncio.sleep(0.5)
        await ev("bulkDeleteColumns()")   # confirm 阻塞中；reader 收到对话框即 accept
        dlg_seen = False
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(events.get(), timeout=1)
                if evt.get('method') == 'Page.javascriptDialogOpening':
                    dlg_seen = True
            except asyncio.TimeoutError:
                break
        st = None
        for _ in range(30):
            await asyncio.sleep(1)
            st = await ev("""(function(){
              var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
              return {toast:toasts, rows:document.querySelectorAll('#boardContent .week-group').length,
                      stored:JSON.parse(sessionStorage.getItem('colChk_admin')||'[]')};
            })()""")
            if '已删除 1 个板块' in (st.get('toast') or ''):
                break
        print('  ', json.dumps(st, ensure_ascii=False), flush=True)
        ok('已删除 1 个板块' in (st.get('toast') or ''), '删除成功提示（confirm 已接受）：%s' % st.get('toast'))
        ok(st.get('rows') == 1, '板块甲已从界面消失（剩 %s 个）' % st.get('rows'))
        ok(len(st.get('stored') or []) == 0, '勾选状态已清空')
    asyncio.run(main())
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)), flush=True)
finally:
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], capture_output=True)
    except Exception:
        pass
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_ck_b'").fetchone()[0]
    c.close()
    print('夹具残留 cards=%d' % n)
