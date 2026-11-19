# -*- coding: utf-8 -*-
"""T-0172 架构管理：人数去重统计 + 组长/组员兼任拦截 CDP 实测。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse, urllib.error

BASE = 'http://127.0.0.1:8100'
PORT = 9474
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []
NID = {'v': 0}

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

def setup():
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.row_factory = sqlite3.Row
    center = c.execute("SELECT id FROM org_nodes WHERE node_type='center' ORDER BY id LIMIT 1").fetchone()[0]
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE '__t_ap2%')")
    c.execute("DELETE FROM org_nodes WHERE name LIKE '__t_ap2%'")
    c.execute("DELETE FROM team_members WHERE account LIKE '__t_ap2_%'")
    c.execute("INSERT INTO org_nodes (name,parent_id,node_type) VALUES ('__t_ap2_dept',?,'dept')", (center,))
    dept = c.execute("SELECT id FROM org_nodes WHERE name='__t_ap2_dept'").fetchone()[0]
    c.execute("INSERT INTO org_nodes (name,parent_id,node_type) VALUES ('__t_ap2_group',?,'group')", (dept,))
    NID['v'] = c.execute("SELECT id FROM org_nodes WHERE name='__t_ap2_group'").fetchone()[0]
    mids = {}
    for name, acc in (('__t_兼任甲__', '__t_ap2_a'), ('__t_兼任乙__', '__t_ap2_b')):
        c.execute("INSERT INTO team_members (id,name,workgroups,account,departments) "
                  "VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),?,'',?,'__t_ap2_dept')", (name, acc))
        mids[name] = c.execute("SELECT id FROM team_members WHERE account=?", (acc,)).fetchone()[0]
    c.commit()
    c.close()
    return NID['v'], mids

def cleanup():
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE '__t_ap2%')")
    c.execute("DELETE FROM org_nodes WHERE name LIKE '__t_ap2%'")
    c.execute("DELETE FROM team_members WHERE account LIKE '__t_ap2_%'")
    c.commit()
    c.close()
    print('夹具残留检查: nodes=%d members=%d appts=%d' % (
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE '__t_ap2%'").fetchone()[0],
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM team_members WHERE account LIKE '__t_ap2_%'").fetchone()[0],
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM org_appointments a JOIN org_nodes n ON n.id=a.node_id "
                                    "WHERE n.name LIKE '__t_ap2%'").fetchone()[0]), flush=True)

async def main():
    import websockets
    NID_V, mids = setup()
    A, B = mids['__t_兼任甲__'], mids['__t_兼任乙__']
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0172')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
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
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    async def wait_guard_idle():
        for _ in range(40):
            r = await ev("!document.getElementById('saveGuard')&&SG_N===0")
            if r is True:
                return True
            await asyncio.sleep(0.5)
        return False

    async def open_and_select():
        await ev("openWgModal()")
        await asyncio.sleep(3.5)
        await ev("(function(){ORG_SELECTED=%d;renderOrgRoles();})()" % NID_V)
        await asyncio.sleep(0.6)

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % make_token('admin')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(60):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True
            break
    ok(ok_login, 'admin 登录成功')
    await asyncio.sleep(1.5)

    print('【① 任命甲为组长（正常路径）】', flush=True)
    await open_and_select()
    await ev("(function(){const i=document.getElementById('g_appt_inp_group_leader');i.value='__t_兼任甲__';i.dispatchEvent(new Event('input'));})()")
    await asyncio.sleep(0.3)
    await ev("(function(){const i=document.getElementById('g_appt_inp_group_leader');i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
    ok(await wait_guard_idle(), '守卫释放')
    await asyncio.sleep(1)
    appts = await ev("""(async function(){
      const d=await api('/api/org/tree');
      let hit=null;(function walk(ns){(ns||[]).forEach(n=>{if(n.id===%d)hit=n;walk(n.children)})})(d.tree);
      return (hit.appointments||[]).map(a=>a.role_key+':'+a.member_name);
    })()""" % NID_V, aw=True)
    print('  ', appts, flush=True)
    ok(appts == ['group_leader:__t_兼任甲__'], '甲已任组长')

    print('【② 提交拦截：甲（现任组长）被任命为组员 → toast 阻止】', flush=True)
    await ev("addOrgApptMulti(%d,'member',[{id:%d,name:'__t_兼任甲__'}],[])" % (NID_V, A))
    await asyncio.sleep(1.2)
    r2 = await ev("""(function(){
      const ts=[...document.querySelectorAll('.toast')].map(x=>x.textContent);
      const guard=document.getElementById('saveGuard');
      return {toasts:ts, guard:!!guard};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(any('不可兼任' in t for t in (r2.get('toasts') or [])), '弹出「不可兼任」拦截提示')
    appts2 = await ev("""(async function(){
      const d=await api('/api/org/tree');
      let hit=null;(function walk(ns){(ns||[]).forEach(n=>{if(n.id===%d)hit=n;walk(n.children)})})(d.tree);
      return (hit.appointments||[]).length;
    })()""" % NID_V, aw=True)
    ok(appts2 == 1, '提交被阻止（仍只有组长 1 条任命）')

    print('【③ 历史兼任数据：人数去重统计】', flush=True)
    # 模拟历史数据：甲同时任组长+组员（前端拦截前可能产生）
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?,'member',1)", (NID_V, A))
    c.commit()
    c.close()
    await ev("location.reload()")
    await asyncio.sleep(4)
    cookie2 = 'tk=%s; path=/; SameSite=Lax' % make_token('admin')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie2))
    for _ in range(60):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            break
    await asyncio.sleep(1.5)
    await ev("openWgModal()")
    await asyncio.sleep(3.5)
    r3 = await ev("""(function(){
      const row=document.querySelector('[data-org-id=\"%d\"]');
      if(!row)return {row:false};
      const m=row.textContent.match(/(\\d+)\\s*人/);
      return {row:true, n:m?Number(m[1]):null, chips:row.textContent.indexOf('__t_兼任甲__')>=0};
    })()""" % NID_V)
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3.get('n') == 1, '兼任（组长+组员）人数统计为 1（不重复计）')

    print('【④ 后端兜底：绕过前端直接 POST → 409 拦截】', flush=True)
    r4 = await ev("""(async function(){
      try{
        await api('/api/org/appointments',{method:'POST',body:JSON.stringify({node_id:%d,member_id:%d,role_key:'member'})});
        return {code:200};
      }catch(e){return {code:'ERR', msg:e.message};}
    })()""" % (NID_V, A), aw=True)
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    ok('不可兼任' in str(r4.get('msg', '')), '后端 409：组长兼任组员被拒（兜底生效）')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    cleanup()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
