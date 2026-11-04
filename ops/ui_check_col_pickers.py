# -*- coding: utf-8 -*-
"""#48 UI 实测：新建/编辑板块的负责人与参与人选择器（部门长视角）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9439
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__ac_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    from app.app import hash_pw
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 12:30:00'
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + 'dept', PREFIX + 'dept', now))
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (PREFIX + 'dept',)).fetchone()[0]
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
              (PREFIX + 'dept', hash_pw(PWD), 'editor', '*', '*', now))
    wC = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','','*')", (PREFIX + 'C',)).lastrowid
    wD = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,?,?,'','')", (PREFIX + 'D', wC, PREFIX + 'dept')).lastrowid
    nC = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'C', 'center', 0, wC)).lastrowid
    nD = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'D', 'dept', nC, wD)).lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wC, wD))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nD, mid, 'dept_head', now))
    bid = PREFIX + 'B1'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, PREFIX + '看板', '', PREFIX + 'dept', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
              (bid + '::编辑组', PREFIX + 'col1', bid, '编辑组', now))
    # ⚠️ 板块下放一张卡：默认「2026 年」chip 激活筛选 → 空板块整块隐藏（#46 语义），
    #    没有这张卡 .week-title 根本渲染不出来，编辑断言会落空。
    c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,creator,created,modified,week_no,deleted,parent_id)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'')""",
              (PREFIX + 'K1', bid, PREFIX + '看板', PREFIX + 'col1', '编辑组', PREFIX + '卡1', 'open', PREFIX + 'dept', now, now, '2026年第45周'))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,?,?,?,'',?)", (bid, PREFIX + 'D', nD, '日常', '启用', now))
    c.commit(); c.close()
    return {'bid': bid, 'nD': nD}

def cleanup(fx):
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.commit(); c.close()

async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_ac%d' % PORT)
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
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;document.getElementById('btn').click();"
                     % (json.dumps(PREFIX + 'dept'), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(2)

            # ── 新建板块 ──
            print('\n【新建板块】部门长视角')
            await ev("openColumnModal();")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              return {ownerWrap:document.getElementById('c_owner_wrap').style.display!=='none',
                      ownerPick:document.getElementById('c_owner_pick_btn').style.display!=='none',
                      partsPick:document.getElementById('c_parts_pick_btn').style.display!=='none'};
            })()""")
            ok(r.get('ownerWrap') is True, '「板块负责人」区块显示（不再整块隐藏）')
            ok(r.get('ownerPick') is True, '「🌳 选择负责人」按钮可见')
            ok(r.get('partsPick') is True, '「🌳 选择参与人」按钮可见')
            # 选负责人并创建（模拟：直接设 COL_OWNER 走保存，树选人交互由 colPickOwner 覆盖）
            await ev("COL_OWNER=%s;colRenderOwner();" % json.dumps(PREFIX + 'dept'))
            await ev("COL_PARTS=[%s];colRenderParticipants();" % json.dumps(PREFIX + 'dept'))
            await ev("document.getElementById('c_name').value=%s;saveColumn();" % json.dumps(PREFIX + '新板块'))
            await asyncio.sleep(2.5)
            c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
            row = c.execute("SELECT col_key, owner, participants FROM board_columns WHERE board_id=? AND column_name=?",
                            (fx['bid'], PREFIX + '新板块')).fetchone()
            c.close()
            ok(bool(row), '新建板块已落库')
            ok(row and row['owner'] == PREFIX + 'dept', '新建板块负责人落库（修复 create 无负责人入口）：%s' % (row and row['owner']))
            ok(row and PREFIX + 'dept' in (row['participants'] or ''), '新建板块参与人落库')

            # ── 编辑板块 ──
            print('\n【编辑板块】部门长视角')
            # ⚠️ 必须先选中看板渲染出板块标题，否则 .week-title 不存在 →
            #    openColumnEdit 没跑，断言落在 create 弹窗残留态上（假通过）。
            #    直接赋 curBoard 不走完整渲染链路 → 点真实看板 tab。
            await ev("""(function(){
              var tabs=document.querySelectorAll('#tbBoards [data-bid], .tb-board [data-bid], #tbBoards button, .tb-board button');
              for(var i=0;i<tabs.length;i++){
                if(tabs[i].getAttribute('data-bid')===%s||tabs[i].textContent.indexOf('看板')>=0){tabs[i].click();return 'clicked'}
              }
              return 'notfound:'+tabs.length;
            })()""" % json.dumps(fx['bid']))
            await asyncio.sleep(3)
            r0 = await ev("document.querySelectorAll('.week-title.edit').length + '/' + (curBoard||'')")
            ok(str(r0).split('/')[0] not in ('0', '') and r0, '看板已选中并渲染出板块标题（%s）' % r0)
            await ev("""(function(){
              var t=[].slice.call(document.querySelectorAll('.week-title.edit'))
                     .find(function(x){return x.textContent.indexOf('编辑组')>=0});
              if(t)openColumnEdit(t);
            })()""")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              return {ownerPick:document.getElementById('c_owner_pick_btn').style.display!=='none',
                      partsPick:document.getElementById('c_parts_pick_btn').style.display!=='none',
                      ownerBox:(document.getElementById('c_owner_box')||{}).textContent||''};
            })()""")
            ok(r.get('ownerPick') is True, '编辑板块「选择负责人」按钮可见')
            ok(r.get('partsPick') is True, '编辑板块「选择参与人」按钮可见')
            # 改负责人并保存
            await ev("COL_OWNER=%s;colRenderOwner();saveColumn();" % json.dumps(PREFIX + 'dept'))
            await asyncio.sleep(2.5)
            c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
            row = c.execute("SELECT owner, participants FROM board_columns WHERE board_id=? AND column_name='编辑组'", (fx['bid'],)).fetchone()
            c.close()
            ok(row and row['owner'] == PREFIX + 'dept', '编辑板块负责人保存落库：%s' % (row and row['owner']))
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
