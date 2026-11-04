# -*- coding: utf-8 -*-
"""#47 UI 实测：新增节点按钮 / 结构字段 / 绑定池过滤 / 绑定保存走专项接口。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9417
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__bu_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    from app.app import hash_pw
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 11:00:00'
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    # 账号：admin 用生产 admin；部门长自建
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + 'dept', PREFIX + 'dept', now))
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (PREFIX + 'dept',)).fetchone()[0]
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
              (PREFIX + 'dept', hash_pw(PWD), 'editor', '*', '*', now))
    # 节点 D→G
    wD = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','','')", (PREFIX + 'D',)).lastrowid
    wG = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,?,?,'','')", (PREFIX + 'G', wD, PREFIX + 'dept')).lastrowid
    nD = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'D', 'dept', 0, wD)).lastrowid
    nG = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'G', 'group', nD, wG)).lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wD, wG))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nD, mid, 'dept_head', now))
    # 看板：B_own（负责人=部门长）、B_for（无关系，但 D 范围内）
    b_own, b_for = PREFIX + 'B_own', PREFIX + 'B_for'
    b_free = PREFIX + 'B_free'   # 既非我、也从未绑定 → 必须被排除出候选池
    for bid, owner in ((b_own, PREFIX + 'dept'), (b_for, 'someone_else'), (b_free, 'someone_else')):
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, bid, '', owner, now))
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
                  (bid + '::C1', bid + 'col', bid, 'C1', now))
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (b_own + ',' + b_for + ',' + b_free, wD))
    # G 已绑定：B_own（负责人自己的）+ B_for（**管理员绑的**，部门长既非负责人也非参与人
    # → 用于验证「已绑定」标记与保存时不被误清）
    c.execute("UPDATE workgroups SET boards=? WHERE id=?", (b_own + ',' + b_for, wG))
    c.commit(); c.close()
    return {'nD': nD, 'nG': nG, 'wG': wG, 'b_own': b_own, 'b_for': b_for, 'b_free': b_free}

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
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_bu%d' % PORT)
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
            async def login(u, p):
                await send('Page.enable'); await send('Runtime.enable')
                await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
                await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;document.getElementById('btn').click();"
                         % (json.dumps(u), json.dumps(p)))
                for _ in range(40):
                    await asyncio.sleep(0.5)
                    if await ev("typeof ME!=='undefined'&&!!ME"): break
                await asyncio.sleep(2)
                await ev("openWgModal();")
                await asyncio.sleep(2)

            # ── 部门长视角 ──
            print('\n【部门长】' + PREFIX + 'dept')
            await login(PREFIX + 'dept', PWD)
            r = await ev("""(function(){
              var addBtn=document.getElementById('g_add_node_btn');
              return {addVisible:!!addBtn&&addBtn.style.display!=='none'};
            })()""")
            ok(r.get('addVisible') is False, '「＋ 新增节点」按钮不可见')
            # 选中小组 G
            await ev("(function(){var el=document.querySelector('.org-node-row[data-org-id=\"%d\"]');if(el&&el.click)el.click();})()" % fx['nG'])
            await asyncio.sleep(1)
            r = await ev("""(function(){
              return {nameRo:document.getElementById('g_new_name').disabled,
                      typeRo:document.getElementById('g_new_type').disabled,
                      parentRo:document.getElementById('g_new_parent').disabled,
                      pool:[].slice.call(document.querySelectorAll('.g_brd_chk')).map(function(c){
                        var lb=c.closest('label');
                        return {id:c.value,checked:c.checked,disabled:c.disabled,
                                boundTag:lb.textContent.indexOf('已绑定')>=0};}),
                      hint:(document.getElementById('g_boards_hint')||{}).textContent||''};
            })()""")
            ok(r.get('nameRo') is True and r.get('typeRo') is True and r.get('parentRo') is True,
               '结构字段（名称/类型/上级）已禁用')
            pool = r.get('pool') or []
            ids = [x['id'] for x in pool]
            ok(fx['b_own'] in ids, '候选池含【我是负责人】的看板')
            ok(fx['b_free'] not in ids, '候选池不含【既非我、也未绑定】的看板（B_for 在池里是因已绑定，符合设计）')
            own = [x for x in pool if x['id'] == fx['b_own']][0] if pool else {}
            ok(own.get('checked') is True, '我的已绑项勾选且无「已绑定」标记：%s' % own)
            foreign = [x for x in pool if x['id'] == fx['b_for']][0] if pool else {}
            ok(foreign and foreign.get('checked') is True and foreign.get('boundTag') is True,
               '管理员绑的「非我」看板：保留显示 + 「已绑定」标记 + 勾选')
            ok('负责人或参与人' in (r.get('hint') or ''), '提示说明新口径：%s' % r.get('hint'))
            # 勾选 B_own 保持 + 保存 → 专项接口落库
            before = sqlite3.connect(DB).execute("SELECT boards FROM workgroups WHERE id=?", (fx['wG'],)).fetchone()[0]
            await ev("(function(){window.bcConfirm=function(){return true};})()")
            await ev("submitWgForm();")
            await asyncio.sleep(3)
            after = sqlite3.connect(DB).execute("SELECT boards FROM workgroups WHERE id=?", (fx['wG'],)).fetchone()[0]
            ok(sorted(after.split(',')) == sorted([fx['b_own'], fx['b_for']]),
               '绑定保存落库且管理员已绑项不被误清（%s → %s）' % (before, after))

            # ── 管理员视角 ──
            print('\n【管理员】admin')
            await login('admin', PWD)
            r = await ev("(function(){var b=document.getElementById('g_add_node_btn');return {addVisible:!!b&&b.style.display!=='none'}})()")
            ok(r.get('addVisible') is True, '「＋ 新增节点」按钮可见')
            await ev("(function(){var el=document.querySelector('.org-node-row[data-org-id=\"%d\"]');if(el&&el.click)el.click();})()" % fx['nG'])
            await asyncio.sleep(1)
            r = await ev("""(function(){
              return {nameRo:document.getElementById('g_new_name').disabled,
                      pool:[].slice.call(document.querySelectorAll('.g_brd_chk')).map(function(c){return c.value})};
            })()""")
            ok(r.get('nameRo') is False, '管理员结构字段可编辑')
            ok(fx['b_for'] in (r.get('pool') or []), '管理员候选池不受限制（含无关系看板）')
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
