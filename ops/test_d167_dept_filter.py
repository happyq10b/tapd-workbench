# -*- coding: utf-8 -*-
"""#167 CDP 实测：成员与账号管理「架构筛选」→「部门筛选」（含「未选部门」选项）。
断言全部按 TM_ALL 实际数据相对计算，不硬编码基线。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token
BASE = 'http://127.0.0.1:8100'
PORT = 9463
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_PASSED = 0
def ok(cond, msg):
    global _PASSED
    tag = 'PASS' if cond else 'FAIL'
    print('  [%s] %s' % (tag, msg), flush=True)
    if cond: _PASSED += 1

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d167')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile,
                      '--window-size=1280,900', 'about:blank'],
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
                if fut and not fut.done(): fut.set_result(msg)
    seq = [0]
    async def send(m, p=None):
        seq[0] += 1; mid = seq[0]
        fut = asyncio.get_event_loop().create_future(); pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=30)).get('result', {})
    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:200]}
        return r.get('result', {}).get('value')
    rt = asyncio.create_task(reader())
    await send('Page.enable'); await send('Runtime.enable')

    tk = make_token('admin')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2)
    await ev("document.cookie='tk=%s; path=/; Max-Age=31536000';location.href='/';" % tk)
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True; break
    assert ok_login, '登录失败'
    await asyncio.sleep(1.5)

    print('【① 打开成员与账号管理 → 部门筛选输入框存在，弹层含「未选部门」】', flush=True)
    await ev("openTeamModal()")
    await asyncio.sleep(2)
    r1 = await ev("""(function(){
      const inp=document.getElementById('tm_filter_dept');
      if(!inp)return {found:false};
      inp.click();
      return {found:true, ph:inp.placeholder};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    ok(r1.get('found'), '部门筛选输入框存在（tm_filter_dept）')
    ok('部门筛选' in (r1.get('ph') or ''), 'placeholder 为「部门筛选（全部）」')
    await asyncio.sleep(0.6)
    r1b = await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      if(!pop)return {found:false};
      const labels=[...pop.querySelectorAll('label span')].map(x=>x.textContent);
      return {found:true, labels:labels.slice(0,4), hasNoDept:labels.some(x=>x.indexOf('未选部门')>=0),
              nOpts:pop.querySelectorAll('input[type=checkbox]').length};
    })()""")
    print('  ', json.dumps(r1b, ensure_ascii=False), flush=True)
    ok(r1b.get('found') and r1b.get('hasNoDept'), '弹层含「未选部门」选项（共 %s 项）' % r1b.get('nOpts'))

    print('【② 只勾「未选部门」→ 仅显示无部门的成员】', flush=True)
    base = await ev("(function(){return {total:TM_ALL.length, noDept:TM_ALL.filter(m=>!(m.departments||[]).length).length, withDept:TM_ALL.filter(m=>(m.departments||[]).length).length};})()")
    print('  基线:', json.dumps(base, ensure_ascii=False), flush=True)
    await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      [...pop.querySelectorAll('input[type=checkbox]')].forEach(c=>{c.checked=(c.value==='__NO_DEPT__');});
      pop.querySelectorAll('input[type=checkbox]').forEach(c=>c.dispatchEvent(new Event('change')));
      applyDeptPick();
    })()""")
    await asyncio.sleep(1)
    r2 = await ev("""(function(){
      const rows=[...document.querySelectorAll('#tm_tbody tr')];
      const ids=[...document.querySelectorAll('#tm_tbody [id^=tm_dept_]')].map(b=>Number(b.id.replace('tm_dept_','')));
      return {visible:ids.length, allNoDept:ids.every(id=>{const m=TM_ALL.find(x=>x.id===id);return m&&!(m.departments||[]).length;})};
    })()""")
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('visible') == base.get('noDept'), '可见行数 = 无部门成员数（%s = %s）' % (r2.get('visible'), base.get('noDept')))
    ok(r2.get('allNoDept'), '可见成员全部未选部门')

    print('【③ 只勾一个具体部门 → 仅显示含该部门的成员】', flush=True)
    dep = await ev("(function(){const m=TM_ALL.find(x=>(x.departments||[]).length);return m?m.departments[0]:null;})()")
    await ev("openDeptFilterPicker(document.getElementById('tm_filter_dept'))")
    await asyncio.sleep(0.5)
    await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      [...pop.querySelectorAll('input[type=checkbox]')].forEach(c=>{c.checked=(c.value==='%s');});
      pop.querySelectorAll('input[type=checkbox]').forEach(c=>c.dispatchEvent(new Event('change')));
      applyDeptPick();
    })()""" % dep)
    await asyncio.sleep(1)
    r3 = await ev("""(function(){
      const ids=[...document.querySelectorAll('#tm_tbody [id^=tm_dept_]')].map(b=>Number(b.id.replace('tm_dept_','')));
      return {visible:ids.length, allMatch:ids.every(id=>{const m=TM_ALL.find(x=>x.id===id);return m&&(m.departments||[]).includes('%s');})};
    })()""" % dep)
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    ok(r3.get('visible') > 0 and r3.get('allMatch'), '勾选「%s」→ 全部可见成员含该部门（%s 个）' % (dep, r3.get('visible')))

    print('【④ 未选部门 + 具体部门（OR）→ 两者并集】', flush=True)
    await ev("openDeptFilterPicker(document.getElementById('tm_filter_dept'))")
    await asyncio.sleep(0.5)
    await ev("""(function(){
      const pop=document.getElementById('dept_pick_pop');
      [...pop.querySelectorAll('input[type=checkbox]')].forEach(c=>{c.checked=(c.value==='__NO_DEPT__'||c.value==='%s');});
      pop.querySelectorAll('input[type=checkbox]').forEach(c=>c.dispatchEvent(new Event('change')));
      applyDeptPick();
    })()""" % dep)
    await asyncio.sleep(1)
    r4 = await ev("""(function(){
      const ids=[...document.querySelectorAll('#tm_tbody [id^=tm_dept_]')].map(b=>Number(b.id.replace('tm_dept_','')));
      return {visible:ids.length, allOr:ids.every(id=>{const m=TM_ALL.find(x=>x.id===id);
        return m&&(!(m.departments||[]).length||(m.departments||[]).includes('%s'));})};
    })()""" % dep)
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    r4b = await ev("(function(){return TM_ALL.filter(m=>!(m.departments||[]).length||(m.departments||[]).includes('%s')).length;})()" % dep)
    ok(r4.get('visible') == r4b, '可见数 = 无部门 ∩∪ 含该部门 的并集（%s = %s）' % (r4.get('visible'), r4b))
    ok(r4.get('allOr'), '全部可见成员满足 OR 条件')

    print('【⑤ 输入框回显 + 重置清空】', flush=True)
    r5 = await ev("(function(){return {val:document.getElementById('tm_filter_dept').value};})()")
    ok('未选部门' in (r5.get('val') or '') and dep in (r5.get('val') or ''), '输入框回显「未选部门 / %s」：%r' % (dep, r5.get('val')))
    await ev("resetTmFilter()")
    await asyncio.sleep(0.8)
    r5b = await ev("(function(){return {val:document.getElementById('tm_filter_dept').value, n:[...document.querySelectorAll('#tm_tbody tr')].length};})()")
    ok(not r5b.get('val'), '重置后输入框清空')
    ok(r5b.get('n') == base.get('total'), '重置后显示全部（%s）' % r5b.get('n'))

    await ev("(function(){try{closeModal('teamModal');}catch(e){}})()")
    print('结果: PASS=%d' % _PASSED, flush=True)

asyncio.run(main())
