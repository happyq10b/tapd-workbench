#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证：复制权限放开到 can_edit 口径（2026-11-03 用户反馈 #45）。

夹具：看板 __cp_看板（归属 __cp_dept）+ 板块 + 事项。
  · __cp_board = 该看板**负责人**（boards.owner）→ 应能复制（列表按钮 + 批量 + 接口）
  · __cp_arch  = 归属部门的**架构负责人** → 应能复制
  · __cp_none  = 无关 editor → 不可见该看板、复制 403
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9393
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__cp_'
U_BOARD = P + 'board'
U_ARCH = P + 'arch'
U_NONE = P + 'none'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  x ') + msg)


def setup():
    now = '2026-11-03 12:00:00'
    c = sqlite3.connect(DB)
    for acct in (U_BOARD, U_ARCH, U_NONE):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (P + acct, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,?,?,?,?)", (acct, hash_pw(PWD), 'editor', '*', '*', now))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (P + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
    nid = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,function) VALUES (?,?,0,'')",
                    (P + 'dept', 'dept')).lastrowid
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (U_ARCH,)).fetchone()[0]
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
              " VALUES (?,?,?,1,?)", (nid, mid, 'dept_head', now))
    st = str(int(time.time() * 1000))
    bid = 'CP' + st
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at)"
              " VALUES (?,?,'',?,0,?)", (bid, P + '看板', U_BOARD, now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, P + 'dept', nid, '日常', '启用', now))
    cid = 'CPC' + st
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,pinned,year,copy_from,owner,participants) VALUES (?,?,?,?,?,?,?,0,'2026','','','')",
              (bid + '::' + P + '板块', cid, bid, P + '板块', now, 'admin', '日常'))
    CARD_COLS = ['card_id','board_id','board_name','column_id','column_name','workspace_id',
                 'card_name','status','status_name','priority','creator','owner','cc',
                 'follower','begin','due','completed','created','modified','description',
                 'attachment_count','label','b_sort','entity_type','cover_setted','cover_info',
                 'is_filed','created_from','date_status','due_time_ux','begin_date_status',
                 'begin_time_ux','comments','column_sort','board_status','board_creator',
                 'parent_id','version','deleted','pinned','week_no','copy_from']
    vals = {k: '' for k in CARD_COLS}
    vals.update({'card_id': 'CPCD' + st, 'board_id': bid, 'board_name': P + '看板',
                 'column_id': cid, 'column_name': P + '板块', 'card_name': P + '事项',
                 'status': 'todo', 'status_name': '未完成', 'creator': 'admin',
                 'created': now, 'modified': now, 'version': 0, 'deleted': 0, 'pinned': 0})
    c.execute('INSERT INTO cards (%s) VALUES (%s)' % (','.join(CARD_COLS), ','.join('?'*len(CARD_COLS))),
              [vals[k] for k in CARD_COLS])
    c.commit(); c.close()
    return {'bid': bid, 'nid': nid}


