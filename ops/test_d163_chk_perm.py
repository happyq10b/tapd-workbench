# -*- coding: utf-8 -*-
"""#163 勾选权限三级 CDP 实测：超管全可用 / 事项负责人仅自己的 / 无权限全禁用"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw
BASE = 'http://127.0.0.1:8100'
PORT = 9459
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m, flush=True)

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM cards WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_pm%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_pm%'")
    c.execute("INSERT INTO boards (board_id,board_name,sort,created_at) VALUES ('__t_pm_b','__t_权限测试看板',0,datetime('now'))")
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_pm_b::__t_板块P','COLpm1','__t_pm_b','__t_板块P',date('now'),'admin','日常','2026',0,'','','open','')")
    # c1/c3 负责人=__t_pm成员（负责人视角可勾）；c2 无负责人（对负责人视角禁用）
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_pm_c1','__t_pm_b','__t_权限测试看板','__t_板块P','__t_事项1','open','__t_pm成员',datetime('now'),0,0,'')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_pm_c2','__t_pm_b','__t_权限测试看板','__t_板块P','__t_事项2','open','',datetime('now'),0,0,'')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_pm_c3','__t_pm_b','__t_权限测试看板','__t_板块P','__t_事项3','open','__t_pm成员',datetime('now'),0,0,'')")
    c.execute("INSERT INTO team_members (id,name,workgroups,account) VALUES "
              "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_pm成员','','__t_pm_v')")
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_pm_v',?,'viewer','__t_pm_b')", (hash_pw('Pm123456'),))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_pm_n',?,'viewer','__t_pm_b')", (hash_pw('Pm123456'),))
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_pm_b'").fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM boards WHERE board_id='__t_pm_b'").fetchone()[0]
    n3 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t_pm%'").fetchone()[0]
    print('SETUP-DB-CHECK: cards=%d boards=%d users=%d' % (n1, n2, n3), flush=True)
    c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_pm_b'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_pm%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_pm%'")
    c.commit(); c.close()

async def login_and_measure(ev, user, tk, mode_on):
    """注入 tk cookie → 整页进应用 → 等就绪 → 开勾选模式 → 选板 → 返回三级勾选框状态"""
    import urllib.parse as _up
    cookie = 'tk=' + _up.quote(tk)
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='%s'" % user)
        if r is True:
            ok_login = True
            break
    if not ok_login:
        snap = await ev("({u:!!document.getElementById('u'),api:typeof api,me:typeof ME,url:location.href,meName:(typeof ME!=='undefined'&&ME)?ME.username:''})")
        return {'__login_failed__': user, 'snap': snap}
    await asyncio.sleep(1.5)
    if mode_on:
        await ev("(function(){if(!CHK_MODE)document.getElementById('chkModeBtn').click();})()")
    else:
        await ev("(function(){if(CHK_MODE)document.getElementById('chkModeBtn').click();})()")
    await asyncio.sleep(2.5)
    await ev("(function(){if(!curBoards.has('__t_pm_b'))pickBoard('__t_pm_b');})()")
    # 轮询等渲染完成（板块勾选框或空态出现）
    for _ in range(20):
        await asyncio.sleep(0.5)
        r = await ev("document.querySelector('#boardContent .col-chk')||document.querySelector('#boardContent .empty')")
        if r is True or isinstance(r, str): break
    await asyncio.sleep(0.5)
    return await ev("""(async function(){
      const d=await api('/api/cards?board_ids=__t_pm_b').catch(function(e){return {err:e.message}});
      const col=document.querySelector('#boardContent .col-chk');
      const items=[...document.querySelectorAll('#boardContent .item-chk')];
      const st=function(x){return x?{dis:x.disabled,checked:x.checked}:null;};
      return {col:st(col),
              dbg:{cur:[...curBoards], mode:CHK_MODE,
                   apiTotal:d.total!==undefined?d.total:('ERR:'+(d.err||'?')),
                   apiCols:(d.columns||[]).length,
                   dom:(document.getElementById('boardContent')||{innerHTML:''}).innerHTML.slice(0,80)},
              items:items.map(function(x){const id=x.dataset.ck;
                return {id:id.slice(-2),dis:x.disabled,checked:x.checked};})};
    })()""", aw=True)

setup()   # #163 夹具：看板+板块+3 事项+两个测试账号（此前漏调用导致接口空数据假失败）
try:
    async def main():
        import websockets
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d163')
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
            if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:250]}
            return r.get('result', {}).get('value')
        rt = asyncio.create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)

        # #163 参数化：单用户单轮运行（跨用户 logout 往返在 CDP 下不可靠）
        import os as _os
        who = _os.environ.get('CHK_USER', 'admin')
        uname = {'admin':'admin','v':'__t_pm_v','n':'__t_pm_n'}[who]
        tkmap = {'admin':'admin','v':'__t_pm_v','n':'__t_pm_n'}
        r1 = await login_and_measure(ev, uname, make_token(tkmap[who]), True)
        print('MEASURE:', json.dumps(r1, ensure_ascii=False), flush=True)
        if who == 'admin':
            ok(r1.get('col') and not r1['col']['dis'], '板块勾选框可用')
            ok(all(not it['dis'] for it in (r1.get('items') or [])), '全部事项勾选框可用')
        elif who == 'v':
            ok(r1.get('col') and r1['col']['dis'], '板块勾选框灰色禁用')
            it2 = {it['id']: it for it in (r1.get('items') or [])}
            ok(it2.get('c1', {}).get('dis') is False and it2.get('c3', {}).get('dis') is False, '自己负责的事项（c1/c3）可勾')
            ok(it2.get('c2', {}).get('dis') is True, '无负责人事项（c2）灰色禁用')
            await ev("(function(){const x=[...document.querySelectorAll('#boardContent .item-chk')].find(function(i){return !i.disabled});if(x)x.click();})()")
            await asyncio.sleep(0.5)
            await ev("document.getElementById('chkAllBtn').click()")
            await asyncio.sleep(0.8)
            r4 = await ev("(function(){return {n:[...ITEM_CHECKED].length, has2:[...ITEM_CHECKED].some(function(id){return id.indexOf('__t_pm_c2')>=0}), toasts:[...document.querySelectorAll('.toast')].map(function(x){return x.textContent})};})()")
            print('R4:', json.dumps(r4, ensure_ascii=False), flush=True)
            ok(r4.get('n') == 2 and not r4.get('has2'), '全选当前只勾有权的 2 个（无权项跳过）')
        else:
            ok(r1.get('col') and r1['col']['dis'], '板块勾选框禁用')
            ok(all(it['dis'] for it in (r1.get('items') or [])), '全部事项勾选框禁用')
    asyncio.run(main())
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)), flush=True)
finally:
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], capture_output=True)
    except Exception:
        pass
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_pm_b'").fetchone()[0]
    c.close()
    print('夹具残留 cards=%d' % n)
