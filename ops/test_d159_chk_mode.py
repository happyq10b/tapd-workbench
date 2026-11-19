# -*- coding: utf-8 -*-
"""#159 勾选模式开关 + 三级三态联动 CDP 实测
夹具：看板 1 个板块，甲（2 子事项）、乙（无子事项）两张主事项。
单 reader + 队列分发 harness（confirm 不涉及）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9453
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
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_ck_b::__t_板块甲','COLck1','__t_ck_b','__t_板块甲',date('now'),'admin','日常','2026',0,'','','open','')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_m1','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_甲主事项','open','',datetime('now'),0,0,'')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_s1','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_甲子事项1','open','',datetime('now'),0,0,'__t_ck_m1')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_s2','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_甲子事项2','open','',datetime('now'),0,0,'__t_ck_m1')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_m2','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_乙主事项','open','',datetime('now'),0,0,'')")
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
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d159')
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
        async def reader():
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') is not None and msg['id'] in pending:
                    fut = pending.pop(msg['id'])
                    if fut and not fut.done():
                        fut.set_result(msg)
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

        print('【① 默认关闭：勾选框不存在】', flush=True)
        await pick_board()
        r = await ev("""(function(){
          return {col:document.querySelectorAll('#boardContent .col-chk').length,
                  item:document.querySelectorAll('#boardContent .item-chk').length,
                  btn:document.getElementById('chkModeBtn').textContent,
                  on:document.getElementById('chkModeBtn').classList.contains('on')};
        })()""")
        print('  ', json.dumps(r, ensure_ascii=False), flush=True)
        ok(r.get('col') == 0 and r.get('item') == 0, '默认无勾选框（col=%s item=%s）' % (r.get('col'), r.get('item')))
        ok(r.get('btn') == '启用勾选' and not r.get('on'), '开关初始为「启用勾选」动作（#160 动作式文案）')

        print('【② 开启勾选 → 三级勾选框出现】', flush=True)
        await ev("document.getElementById('chkModeBtn').click()")
        await asyncio.sleep(2.5)
        await pick_board()
        r2 = await ev("""(function(){
          return {col:document.querySelectorAll('#boardContent .col-chk').length,
                  item:document.querySelectorAll('#boardContent .item-chk').length,
                  btn:document.getElementById('chkModeBtn').textContent,
                  storedMode:sessionStorage.getItem('chkMode_admin')};
        })()""")
        print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
        ok(r2.get('col') == 1 and r2.get('item') == 2, '板块 1 + 主事项 2 勾选框出现')
        ok(r2.get('btn') == '关闭勾选', '开启后按钮显示动作「关闭勾选」')
        ok(r2.get('storedMode') == '1', '模式持久化（chkMode_admin=1）')

        print('【③ 勾板块 → 其下事项全选】', flush=True)
        await ev("(function(){document.querySelector('#boardContent .col-chk').click();})()")
        await asyncio.sleep(0.6)
        r3 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          const items=[...document.querySelectorAll('#boardContent .item-chk')];
          return {colChecked:col.checked, colInd:col.indeterminate,
                  itemChecked:items.map(function(x){return x.checked})};
        })()""")
        print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
        ok(r3.get('colChecked') and not r3.get('colInd'), '板块全选态')
        ok(all(r3.get('itemChecked') or []), '两个主事项自动勾选')

        print('【④ 展开甲子树 → 子事项跟随勾选；取消勾 1 个子事项 → 主事项+板块半选】', flush=True)
        await ev("toggleSubTree('__t_ck_m1',true)")
        await asyncio.sleep(1.5)
        r4 = await ev("""(function(){
          const subs=[...document.querySelectorAll('#boardContent .sub-chk')];
          return {subChecked:subs.map(function(x){return x.checked}), n:subs.length};
        })()""")
        print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
        ok(r4.get('n') == 2 and all(r4.get('subChecked') or []), '展开后子事项跟随勾选（2/2）')
        await ev("(function(){const s=[...document.querySelectorAll('#boardContent .sub-chk')][0];s.click();})()")
        await asyncio.sleep(0.6)
        r5 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          const mainChk=document.querySelector('.item-chk[data-ck=\"__t_ck_m1\"]');
          const subs=[...document.querySelectorAll('#boardContent .sub-chk')];
          return {colInd:col.indeterminate,colChecked:col.checked,
                  mainInd:mainChk.indeterminate,mainChecked:mainChk.checked,
                  subStates:subs.map(function(x){return x.checked})};
        })()""")
        print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
        ok((r5.get('mainInd')) and not r5.get('mainChecked'), '主事项呈半选（indeterminate）')
        ok(r5.get('colInd'), '板块呈半选（部分主事项勾选）')
        ok((r5.get('subStates') or []) == [False, True], '子事项一有一无')

        print('【⑤ 勾乙主事项 → 板块半选（甲半选+乙全选）】', flush=True)
        await ev("(function(){document.querySelector('.item-chk[data-ck=\"__t_ck_m2\"]').click();})()")
        await asyncio.sleep(0.6)
        r6 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          return {colChecked:col.checked, colInd:col.indeterminate};
        })()""")
        ok(r6.get('colInd') and not r6.get('colChecked'), '板块呈半选（甲半选 + 乙全选 → 聚合半选）')

        print('【⑥ 点击半选板块 → 全选（浏览器原生），再点 → 全部清空】', flush=True)
        await ev("(function(){document.querySelector('#boardContent .col-chk').click();})()")
        await asyncio.sleep(0.6)
        r7 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          const items=[...document.querySelectorAll('#boardContent .item-chk')];
          const subs=[...document.querySelectorAll('#boardContent .sub-chk')];
          return {colChecked:col.checked, colInd:col.indeterminate,
                  itemChecked:items.map(function(x){return x.checked}),
                  subChecked:subs.map(function(x){return x.checked})};
        })()""")
        print('  ', json.dumps(r7, ensure_ascii=False), flush=True)
        ok(r7.get('colChecked') and not r7.get('colInd') and all(r7.get('itemChecked') or []) and all(r7.get('subChecked') or []),
           '半选点击一次 = 板块全选（含子事项）')
        await ev("(function(){document.querySelector('#boardContent .col-chk').click();})()")
        await asyncio.sleep(0.6)
        r8 = await ev("""(function(){
          const col=document.querySelector('#boardContent .col-chk');
          const items=[...document.querySelectorAll('#boardContent .item-chk')];
          const subs=[...document.querySelectorAll('#boardContent .sub-chk')];
          return {colChecked:col.checked, colInd:col.indeterminate,
                  itemChecked:items.map(function(x){return x.checked}),
                  subChecked:subs.map(function(x){return x.checked})};
        })()""")
        print('  ', json.dumps(r8, ensure_ascii=False), flush=True)
        ok(not r8.get('colChecked') and not r8.get('colInd'), '再点一次板块回到未选')
        ok(not any(r8.get('itemChecked') or []) and not any(r8.get('subChecked') or []), '事项/子事项全部清空')

        print('【⑦ 关闭开关 → 勾选框消失 + 记录清空】', flush=True)
        # 先勾一个再关，验证清空
        await ev("(function(){document.querySelector('#boardContent .item-chk').click();})()")
        await asyncio.sleep(0.5)
        await ev("document.getElementById('chkModeBtn').click()")
        await asyncio.sleep(2.5)
        await pick_board()
        r8 = await ev("""(function(){
          return {col:document.querySelectorAll('#boardContent .col-chk').length,
                  item:document.querySelectorAll('#boardContent .item-chk').length,
                  itemSet:JSON.parse(sessionStorage.getItem('itemChk_admin')||'[]'),
                  colSet:JSON.parse(sessionStorage.getItem('colChk_admin')||'[]'),
                  btn:document.getElementById('chkModeBtn').textContent};
        })()""")
        print('  ', json.dumps(r8, ensure_ascii=False), flush=True)
        ok(r8.get('col') == 0 and r8.get('item') == 0, '勾选框全部消失')
        ok(len(r8.get('itemSet') or []) == 0 and len(r8.get('colSet') or []) == 0, '勾选记录已清空')
        ok(r8.get('btn') == '启用勾选', '关闭后按钮回到「启用勾选」动作')
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