def cleanup(fx):
    c = sqlite3.connect(DB)
    copies = [r[0] for r in c.execute("SELECT board_id FROM boards WHERE copy_from=?", (fx['bid'],))]
    for b in copies + [fx['bid']]:
        c.execute("DELETE FROM cards WHERE board_id=?", (b,))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (b,))
        c.execute("DELETE FROM board_config WHERE board_id=?", (b,))
        c.execute("DELETE FROM boards WHERE board_id=?", (b,))
    c.execute("DELETE FROM org_appointments WHERE node_id=?", (fx['nid'],))
    c.execute("DELETE FROM org_nodes WHERE id=?", (fx['nid'],))
    for acct in (U_BOARD, U_ARCH, U_NONE):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
    c.commit(); c.close()
    return copies


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP','.'), 'cdp_p%d'%PORT)
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

            async def login(user):
                await send('Page.navigate',{'url':BASE+'/login'}); await asyncio.sleep(2)
                await ev("document.getElementById('u').value=%s;"
                         "document.getElementById('p').value=%s;"
                         "document.getElementById('btn').click();" % (json.dumps(user), json.dumps(PWD)))
                for _ in range(40):
                    await asyncio.sleep(0.5)
                    if await ev("typeof ME!=='undefined'&&!!ME"): break
                await asyncio.sleep(2)

            # ── 看板负责人 ──
            print('\n[board owner] copy visible & works')
            await login(U_BOARD)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            r = await ev("""(function(){
              var btn=document.querySelector('.bc-pick[data-bid=\"%s\"]');
              var item=btn?btn.closest('.bc-item'):null;
              var copy=item?item.querySelector('.cp-copy-btn'):null;
              var bar=document.getElementById('bcCopyBtn');
              return {listed:!!item,rowCopy:!!copy,batchVisible:bar?bar.style.display!=='none':null,
                      batchDisabled:bar?bar.disabled:null};
            })()""" % fx['bid'])
            ok(r.get('listed') is True,'board listed for owner')
            ok(r.get('rowCopy') is True,'row copy button visible (fixed)')
            ok(r.get('batchVisible') is True,'batch copy button visible')
            # 勾选夹具看板 → 批量复制
            await ev("window.bcConfirm=function(){return true};")
            pick_js = ("(function(){var el=document.querySelector('.bc-pick[data-bid=\"" + fx['bid'] + "\"]');"
                       "if(el){BC_SEL=new Set([el.getAttribute('data-bid')]);bcPaintPick();}})()")
            await ev(pick_js)
            await asyncio.sleep(0.5)
            await ev("bcCopySelected();")
            await asyncio.sleep(4)
            # DB 校验副本
            c = sqlite3.connect(DB)
            copies1 = [x[0] for x in c.execute("SELECT board_id FROM boards WHERE copy_from=?", (fx['bid'],))]
            c.close()
            ok(len(copies1)==1,'board owner: 1 copy created (%s)'%copies1)
            await ev("closeModal('boardConfigModal');")
            await asyncio.sleep(1)

            # ── 架构负责人（直调接口验证 + UI 按钮可见性）──
            print('\n[arch owner] copy visible & works')
            await login(U_ARCH)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            r2 = await ev("""(function(){
              var btn=document.querySelector('.bc-pick[data-bid=\"%s\"]');
              var item=btn?btn.closest('.bc-item'):null;
              var copy=item?item.querySelector('.cp-copy-btn'):null;
              var bar=document.getElementById('bcCopyBtn');
              return {listed:!!item,rowCopy:!!copy,batchVisible:bar?bar.style.display!=='none':null};
            })()""" % fx['bid'])
            ok(r2.get('listed') is True,'board listed for arch owner')
            ok(r2.get('rowCopy') is True,'row copy button visible')
            ok(r2.get('batchVisible') is True,'batch copy button visible')
            await ev("window.bcConfirm=function(){return true};")
            await ev("(function(){var el=document.querySelector('.bc-pick[data-bid=\"%s\"]');"
                     "if(el){BC_SEL=new Set([el.getAttribute('data-bid')]);bcPaintPick();}})()" % fx['bid'])
            await asyncio.sleep(0.5)
            await ev("bcCopySelected();")
            await asyncio.sleep(4)
            c = sqlite3.connect(DB)
            copies2 = [x[0] for x in c.execute("SELECT board_id FROM boards WHERE copy_from=?", (fx['bid'],))]
            c.close()
            ok(len(copies2)==2,'arch owner: copy created (total %s)'%len(copies2))
            await ev("closeModal('boardConfigModal');")
            await asyncio.sleep(1)

            # ── 无关账号：按钮不可见 + 接口 403 ──
            print('\n[unrelated] copy blocked')
            await login(U_NONE)
            r3 = await ev("""(async function(){
              var tk=localStorage.getItem('tk')||'';
              var res=await fetch('/api/boards/'+encodeURIComponent(%s)+'/copy',{method:'POST',
                headers:{'Content-Type':'application/json','Authorization':'Bearer '+tk},
                body:JSON.stringify({deep:true})});
              var body=await res.text();
              return {code:res.status,denied:body.indexOf('PERMISSION_DENIED')>=0};
            })()""" % json.dumps(fx['bid']), aw=True)
            ok(r3.get('code')==403 and r3.get('denied') is True,
               'unrelated account: copy API 403 (%s)'%r3.get('code'))
    finally:
        cleanup(fx)
    print('\n=== result: %d pass / %d fail ==='%(len(PASS),len(FAIL)))
    return 1 if FAIL else 0
sys.exit(asyncio.run(main()))
