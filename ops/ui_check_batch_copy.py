#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证：看板管理批量复制（勾选 → 复制按钮 → 整套副本）。
  造 1 个带板块+事项的夹具看板 → 勾选 → 点「复制」→ 确认 →
  断言副本出现（含板块/事项）、勾选清空、未勾选时按钮禁用。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9389
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  x ') + msg)


def setup():
    now = '2026-11-03 12:00:00'
    c = sqlite3.connect(DB)
    st = str(int(time.time() * 1000))
    bid = 'BC' + st
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at)"
              " VALUES (?,?,'','',0,?)", (bid, '__bcc_看板', now))
    dept = c.execute("SELECT id,name FROM org_nodes WHERE node_type='dept' ORDER BY id LIMIT 1").fetchone()
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, dept[1], dept[0], '日常', '启用', now))
    cid = 'BCC' + st
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,pinned,year,copy_from,owner,participants) VALUES (?,?,?,?,?,?,?,0,'2026','','','')",
              (bid + '::__bcc_板块', cid, bid, '__bcc_板块', now, 'admin', '日常'))
    card = 'BCCD' + st
    CARD_COLS = ['card_id','board_id','board_name','column_id','column_name','workspace_id',
                 'card_name','status','status_name','priority','creator','owner','cc',
                 'follower','begin','due','completed','created','modified','description',
                 'attachment_count','label','b_sort','entity_type','cover_setted','cover_info',
                 'is_filed','created_from','date_status','due_time_ux','begin_date_status',
                 'begin_time_ux','comments','column_sort','board_status','board_creator',
                 'parent_id','version','deleted','pinned','week_no','copy_from']
    vals = {k: '' for k in CARD_COLS}
    vals.update({'card_id': card, 'board_id': bid, 'board_name': '__bcc_看板',
                 'column_id': cid, 'column_name': '__bcc_板块', 'card_name': '__bcc_事项',
                 'status': 'todo', 'status_name': '未完成', 'creator': 'admin',
                 'created': now, 'modified': now, 'version': 0, 'deleted': 0, 'pinned': 0})
    c.execute('INSERT INTO cards (%s) VALUES (%s)' % (','.join(CARD_COLS), ','.join('?'*len(CARD_COLS))),
              [vals[k] for k in CARD_COLS])
    c.commit(); c.close()
    return {'bid': bid, 'card': card}


