# -*- coding: utf-8 -*-
"""T-013e CDP 实测：角色下拉含离岗/旧按钮移除/选择保存生效/登录页拦截文案"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9468
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS = []
MID, ACC, MNAME, PWD = 990416, '__t_lg4_u', '__t_离岗角色界面成员__', 'Xx12345678'


def ok(cond, msg):
    PASS.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA busy_timeout=5000')
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (ACC, hash_pw(PWD)))
c.execute("INSERT OR IGNORE INTO team_members (id,name,account,status) VALUES (?,?,?,'')", (MID, MNAME, ACC))
c.commit(); c.close()

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t013e')
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
        fut = asyncio.get_event_loop().create_future(); pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return None
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')

    print('【① admin 登录 → 账号管理：夹具成员角色下拉含【离岗】，旧独立按钮不存在】', flush=True)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev("document.cookie=%s;location.href='/';" % json.dumps("tk=%s; path=/; SameSite=Lax" % make_token('admin')))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True; break
    ok(ok_login, 'admin 登录成功')
    await asyncio.sleep(1.5)
    await ev("openTeamModal()")
    await asyncio.sleep(2.5)
    r1 = await ev("""(function(){
      const sel=document.getElementById('tm_role_%d');
      if(!sel)return {found:false};
      const vals=[...sel.options].map(o=>o.value);
      const cell=sel.closest('td');
      const oldBtn=[...cell.querySelectorAll('button')].filter(b=>b.textContent.trim()==='离岗'||b.textContent.indexOf('恢复在岗')>=0);
      return {found:true, vals:vals, oldBtns:oldBtn.length};
    })()""" % MID)
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1 and 'departed' in r1.get('vals', []), '角色下拉含「离岗」选项')
    ok(r1 and r1.get('oldBtns') == 0, '旧独立【离岗】按钮已移除')

    print('【② 下拉选离岗 → 保存全部 → users.role/成员状态落库】', flush=True)
    pre = await ev("JSON.stringify({tmall:TM_ALL.length, vis:TM_VISIBLE_IDS.has(990416), domSel:!!document.getElementById('tm_role_990416'), inAll:!!TM_ALL.find(m=>m.id===990416)})")
    print('   前置状态:', pre, flush=True)
    await ev("""(function(){
      const s=document.getElementById('tm_role_990416');
      s.value='departed';
      window.__sent=[];
      const _f=window.fetch;
      window.fetch=function(u,o){return _f.apply(this,arguments).then(function(res){try{if(String(u).indexOf('/api/team/')>=0)window.__sent.push(res.status+' '+String(u)+' '+String(o&&o.body||'').slice(0,160));}catch(e){}return res;});};
      saveAllTeamMembers();
    })()""")
    # 串行提交按 id 排序，990416 排最后 → 轮询等待本行请求出现
    hit_ok = False
    for _ in range(60):
        await asyncio.sleep(1)
        h = await ev("(window.__sent||[]).filter(function(x){return x.indexOf('/api/team/990416')>=0}).length")
        if h:
            hit_ok = True; break
    await asyncio.sleep(1)
    tw = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    total = await ev("(window.__sent||[]).length")
    hits = await ev("(window.__sent||[]).filter(function(x){return x.indexOf('200')<0}).slice(0,4)")
    ok200 = await ev("(window.__sent||[]).filter(function(x){return x.indexOf('990416')>=0})")
    print('   toasts:', json.dumps(tw, ensure_ascii=False), flush=True)
    print('   请求总数:', total, '| 失败样例:', json.dumps(hits, ensure_ascii=False), flush=True)
    print('   本行请求:', json.dumps(ok200, ensure_ascii=False), flush=True)
    ids = await ev("(window.__sent||[]).slice(0,3)")
    print('   请求样例:', json.dumps(ids, ensure_ascii=False), flush=True)
    ok(hit_ok, '本行 PUT 已发出（轮询等待命中）')
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    ok(c.execute("SELECT role FROM users WHERE username=?", (ACC,)).fetchone()[0] == 'departed', 'users.role=departed')
    ok(c.execute("SELECT status FROM team_members WHERE id=?", (MID,)).fetchone()[0] == 'departed', '成员状态=离岗')
    c.close()

    print('【③ 登录页：正确密码 → 提示文案 + 阻止登录】', flush=True)
    await ev("(function(){try{localStorage.clear();sessionStorage.clear();}catch(e){}document.cookie='tk=; path=/; Max-Age=0';location.href='/login';})()")
    await asyncio.sleep(3)
    await ev("document.getElementById('u').value='%s';document.getElementById('p').value='%s';document.getElementById('btn').click();" % (ACC, PWD))
    got = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        m = await ev("document.getElementById('msg').textContent")
        if m:
            got = m; break
    print('   msg:', got, flush=True)
    ok(got == '已不在本岗位，如需登入请联系管理员', '登录页提示文案精确匹配')
    ok(await ev("!!document.getElementById('btn')") is True, '仍停留在登录页（登录被阻止）')

    print('【④ 角色筛选弹层含「离岗」】', flush=True)
    await ev("document.cookie=%s;location.href='/';" % json.dumps("tk=%s; path=/; SameSite=Lax" % make_token('admin')))
    for _ in range(60):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True: break
    await asyncio.sleep(1.5)
    await ev("openTeamModal()")
    await asyncio.sleep(2.5)
    await ev("document.getElementById('tm_filter_role').click()")
    await asyncio.sleep(0.8)
    r4 = await ev("""(function(){
      const pop=document.getElementById('role_multi_pop');
      if(!pop)return {found:false};
      const labs=[...pop.querySelectorAll('label span')].map(s=>s.textContent.trim());
      return {found:true, labs:labs};
    })()""")
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    ok(r4 and r4.get('found') and '离岗' in (r4.get('labs') or []), '角色筛选含「离岗」')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE member_id=?", (MID,))
    c.execute("DELETE FROM team_members WHERE id=?", (MID,))
    c.execute("DELETE FROM users WHERE username=?", (ACC,))
    c.commit()
    n1 = c.execute("SELECT COUNT(*) FROM team_members WHERE id=?", (MID,)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username=?", (ACC,)).fetchone()[0]
    print('夹具残留检查: members=%d users=%d' % (n1, n2), flush=True)
    c.close()
n = sum(PASS)
print('结果: PASS=%d/%d' % (n, len(PASS)), flush=True)
sys.exit(0 if n == len(PASS) else 1)
