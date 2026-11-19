# -*- coding: utf-8 -*-
"""T-0171 架构管理任命「输入姓名」联想 CDP 实测。
组长为唯一岗位：每轮任命前用 SQL 清空该岗位并整页重载（ORG_FLAT 缓存刷新）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9472
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
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name='__t_ap_b')")
    c.execute("DELETE FROM org_nodes WHERE name='__t_ap_b'")
    c.execute("DELETE FROM team_members WHERE account LIKE '__t_ap_%'")
    c.execute("INSERT INTO org_nodes (name,parent_id,node_type) VALUES ('__t_ap_b',?,'dept')", (center,))
    NID['v'] = c.execute("SELECT id FROM org_nodes WHERE name='__t_ap_b'").fetchone()[0]
    mids = {}
    for name, acc in (('__t_甲__', '__t_ap_a'), ('__t_乙__', '__t_ap_x'), ('__t_丙__', '__t_ap_c')):
        c.execute("INSERT INTO team_members (id,name,workgroups,account,departments) "
                  "VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM team_members),?,'',?,'__t_ap_b')", (name, acc))
        mids[name] = c.execute("SELECT id FROM team_members WHERE account=?", (acc,)).fetchone()[0]
    # 甲先任组长（唯一槽位）：②③ 用于验证候选排除；④ 前由测试移除
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?,'dept_head',1)",
              (NID['v'], mids['__t_甲__']))
    c.commit()
    c.close()
    return NID['v'], mids

def clear_leader():
    """清空夹具节点的 dept_head 任命（唯一槽位腾位）。"""
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE node_id=? AND role_key='dept_head'", (NID['v'],))
    c.commit()
    c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name='__t_ap_b')")
    c.execute("DELETE FROM org_nodes WHERE name='__t_ap_b'")
    c.execute("DELETE FROM team_members WHERE account LIKE '__t_ap_%'")
    c.commit()
    c.close()
    print('夹具残留检查: node=%d members=%d appts=%d' % (
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM org_nodes WHERE name='__t_ap_b'").fetchone()[0],
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM team_members WHERE account LIKE '__t_ap_%'").fetchone()[0],
        sqlite3.connect(DB).execute("SELECT COUNT(*) FROM org_appointments WHERE node_id=? AND role_key='dept_head'", (NID['v'],)).fetchone()[0]), flush=True)

async def main():
    import websockets
    NID_V, mids = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0171')
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

    async def login():
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2.5)
        cookie = 'tk=%s; path=/; SameSite=Lax' % make_token('admin')
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(60):
            await asyncio.sleep(0.5)
            r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
            if r is True:
                break
        await asyncio.sleep(1.5)
        await ev("openWgModal()")
        await asyncio.sleep(3.5)
        await ev("(function(){ORG_SELECTED=%d;renderOrgRoles();})()" % NID_V)
        await asyncio.sleep(0.6)

    async def heads():
        return await ev("""(async function(){
          const d=await api('/api/org/tree');
          let hit=null;
          (function walk(ns){(ns||[]).forEach(n=>{if(n.id===%d)hit=n;walk(n.children)})})(d.tree);
          return ((hit.appointments||[]).filter(a=>a.role_key==='dept_head').map(a=>a.member_name));
        })()""" % NID_V, aw=True)

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')

    print('【① 组长任命控件：下拉 → 输入框】', flush=True)
    await login()
    r1 = await ev("""(function(){
      const sel=document.getElementById('g_appt_sel_dept_head');
      const inp=document.getElementById('g_appt_inp_dept_head');
      return {selGone:!sel, inp:!!inp, ph:inp?inp.placeholder:null};
    })()""")
    ok(r1.get('selGone') and r1.get('inp'), '下拉已替换为输入框')
    ok('输入姓名' in (r1.get('ph') or ''), 'placeholder 提示输入姓名')

    print('【② 聚焦联想：候选=乙/丙（已任组长的甲被剔除）】', flush=True)
    # headless 下 el.focus() 不派发事件 → 显式 dispatch focus
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.dispatchEvent(new Event('focus'));})()")
    await asyncio.sleep(0.6)
    r2 = await ev("""(function(){
      const p=document.querySelector('.combo-panel');
      return {panel:!!p, opts:p?[...p.querySelectorAll('.combo-opt')].map(o=>o.getAttribute('data-v')):[]};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('panel'), '联想面板出现（focus 触发）')
    ok(str(mids['__t_甲__']) not in (r2.get('opts') or []), '已任组长的甲不在候选')
    ok(str(mids['__t_乙__']) in (r2.get('opts') or []) and str(mids['__t_丙__']) in (r2.get('opts') or []),
       '乙/丙在候选中')

    print('【③ 输入模糊词过滤 + 点选回显】', flush=True)
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.value='乙';i.dispatchEvent(new Event('input'));})()")
    await asyncio.sleep(0.5)
    r3 = await ev("""(function(){
      const p=document.querySelector('.combo-panel');
      const opts=p?[...p.querySelectorAll('.combo-opt')]:[];
      if(!opts.length)return {opts:0};
      const v=opts[0].getAttribute('data-v');
      opts[0].dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
      const i=document.getElementById('g_appt_inp_dept_head');
      return {opts:opts.length, val:i.value, mid:i.dataset.mid};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3.get('opts') == 1, '模糊词过滤到 1 位候选')
    ok(r3.get('val') == '__t_乙__' and r3.get('mid') == str(mids['__t_乙__']), '点选回显姓名并记住 member_id')

    print('【④ 移除甲（腾出唯一槽位）→ 点「任命」→ 乙上任】', flush=True)
    clear_leader()
    await login()   # 整页重载刷新 ORG_FLAT
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.value='__t_乙__';i.dispatchEvent(new Event('input'));})()")
    await asyncio.sleep(0.5)
    await ev("""(function(){
      const i=document.getElementById('g_appt_inp_dept_head');
      const p=document.querySelector('.combo-panel');
      const opt=p?p.querySelector('.combo-opt'):null;
      if(opt)opt.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
    })()""")
    await asyncio.sleep(0.3)
    # 行内自己的「任命」按钮（输入框同排）
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');(i.closest('div')||i.parentElement).querySelector('button').click();})()")
    ok(await wait_guard_idle(), '保存守卫释放（任命请求完成）')
    await asyncio.sleep(1)
    h = await heads()
    print('  heads:', h, flush=True)
    ok(h == ['__t_乙__'], '乙已任命为组长（唯一槽位）')

    print('【⑤ 移除乙 → 纯手输精确名 + Enter → 直接任命】', flush=True)
    clear_leader()
    await login()
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.value='__t_丙__';i.dispatchEvent(new Event('input'));})()")
    await asyncio.sleep(0.3)
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
    ok(await wait_guard_idle(), '保存守卫释放')
    await asyncio.sleep(1)
    h = await heads()
    print('  heads:', h, flush=True)
    ok(h == ['__t_丙__'], '丙经 Enter 直接任命（无需点选联想）')

    print('【⑥ 无效姓名 + Enter → 拦截不任命】', flush=True)
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.value='__t_不存在__';i.dispatchEvent(new Event('input'));})()")
    await asyncio.sleep(0.3)
    await ev("(function(){const i=document.getElementById('g_appt_inp_dept_head');i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
    await asyncio.sleep(1)
    h = await heads()
    ok(h == ['__t_丙__'], '无效姓名被拦截（组长仍为丙）')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    cleanup()

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