def cleanup(fx):
    c = sqlite3.connect(DB)
    copies = [r[0] for r in c.execute("SELECT board_id FROM boards WHERE copy_from=?", (fx['bid'],))]
    for b in copies + [fx['bid']]:
        c.execute("DELETE FROM cards WHERE board_id=?", (b,))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (b,))
        c.execute("DELETE FROM board_config WHERE board_id=?", (b,))
        c.execute("DELETE FROM boards WHERE board_id=?", (b,))
    c.commit(); c.close()
    return copies


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP','.'), 'cdp_c%d'%PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run',
        '--remote-debugging-port=%d'%PORT,'--user-data-dir='+profile,'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version'%PORT,timeout=2) as r:
                json.loads(r.read()); break
        except Exception: time.sleep(0.5)
    import websockets
    targets=json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json'%PORT,timeout=5).read())
    ws=[t['webSocketDebuggerUrl'] for t in targets if t.get('type')=='page'][0]
    copies = []
    try:
        async with websockets.connect(ws,max_size=30*1024*1024) as ws_:
            i=0
            async def send(m,p=None):
                nonlocal i; i+=1; mid=i
                await ws_.send(json.dumps({'id':mid,'method':m,'params':p or {}}))
                while True:
                    msg=json.loads(await ws_.recv())
                    if msg.get('id')==mid: return msg.get('result',{})
            async def ev(e,aw=False):
                r=await send('Runtime.evaluate',{'expression':e,'returnByValue':True,'awaitPromise':aw})
                if r.get('exceptionDetails'): return {'__error__':str(r['exceptionDetails'])[:300]}
                return r.get('result',{}).get('value')
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',{'width':1600,'height':1000,'deviceScaleFactor':1,'mobile':False})
            await send('Page.navigate',{'url':BASE+'/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(2)

            print('\n[1] button present & disabled initially')
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            r = await ev("""(function(){
              var b=document.getElementById('bcCopyBtn');
              return {present:!!b,disabled:b?b.disabled:null,visible:b?b.style.display!=='none':null};
            })()""")
            ok(r.get('present') is True,'copy button in opbar')
            ok(r.get('visible') is True,'admin: visible')
            ok(r.get('disabled') is True,'nothing checked -> disabled')

            print('\n[2] check fixture board -> enabled -> copy')
            # 覆盖 confirm 自动确认
            await ev("window.bcConfirm=function(){return true};")
            # ⚠️ 按 data-bid 精确勾选**夹具**看板 ——
            #    上一版取列表第一个勾选框，勾到的是排序第一的**生产看板**，
            #    复制的也是生产看板（还污染了生产库，已手工清理）。
            pick_js = ("(function(){"
                       "var el=document.querySelector('.bc-pick[data-bid=\"" + fx['bid'] + "\"]');"
                       "if(el){BC_SEL=new Set([el.getAttribute('data-bid')]);bcPaintPick();}"
                       "})()")
            await ev(pick_js)
            await asyncio.sleep(1)
            r2 = await ev("(function(){var b=document.getElementById('bcCopyBtn');return {disabled:b.disabled,n:BC_SEL.size};})()")
            ok(r2.get('n',0)>=1,'checked %s board(s)'%r2.get('n'))
            ok(r2.get('disabled') is False,'enabled after checking')
            before = await ev("BC_BOARDS.length")
            await ev("bcCopySelected();")
            await asyncio.sleep(4)
            r3 = await ev("""(function(){
              var copies=(BC_BOARDS||[]).filter(function(b){return b.board_name&&b.board_name.indexOf('__bcc_看板')===0&&b.copy_of!==undefined});
              var named=(BC_BOARDS||[]).filter(function(b){return (b.board_name||'').indexOf('__bcc_看板')===0;});
              return {total:BC_BOARDS.length,named:named.length,sel:BC_SEL.size,
                      copyBtnDisabled:document.getElementById('bcCopyBtn').disabled};
            })()""")
            ok(r3.get('named',0)>=2,'copy appears in list (%s named __bcc_看板)'%r3.get('named'))
            ok(r3.get('sel',1)==0,'selection cleared')
            # 副本内容校验（数据库）
            await asyncio.sleep(1)
        # DB 校验
        c = sqlite3.connect(DB)
        copies = [r[0] for r in c.execute("SELECT board_id FROM boards WHERE copy_from=?", (fx['bid'],))]
        ok(len(copies)==1,'exactly 1 copy created (%s)'%copies)
        if copies:
            nb = copies[0]
            ncols = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id=?", (nb,)).fetchone()[0]
            ncards = c.execute("SELECT COUNT(*) FROM cards WHERE board_id=? AND deleted=0", (nb,)).fetchone()[0]
            ok(ncols==1 and ncards==1,'copy contains 1 column + 1 card (%s/%s)'%(ncols,ncards))
            src_card = c.execute("SELECT owner,week_no FROM cards WHERE card_id=?", (fx['card'],)).fetchone()
            cp_card = c.execute("SELECT status,creator,copy_from FROM cards WHERE board_id=? AND deleted=0", (nb,)).fetchone()
            ok(cp_card and cp_card[0]=='todo','copy card status reset to todo')
            ok(cp_card and cp_card[2]==fx['card'],'copy card copy_from traced')
        c.close()
    finally:
        cleanup(fx)
    print('\n=== result: %d pass / %d fail ==='%(len(PASS),len(FAIL)))
    return 1 if FAIL else 0
sys.exit(asyncio.run(main()))
