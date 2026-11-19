# -*- coding: utf-8 -*-
"""T-0169 CDP：新成员表单同排含部门按钮 / 选择回显 / 添加后 ID=工号+部门显示"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9470
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS = []
NEW_NAME = '__t_id界面成员__'


def ok(cond, msg):
    PASS.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0169')
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

    print('【① admin 登录 → 打开成员与账号管理】', flush=True)
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

    print('【② 部门按钮与姓名/账号/密码/角色同排】', flush=True)
    r2 = await ev("""(function(){
      const btn=document.getElementById('t_new_dept');
      const name=document.getElementById('t_new_name');
      if(!btn||!name)return {found:false};
      const sameRow=Math.abs(btn.getBoundingClientRect().top-name.getBoundingClientRect().top)<30;
      return {found:true, sameRow:sameRow, txt:btn.textContent.trim()};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2 and r2.get('found') and r2.get('sameRow'), '部门按钮与姓名等同排（同一行布局）')

    print('【③ 点击 → 部门弹层 → 勾选核算部 → 确定回显】', flush=True)
    await ev("openNewMemberDeptPick(document.getElementById('t_new_dept'))")
    await asyncio.sleep(0.6)
    r3 = await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      if(!pop)return {found:false};
      const box=[...pop.querySelectorAll('input[type=checkbox]')].find(b=>b.value==='核算部');
      if(box&&!box.checked)box.click();
      applyDeptPick();
      return {found:true, dept:TM_NEW_DEPT};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3 and r3.get('dept') == ['核算部'], '勾选核算部并回显')
    lbl = await ev("document.getElementById('t_new_dept').textContent.trim()")
    ok(lbl == '核算部', '按钮回显：%s' % lbl)

    print('【④ 填姓名 + 开账号 → 添加成员 → 新行 ID=工号（no+5位）、部门列显示】', flush=True)
    await ev("document.getElementById('t_new_name').value='%s';document.getElementById('t_new_account').value='__t_id_ui';document.getElementById('t_new_pwd').value='Xx12345678';addTeamMember();" % NEW_NAME)
    await asyncio.sleep(3)
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    row = c.execute("SELECT id,emp_no,departments FROM team_members WHERE name=?", (NEW_NAME,)).fetchone()
    c.close()
    ok(row and bool(__import__('re').fullmatch(r'no\d{5}', row[1])), '新成员工号=%r（no+5位随机）' % (row[1] if row else None))
    ok(row and row[2] == '核算部', '部门已落库')
    r4 = await ev("""(function(){
      const m=TM_ALL.find(x=>x.name==='__t_id界面成员__');
      if(!m)return {found:false};
      const empInput=document.getElementById('tm_empno_'+m.id);
      return {found:true, empShow:empInput?empInput.value:(m.emp_no||''), dept:(m.departments||[]).join('、')};
    })()""")
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    ok(r4 and r4.get('found') and str(r4.get('empShow', '')).startswith('no'),
       '表格 ID 列显示生成的工号')
    ok(r4 and r4.get('dept') == '核算部', '表格部门列显示核算部')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
    c.execute("DELETE FROM org_appointments WHERE member_id IN (SELECT id FROM team_members WHERE name=?)", (NEW_NAME,))
    c.execute("DELETE FROM users WHERE username='__t_id_ui'")
    c.execute("DELETE FROM team_members WHERE name=?", (NEW_NAME,))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM team_members WHERE name=?", (NEW_NAME,)).fetchone()[0]
    print('夹具残留检查: members=%d' % n, flush=True)
    c.close()
n = sum(PASS)
print('结果: PASS=%d/%d' % (n, len(PASS)), flush=True)
sys.exit(0 if n == len(PASS) else 1)
