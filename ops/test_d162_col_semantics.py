# -*- coding: utf-8 -*-
"""#162 针对性实测：①勾板块批量删除只删事项板块保留 ②空板块显示 ③清空无事项板块"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9456
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
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d162')
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
        # 带守卫选板：登录后可能已自动选中，直接 pickBoard 会变成取消选择
        await ev("(function(){if(!curBoards.has('__t_bd_b'))pickBoard('__t_bd_b');})()")
        # 轮询等待内容区渲染出板块勾选框（需先开启勾选模式才有 → 分两步）
        for _ in range(20):
            await asyncio.sleep(0.5)
            if await ev("document.getElementById('boardContent')&&(document.querySelector('#boardContent .week-header')||document.querySelector('#boardContent .empty'))"): break

        print('【① 勾板块 → 批量删除勾选 → 只删事项，板块保留】', flush=True)
        await ev("document.getElementById('chkModeBtn').click()")
        for _ in range(20):
            await asyncio.sleep(0.5)
            if await ev("document.querySelector('#boardContent .col-chk')"): break
        await ev("(function(){document.querySelector('#boardContent .col-chk').click();})()")
        await asyncio.sleep(0.5)
        await ev("bulkDeleteChecked()")
        for _ in range(5):
            try:
                await asyncio.wait_for(dialog_fired.wait(), timeout=1); break
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(3)
        r1 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          var c=document.getElementById('boardContent');
          return {toast:toasts, colAlive:!!document.querySelector('#boardContent .week-header .week-title'),
                  colInDb:(typeof COLS_META!=='undefined')&&(COLS_META||[]).length,
                  items:document.querySelectorAll('#boardContent .item-card').length,
                  first300:c.innerHTML.slice(0,300)};
        })()""")
        print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
        ok('已删除事项 3 个' in (r1.get('toast') or ''), '提示删除 3 个事项：%s' % r1.get('toast'))
        ok(r1.get('colAlive') and r1.get('colInDb'), '板块保留（界面+数据库）')
        ok(r1.get('items') == 0, '事项全部删除')

        print('【② 空板块仍显示（标题 + 0/0 完成）】', flush=True)
        r2 = await ev("""(function(){
          const t=document.querySelector('#boardContent .week-header .week-title');
          const meta=document.querySelector('#boardContent .week-meta');
          return {title:t?t.textContent:'', meta:meta?meta.textContent:''};
        })()""")
        print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
        ok((r2.get('title') or '').find('板块A') >= 0, '空板块标题仍显示')
        ok((r2.get('meta') or '').find('0/0') >= 0, '完成计数 0/0')

        print('【③ 清空无事项板块：菜单存在 → 执行 → 板块删除】', flush=True)
        await ev("document.getElementById('toolbarOpsBtn').click()")
        await asyncio.sleep(1)
        menu = await ev("""(function(){
          const menu=document.getElementById('rowOpsMenu');
          if(!menu)return {found:false};
          const item=[...menu.querySelectorAll('.row-ops-item')].find(function(el){return el.textContent.indexOf('清空无事项板块')>=0;});
          if(!item)return {found:false, txt:menu.textContent.slice(0,150)};
          item.click();
          return {found:true};
        })()""")
        print('  ', json.dumps(menu, ensure_ascii=False), flush=True)
        ok(menu.get('found'), '菜单含「清空无事项板块」并点击')
        for _ in range(5):
            try:
                await asyncio.wait_for(dialog_fired.wait(), timeout=1); break
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(3)
        r3 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          return {toast:toasts, colAlive:!!document.querySelector('#boardContent .week-header'),
                  empty:!!document.querySelector('#boardContent .empty')};
        })()""")
        print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
        ok('已删除无事项板块 1 个' in (r3.get('toast') or ''), '空板块删除提示：%s' % r3.get('toast'))
        ok(r3.get('empty') and not r3.get('colAlive'), '空板块已从界面消失（内容区空态）')
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
