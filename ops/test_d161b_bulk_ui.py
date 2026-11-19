# -*- coding: utf-8 -*-
"""#161b CDP：全选当前按钮、通用批量删除、导出勾选菜单、失效校验"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9455
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m, flush=True)

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM cards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_bd_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_bd_b'")
    c.execute("INSERT INTO boards (board_id,board_name,sort,created_at) VALUES ('__t_bd_b','__t_批量测试看板',0,datetime('now'))")
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_bd_b::__t_板块A','COLbd1','__t_bd_b','__t_板块A',date('now'),'admin','日常','2026',0,'','','open','')")
    for i, cid in ((1, '__t_bd_c1'), (2, '__t_bd_c2'), (3, '__t_bd_c3')):
        c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
                  " VALUES (?,'__t_bd_b','__t_批量测试看板','__t_板块A',?,'open','',datetime('now'),0,0,'')", (cid, '__t_事项%d' % i))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_bd_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_bd_b'")
    c.commit(); c.close()

setup()
try:
    async def main():
        import websockets
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d161')
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
        pending = {}
        dialog_fired = asyncio.Event()
        async def reader():
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') is not None and msg['id'] in pending:
                    fut = pending.pop(msg['id'])
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif msg.get('method') == 'Page.javascriptDialogOpening':
                    dialog_fired.set()
                    await w.send(json.dumps({'id': 999901, 'method': 'Page.handleJavaScriptDialog',
                                             'params': {'accept': True}}))
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
        rt = asyncio.create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"): break
        await asyncio.sleep(1.5)
        await ev("(function(){const b=(ME.boards||[]).find(x=>x.board_id==='__t_bd_b');if(b)pickBoard(b.board_id);})()")
        await asyncio.sleep(2.5)

        print('【① 勾选关闭态：全选当前隐藏】', flush=True)
        r = await ev("(function(){const ab=document.getElementById('chkAllBtn');return {hidden:ab&&ab.style.display==='none'}})()")
        ok(r.get('hidden'), '勾选未启用时「全选当前」隐藏')

        print('【② 启用勾选 → 全选当前出现在勾选按钮左侧】', flush=True)
        await ev("document.getElementById('chkModeBtn').click()")
        await asyncio.sleep(2.5)
        r2 = await ev("""(function(){
          const ab=document.getElementById('chkAllBtn'), cm=document.getElementById('chkModeBtn');
          const ar=ab.getBoundingClientRect(), cr=cm.getBoundingClientRect();
          return {visible:ab.style.display!=='none', left:ar.right<=cr.left+2,
                  txt:ab.textContent, gap:Math.round(cr.left-ar.right)};
        })()""")
        print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
        ok(r2.get('visible') and r2.get('left'), '全选当前可见且位于勾选按钮左侧（间隔 %s px）' % r2.get('gap'))

        print('【③ 点全选当前 → 全部事项勾选 + 板块全选】', flush=True)
        await ev("document.getElementById('chkAllBtn').click()")
        await asyncio.sleep(0.8)
        r3 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          const items=[...document.querySelectorAll('#boardContent .item-chk')];
          return {colChecked:col.checked, itemChecked:items.map(x=>x.checked),
                  colSet:[...COL_CHECKED], itemSet:[...ITEM_CHECKED]};
        })()""")
        print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
        ok(r3.get('colChecked') and all(r3.get('itemChecked') or []),
           '3 个事项全勾 + 板块全选')
        ok(len(r3.get('itemSet') or []) == 3 and len(r3.get('colSet') or []) == 1, '集合落位')

        print('【④ 菜单：导出勾选（xlsx）+ 批量删除勾选】', flush=True)
        await ev("document.getElementById('toolbarOpsBtn').click()")
        await asyncio.sleep(1)
        menu = await ev("""(function(){
          const menu=document.getElementById('rowOpsMenu');
          const t=menu?menu.textContent:'';
          return {hasExport:t.indexOf('导出勾选')>=0, hasDel:t.indexOf('批量删除勾选')>=0,
                  oldExport:t.indexOf('导出（xlsx）')>=0};
        })()""")
        print('  ', json.dumps(menu, ensure_ascii=False), flush=True)
        ok(menu.get('hasExport') and menu.get('hasDel') and not menu.get('oldExport'), '菜单项升级到位')
        await ev("closeRowOps()")

        print('【⑤ 失效校验：勾选仅含已失效 id → 剔除且不执行】', flush=True)
        await ev("(function(){COL_CHECKED.clear();ITEM_CHECKED.clear();"
                 "COL_CHECKED.add('__t_bd_b::__t_不存在');ITEM_CHECKED.add('__t_bd_fake');saveColChecked();saveItemChecked();})()")
        await ev("bulkDeleteChecked()")
        await asyncio.sleep(2)
        r5 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          return {toast:toasts, rows:document.querySelectorAll('#boardContent .week-group').length,
                  dialog:!!document.querySelector('dialog')};
        })()""")
        print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
        ok('均已失效' in (r5.get('toast') or ''), '失效项剔除提示：%s' % r5.get('toast'))
        ok(r5.get('rows') == 1, '真实数据未被删除（板块仍在）')

        print('【⑥ 全选当前 → 批量删除勾选生效（板块+事项一起删）】', flush=True)
        await ev("selectAllCurrent()")
        await asyncio.sleep(0.8)
        await ev("bulkDeleteChecked()")
        for _ in range(5):
            try:
                await asyncio.wait_for(dialog_fired.wait(), timeout=1)
                break
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(3)
        r6 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          return {toast:toasts, rows:document.querySelectorAll('#boardContent .week-group').length,
                  empty:document.querySelector('#boardContent .empty')?true:false};
        })()""")
        print('  ', json.dumps(r6, ensure_ascii=False), flush=True)
        ok('已删除 板块 1 个' in (r6.get('toast') or ''), '删除提示（板块级联删掉其下事项，事项不再重复删）：%s' % r6.get('toast'))
        ok(r6.get('rows') == 0 or r6.get('empty'), '板块与事项全部消失')
    asyncio.run(main())
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)), flush=True)
finally:
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], capture_output=True)
    except Exception:
        pass
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_bd_b'").fetchone()[0]
    c.close()
    print('夹具残留 cards=%d' % n)
