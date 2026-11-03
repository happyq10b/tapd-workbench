#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证：架构负责人在看板管理里能看到「选择负责人」按钮（用户反馈 #43）。

场景：架构负责人（__ow_arch，dept_a 部门长）+ 归属 dept_a 的看板。
  · 编辑区身份行 = 架构负责人 · 可改基本信息并指定负责人
  · 页脚「保存负责人」可见（can_assign_owner）
  · 负责人区块「🌳 选择负责人」按钮可见（canSetOwner ← can_assign_owner）——本次修复点
  · 只读账号：两个按钮都不可见
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9381
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__ow_'
U_ARCH = P + 'arch'
U_VIEWER = P + 'viewer'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  x ') + msg)


def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-03 12:00:00'
    for acct, role in ((U_ARCH, 'editor'), (U_VIEWER, 'viewer')):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (P + acct, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,?,?,?,?)", (acct, hash_pw(PWD), role, '*', '*', now))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (P + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (P + '%',))
    nid = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,function) VALUES (?,?,0,'')",
                    (P + 'dept', 'dept')).lastrowid
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (U_ARCH,)).fetchone()[0]
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
              " VALUES (?,?,?,1,?)", (nid, mid, 'dept_head', now))
    bid = 'OW' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at)"
              " VALUES (?,?,'','',0,?)", (bid, P + '看板', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, P + 'dept', nid, '日常', '启用', now))
    c.commit(); c.close()
    return {'bid': bid, 'nid': nid}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        c.execute("DELETE FROM board_config WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM boards WHERE board_id=?", (fx['bid'],))
        c.execute("DELETE FROM org_appointments WHERE node_id=?", (fx['nid'],))
        c.execute("DELETE FROM org_nodes WHERE id=?", (fx['nid'],))
    for acct in (U_ARCH, U_VIEWER):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
    c.commit(); c.close()


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP','.'), 'cdp_o%d'%PORT)
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

            # ── 架构负责人 ──
            print('\n[arch owner] pick-owner button visible')
            await login(U_ARCH)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            await ev("(function(){var it=document.querySelector('#bcList .bc-item');if(it)it.click();})()")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              var secs=[].slice.call(document.querySelectorAll('#bcEditArea .bc-section'));
              var sec=null;
              secs.forEach(function(x){var l=x.querySelector('.lab');if(l&&l.textContent==='看板负责人')sec=x;});
              if(!sec)return {found:false};
              return {found:true,
                      pick:!!sec.querySelector('button[onclick*="bcPickOwner"]'),
                      roleNote:(document.querySelector('#bcEditArea .bc-hint b')||{}).textContent||'',
                      saveAcl:!!document.querySelector('button[onclick*="saveBoardAcl"]')};
            })()""")
            ok(isinstance(r,dict) and r.get('found') is True,'owner section rendered')
            ok(isinstance(r,dict) and r.get('roleNote')=='架构负责人',
               'identity note = 架构负责人 (%s)'%r.get('roleNote'))
            ok(isinstance(r,dict) and r.get('saveAcl') is True,'footer save-owner button visible')
            ok(isinstance(r,dict) and r.get('pick') is True,
               '「选择负责人」button VISIBLE (fixed)')

            # ── 只读 ──
            print('\n[viewer] both buttons hidden')
            await ev("closeModal('boardConfigModal');")
            await asyncio.sleep(1)
            await login(U_VIEWER)
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2)
            r2 = await ev("""(function(){
              var secs=[].slice.call(document.querySelectorAll('#bcEditArea .bc-section'));
              var sec=null;
              secs.forEach(function(x){var l=x.querySelector('.lab');if(l&&l.textContent==='看板负责人')sec=x;});
              return {pick:sec?!!sec.querySelector('button[onclick*="bcPickOwner"]'):null,
                      saveAcl:!!document.querySelector('button[onclick*="saveBoardAcl"]')};
            })()""")
            ok(isinstance(r2,dict) and not r2.get('pick'),'viewer: pick button hidden (or modal blocked)')
            ok(isinstance(r2,dict) and r2.get('saveAcl') is False,'viewer: save-owner hidden')
            await ev("closeModal('boardConfigModal');")
    finally:
        cleanup(fx)
    print('\n=== result: %d pass / %d fail ==='%(len(PASS),len(FAIL)))
    return 1 if FAIL else 0
sys.exit(asyncio.run(main()))
