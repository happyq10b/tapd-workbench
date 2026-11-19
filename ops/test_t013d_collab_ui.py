# -*- coding: utf-8 -*-
"""T-013d 协作部门 CDP 实测：中心看板动态出现协作部门控件 / 多选 / 保存回显"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9467
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PASS = []
ORIG = None


def ok(cond, msg):
    PASS.append(bool(cond))
    print(('  PASS  ' if cond else '  FAIL  ') + msg, flush=True)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t013d')
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
                await w.send(json.dumps({'method': 'Page.handleJavaScriptDialog', 'params': {'accept': True}}))

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

    print('【① admin 登录 → 打开中心归属看板的编辑区】', flush=True)
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
    # 选一个归属=财务中心的看板（真实数据，测完还原其协作配置）
    r0 = await ev("""(async function(){
      await loadBoardConfig();
      const b=(BC_BOARDS||[]).find(function(x){return x.dept==='财务中心' && x.config_id;});
      if(!b)return {found:false};
      bcSelect(b.board_id);
      return {found:true, bid:b.board_id, name:b.board_name};
    })()""", aw=True)
    print('  ', json.dumps(r0, ensure_ascii=False), flush=True)
    ok(r0 and r0.get('found'), '找到中心归属看板：%s' % (r0 or {}).get('name'))
    await asyncio.sleep(2)
    global ORIG
    ORIG = await ev("JSON.stringify({bid:BC_SELECTED.board_id, id:BC_EDIT_ID, collab:BC_FORM.collab_depts, dept:BC_FORM.dept})")

    print('【② 归属=财务中心 → 协作部门按钮出现在归属部门右侧；选项为中心下级部门】', flush=True)
    r2 = await ev("""(function(){
      const btn=document.getElementById('bc_collab_btn');
      const deptSel=document.getElementById('bc_dept');
      return {btn:!!btn, btnText:btn?btn.textContent.trim():null,
              dept:deptSel?deptSel.value:null,
              sideBySide:btn&&deptSel?Math.abs(btn.getBoundingClientRect().top-deptSel.getBoundingClientRect().top)<30:null};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2 and r2.get('btn'), '协作部门按钮动态出现（截图标注位置：归属部门右侧）')
    ok(r2 and r2.get('sideBySide'), '与归属部门同一行（右侧）')

    print('【③ 点击 → 弹层选项为中心下级部门（无中心自身）→ 勾选两个 → 确定】', flush=True)
    await ev("openBcCollabPick(document.getElementById('bc_collab_btn'))")
    await asyncio.sleep(0.6)
    r3 = await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      if(!pop)return {found:false};
      const labs=[...pop.querySelectorAll('label span')].map(s=>s.textContent.trim());
      return {found:true, n:labs.length, hasCenter:labs.some(function(x){return x.indexOf('财务中心')===0;}),
              first:labs.slice(0,4)};
    })()""")
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3 and r3.get('found') and r3.get('n', 0) >= 2, '弹层有部门选项（%s 个）' % (r3 or {}).get('n'))
    ok(r3 and r3.get('hasCenter') is False, '不含中心自身（仅下级部门）')
    # 勾选前两个选项 → 确定
    picked = await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      const boxes=[...pop.querySelectorAll('input[type=checkbox]')];
      boxes.slice(0,2).forEach(function(b){if(!b.checked)b.click();});
      applyDeptPick();
      return {picked:BC_FORM.collab_depts.length};
    })()""")
    print('  picked:', picked, flush=True)
    ok(picked and picked.get('picked') == 2, '勾选 2 个协作部门')
    r3b = await ev("document.getElementById('bc_collab_btn').textContent.trim()")
    ok(r3b and r3b != '选择协作部门（可选）', '按钮回显所选：%s' % r3b)

    print('【④ 保存看板 → 落库；重开编辑区回显】', flush=True)
    await ev("saveBoardAll()")
    await asyncio.sleep(3)
    saved = await ev("""(async function(){
      const cfgs=await api('/api/board-config');
      const cfg=cfgs.items.find(function(x){return x.board_id===BC_SELECTED.board_id;});
      return JSON.stringify({n:(cfg.collab_depts||'').split(',').filter(Boolean).length});
    })()""", aw=True)
    print('  saved:', saved, flush=True)
    ok(saved and json.loads(saved).get('n') == 2, '保存后协作部门落库 2 个')
    # 重开编辑区 → BC_FORM 回显
    await ev("bcSelect(BC_SELECTED.board_id)")
    await asyncio.sleep(1.5)
    reopen = await ev("JSON.stringify({n:(BC_FORM.collab_depts||[]).length})")
    ok(reopen and json.loads(reopen).get('n') == 2, '重开编辑区回显 2 个协作部门')

    # 还原原配置（保存界面 + 数据库双保险）
    if ORIG:
        await ev("(function(){BC_FORM.collab_depts=%s;saveBoardAll();})()" % json.loads(ORIG)['collab'])
        await asyncio.sleep(2.5)
    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    try:
        orig_data = json.loads(ORIG) if ORIG else None
        if not orig_data: raise RuntimeError('no orig')
        c = sqlite3.connect(DB); c.execute('PRAGMA busy_timeout=5000')
        c.execute('UPDATE board_config SET collab_depts=? WHERE id=?',
                  (','.join(orig_data['collab']), orig_data['id']))
        c.commit(); c.close()
        print('原协作配置已还原:', orig_data['collab'], flush=True)
    except Exception as e:
        print('还原跳过:', e, flush=True)
n = sum(PASS)
print('结果: PASS=%d/%d' % (n, len(PASS)), flush=True)
sys.exit(0 if n == len(PASS) else 1)
