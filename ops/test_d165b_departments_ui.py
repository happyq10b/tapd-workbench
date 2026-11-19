# -*- coding: utf-8 -*-
"""#165 CDP 实测：个人界面部门字段 + 账号管理部门列
单 reader 收发（按 id 分发）；make_token 注入 cookie 登录（无 logout 往返）。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
PORT = 9461
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def cleanup(c):
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE '__t_d165%')")
    c.execute("DELETE FROM org_nodes WHERE name LIKE '__t_d165%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_d165%'")
    c.execute("DELETE FROM team_members WHERE name LIKE '__t_d165%' OR account LIKE '__t_d165%'")
    c.commit()


# ---------- 夹具：一个长名部门（测截断）+ 一个普通部门 + 成员 ----------
conn = sqlite3.connect(DB)
cleanup(conn)
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP','center',0,9011,'')")
ca = conn.execute("SELECT id FROM org_nodes WHERE name LIKE '__t_d165中心超长%'").fetchone()[0]
conn.execute("INSERT INTO org_nodes (name,node_type,parent_id,sort,participants) VALUES ('__t_d165部丙','dept',?,9012,'')", (ca,))
conn.execute("INSERT INTO users (username,password_hash,role) VALUES ('__t_d165_u9',?,'admin')", (hash_pw('Xx12345678'),))
conn.execute("INSERT INTO team_members (name,account) VALUES ('__t_d165成员玖','__t_d165_u9')")
conn.commit()
conn.close()

tk_admin = make_token('__t_d165_u9')   # 夹具成员绑定的账号（个人界面↔成员行对齐）


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d165')
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
        res = await asyncio.wait_for(fut, timeout=30)
        return res.get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')

    # 登录（cookie 注入，等待条件必须 r is True）
    cookie = 'tk=%s; path=/; Max-Age=86400' % tk_admin
    await send('Page.navigate', {'url': BASE + '/'})
    await asyncio.sleep(1)
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__t_d165_u9'")
        if r is True:
            ok_login = True
            break
    ok(ok_login, 'admin 登录就绪')
    await asyncio.sleep(2)

    print('【① 个人界面：部门字段渲染与选项】', flush=True)
    await ev("openProfileModal()")
    await asyncio.sleep(1)
    r1 = await ev("""(function(){
      const b=document.getElementById('pf_departments');
      const grid=document.querySelectorAll('#profileModal .pg-item').length;
      return {has:b&&b.textContent==='未选择', items:grid, opts:(ME.dept_options||[]).length};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1.get('has'), '部门按钮存在且初始「未选择」')
    ok((r1.get('items') or 0) >= 9, '基本信息网格含新字段（9 项）')
    ok((r1.get('opts') or 0) >= 2, 'dept_options 已下发')

    print('【② 部门多选：勾选两个 → 确定 → 回显】', flush=True)
    await ev("openPfDeptPick(document.getElementById('pf_departments'))")
    await asyncio.sleep(0.5)
    r2 = await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      if(!pop)return {pop:false};
      const cbs=[...pop.querySelectorAll('input[type=checkbox]')];
      const target=cbs.find(x=>x.value.indexOf('__t_d165部丙')>=0);
      const center=cbs.find(x=>x.value.indexOf('__t_d165中心超长')>=0);
      if(target)target.click(); if(center)center.click();
      return {pop:true, total:cbs.length,
              centerTagged:!!center&&center.closest('label').textContent.indexOf('全员')>=0};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('pop') and (r2.get('total') or 0) >= 2, '选择器列出前两级部门')
    ok(r2.get('centerTagged'), '中心节点标注「全员」')
    await ev("applyDeptPick()")
    await asyncio.sleep(0.5)
    r3 = await ev("""(function(){
      const b=document.getElementById('pf_departments');
      const cs=getComputedStyle(b);
      return {txt:b.textContent, nowrap:cs.whiteSpace, ellip:cs.textOverflow};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(sorted((r3.get('txt') or '').split('、')) == sorted(['__t_d165部丙', '__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP']),
       '确定后按钮回显所选（按选项顺序显示）：%r' % r3.get('txt'))
    ok(r3.get('nowrap') == 'nowrap' and r3.get('ellip') == 'ellipsis', '部门字段单行 + 省略号截断样式')
    # 长文本实际截断（scrollWidth > clientWidth → 出现省略）
    r4 = await ev("""(function(){
      const b=document.getElementById('pf_departments');
      return {trunc:b.scrollWidth>b.clientWidth};
    })()""")
    ok(r4.get('trunc'), '超长部门名实际触发「…」截断')
    await ev("saveProfile()")
    await asyncio.sleep(1.5)

    print('【③ 账号管理：列替换 + 管理员可编辑】', flush=True)
    await ev("openTeamModal()")
    for _ in range(20):
        await asyncio.sleep(0.5)
        r = await ev("!!document.getElementById('tm_tbody')&&document.getElementById('tm_tbody').children.length>0")
        if r is True:
            break
    await asyncio.sleep(1)
    r5 = await ev("""(function(){
      const ths=[...document.querySelectorAll('#teamModal thead th')].map(x=>x.textContent.trim());
      const row=[...document.querySelectorAll('#tm_tbody tr')].find(tr=>tr.textContent.indexOf('__t_d165成员玖')>=0);
      const btn=row?row.querySelector('button[id^=tm_dept_]'):null;
      return {ths:ths, hasWgCol:ths.indexOf('已选工作组')>=0, hasDeptCol:ths.indexOf('部门')>=0,
              btnText:btn?btn.textContent:'', rowFound:!!row};
    })()""")
    print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
    ok(r5.get('hasDeptCol') and not r5.get('hasWgCol'), '表头「已选工作组」→「部门」')
    mid9 = sqlite3.connect(DB).execute("SELECT id FROM team_members WHERE name='__t_d165成员玖'").fetchone()[0]
    r5b = await ev("(function(){const b=document.getElementById('tm_dept_%d');return b?b.textContent:'';})()" % mid9)
    ok(r5b == '__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP、__t_d165部丙',
       '账号管理按钮显示个人界面刚存的选择（双向同步一致）：%r' % r5b)

    print('【④ 账号管理修改部门 → 个人界面生效】', flush=True)
    await ev("(function(){openTmDeptPick(document.getElementById('tm_dept_%d'), %d);})()" % (mid9, mid9))
    await asyncio.sleep(0.5)
    await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      [...pop.querySelectorAll('input[type=checkbox]')].forEach(c=>{
        if(c.value.indexOf('__t_d165部丙')>=0)c.click();     // 取消部丙
        if(c.value.indexOf('核算部')>=0)c.click();            // 勾真实部门
      });
    })()""")
    await ev("applyDeptPick()")
    await asyncio.sleep(0.5)
    dd = await ev("(function(){return {draft:JSON.stringify(TM_DEPT_DRAFT), mid9:%d, vis:TM_VISIBLE_IDS.has(%d), sel:DEPT_PICK.sel};})()" % (mid9, mid9))
    print('  草稿状态:', json.dumps(dd, ensure_ascii=False), flush=True)
    serr = await ev("saveAllTeamMembers().catch(function(e){return 'CATCH:'+(e&&e.message||e);})", aw=True)
    print('  save 返回:', json.dumps(serr, ensure_ascii=False), flush=True)
    await asyncio.sleep(2)
    dt = await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)")
    print('  toasts:', json.dumps(dt, ensure_ascii=False), flush=True)
    c = sqlite3.connect(DB)
    deps = c.execute("SELECT departments FROM team_members WHERE name='__t_d165成员玖'").fetchone()[0]
    p1 = c.execute("SELECT participants FROM org_nodes WHERE name LIKE '__t_d165部丙'").fetchone()[0]
    p2 = c.execute("SELECT participants FROM org_nodes WHERE name='核算部'").fetchone()[0]
    c.close()
    ok(sorted(deps.split(',')) == sorted(['核算部', '__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP']),
       '账号管理修改落库（部丙取消、核算部加入、保留中心超长）：%r' % deps)
    ok('__t_d165_u9' not in (p1 or '').split(','), '取消的部门 → 参与人同步移除')
    ok('__t_d165_u9' in (p2 or '').split(','), '新选部门 → 参与人同步加入')
    r6 = await ev("(function(){return (ME.departments||[]).join(',');})()")
    # ME 是登录时快照，openTeamModal 不刷新 ME —— 刷新页面验证个人界面读到新值
    await ev("location.reload()")
    await asyncio.sleep(4)
    for _ in range(40):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME")
        if r is True:
            break
    r7 = await ev("(function(){openProfileModal();return {me:(ME.departments||[]).join(','),btn:document.getElementById('pf_departments').textContent};})()")
    print('  ', json.dumps(r7, ensure_ascii=False), flush=True)
    ok(sorted((r7.get('me') or '').split(',')) == sorted(['核算部', '__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP'])
       and sorted((r7.get('btn') or '').split('、')) == sorted(['核算部', '__t_d165中心超长名称测试用例ABCDEFGHIJKLMNOP']),
       '刷新后个人界面显示账号管理的修改（同步一致）：%r/%r' % (r7.get('me'), r7.get('btn')))


asyncio.run(main())
# cleanup（夹具清理不依赖测试成败）
conn = sqlite3.connect(DB)
cleanup(conn)
n1 = conn.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE '__t_d165%'").fetchone()[0]
n2 = conn.execute("SELECT COUNT(*) FROM team_members WHERE name LIKE '__t_d165%'").fetchone()[0]
n3 = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t_d165%'").fetchone()[0]
conn.close()
print('残留: nodes=%d members=%d users=%d' % (n1, n2, n3), flush=True)

good, total = sum(PASSED), len(PASSED)
print('结果: %d/%d' % (good, total), flush=True)
sys.exit(0 if good == total else 1)

