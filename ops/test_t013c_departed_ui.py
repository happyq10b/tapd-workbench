# -*- coding: utf-8 -*-
"""T-013c 离岗 CDP 实测：角色列下离岗控件 / 确认交互 / 名单剔除联动 / 恢复"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9465
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS = []
MID, ACC, MNAME = 990414, '__t_lg2_u', '__t_离岗界面成员__'


def ok(cond, msg):
    PASS.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


def dbq(sql, args=()):
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


# 夹具：成员 + 账号 + 任命（核算部）
NID = dbq("SELECT id FROM org_nodes WHERE name='核算部' AND node_type='dept' LIMIT 1")[0]
c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'viewer')", (ACC, hash_pw('Xx12345678')))
c.execute("INSERT OR IGNORE INTO team_members (id,name,account,status) VALUES (?,?,?,'')", (MID, MNAME, ACC))
c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary) VALUES (?,?, 'backbone',1)", (NID, MID))
c.commit(); c.close()

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t013c')
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
            if msg.get('method') == 'Page.javascriptDialogOpening':
                await w.send(json.dumps({'id': 999900, 'method': 'Page.handleJavaScriptDialog',
                                         'params': {'accept': True}}))

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

    print('【① admin 登录 → 账号管理：夹具成员角色列下有【离岗】按钮】', flush=True)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev("document.cookie=%s;location.href='/';" % json.dumps("tk=%s; path=/; SameSite=Lax" % make_token('admin')))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True; break
    if not ok_login:
        snap = await ev("({url:location.href, api:typeof api, me:typeof ME, dom:(document.body?document.body.innerHTML.slice(0,150):'')})")
        print('   现场快照:', json.dumps(snap, ensure_ascii=False), flush=True)
    ok(ok_login, 'admin 登录成功')
    await asyncio.sleep(1.5)
    await ev("openTeamModal()")
    await asyncio.sleep(2.5)
    r1 = await ev("""(function(){
      const sel=document.getElementById('tm_role_%d');
      if(!sel)return {found:false};
      const cell=sel.closest('td');
      const btn=[...cell.querySelectorAll('button')].find(b=>b.textContent.trim()==='离岗');
      return {found:true, hasBtn:!!btn};
    })()""" % MID)
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1 and r1.get('found') and r1.get('hasBtn'), '角色列下方出现【离岗】按钮')

    print('【② 点击离岗（自动接受确认）→ 变离岗标签 + 恢复在岗按钮，任命剔除】', flush=True)
    appt_before = dbq('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,))[0]
    await ev("(function(){const sel=document.getElementById('tm_role_%d');[...sel.closest('td').querySelectorAll('button')].find(b=>b.textContent.trim()==='离岗').click();})()" % MID)
    await asyncio.sleep(2.5)
    r2 = await ev("""(function(){
      const sel=document.getElementById('tm_role_%d');
      if(!sel)return {found:false};
      const cell=sel.closest('td');
      const tag=[...cell.querySelectorAll('span')].find(s=>s.textContent.trim()==='离岗');
      const btn=[...cell.querySelectorAll('button')].find(b=>b.textContent.indexOf('恢复在岗')>=0);
      return {found:true, hasTag:!!tag, hasRestore:!!btn};
    })()""" % MID)
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2 and r2.get('hasTag') and r2.get('hasRestore'), '界面变为「离岗」标签 + 恢复在岗按钮')
    appt_after = dbq('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,))[0]
    ok(appt_before >= 1 and appt_after == 0, '任命已剔除（%d→%d）' % (appt_before, appt_after))

    print('【③ 任命候选不含离岗成员】', flush=True)
    await ev("openWgModal()")   # ORG_MEMBERS 随架构管理弹窗载入
    await asyncio.sleep(3.5)
    r3 = await ev("""(function(){
      // ORG_MEMBERS 随 /api/team 已载入（ORG_MEMBERS 与 TM_ALL 同源）
      const cands=orgApptCandidates({id:%d,node_type:'dept',appointments:[]},'backbone');
      const mem=ORG_MEMBERS.find(function(m){return m.id===%d;});
      return {n:cands.length, has:cands.some(function(m){return m.id===%d;}),
              memStatus:mem?mem.status:null};
    })()""" % (NID, MID, MID))
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3 and r3.get('memStatus') == 'departed' and r3.get('has') is False,
       '离岗成员不进任命候选（memStatus=departed，%s 个候选）' % (r3.get('n') if r3 else '?'))

    print('【④ 恢复在岗 → 标签消失，名单不回填】', flush=True)
    await ev("(function(){const sel=document.getElementById('tm_role_%d');[...sel.closest('td').querySelectorAll('button')].find(b=>b.textContent.indexOf('恢复在岗')>=0).click();})()" % MID)
    await asyncio.sleep(2.5)
    r4 = await ev("""(function(){
      const sel=document.getElementById('tm_role_%d');
      const btn=sel?[...sel.closest('td').querySelectorAll('button')].find(b=>b.textContent.trim()==='离岗'):null;
      return {hasBtnAgain:!!btn};
    })()""" % MID)
    ok(r4 and r4.get('hasBtnAgain'), '恢复在岗后回到【离岗】按钮')
    appt_restored = dbq('SELECT COUNT(*) FROM org_appointments WHERE member_id=?', (MID,))[0]
    ok(appt_restored == 0, '名单未自动回填（需重新任命）')

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
