# -*- coding: utf-8 -*-
"""#168 CDP 实测：架构管理任命候选按部门筛选。
断言全部按页面内实际数据（ORG_MEMBERS/ORG_FLAT）相对计算。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token
BASE = 'http://127.0.0.1:8100'
PORT = 9464
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_PASSED = 0
def ok(cond, msg):
    global _PASSED
    tag = 'PASS' if cond else 'FAIL'
    print('  [%s] %s' % (tag, msg), flush=True)
    if cond: _PASSED += 1

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d168')
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
            return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:250]}
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

    print('【① 打开架构管理，准备数据基线】', flush=True)
    await ev("openWgModal()")
    await asyncio.sleep(3)
    base = await ev("""(function(){
      const depts=ORG_FLAT.filter(x=>x.node_type==='dept');
      const withCnt=depts.map(d=>({id:d.id,name:d.name,
        n:ORG_MEMBERS.filter(m=>(m.departments||[]).includes(d.name)).length,
        nAppt:ORG_MEMBERS.filter(m=>(m.departments||[]).includes(d.name)&&
          !(d.appointments||[]).some(a=>a.role_key!=='member'&&false)).length}));
      return {total:ORG_MEMBERS.length, deptCount:depts.length,
              pick:withCnt.sort((a,b)=>b.n-a.n)[0]||null};
    })()""")
    print('  ', json.dumps(base, ensure_ascii=False), flush=True)
    ok(base.get('deptCount', 0) > 0 and base.get('pick'), '存在部门节点（%d 个）' % base.get('deptCount', 0))
    d = base['pick']

    print('【② 选中部门「%s」→ 各岗位下拉候选仅含该部门成员】' % d['name'], flush=True)
    await ev("selectOrgNode(%d)" % d['id'])
    await asyncio.sleep(1)
    r2 = await ev("""(function(){
      const node=ORG_FLAT.find(x=>x.id===%d);
      const out=[];
      [...document.querySelectorAll('[id^=g_appt_sel_]')].forEach(sel=>{
        const rk=sel.id.replace('g_appt_sel_','');
        const optIds=[...sel.options].map(o=>Number(o.value)).filter(v=>v);
        const exp=orgApptCandidates(node,rk).map(m=>m.id);
        const allDept=optIds.every(id=>{const m=ORG_MEMBERS.find(x=>x.id===id);
          return m&&(m.departments||[]).includes(node.name);});
        const noDup=optIds.every(id=>!(node.appointments||[]).some(a=>a.member_id===id&&a.role_key===rk));
        out.push({rk:rk, n:optIds.length, matchesExp:JSON.stringify(optIds)===JSON.stringify(exp), allDept:allDept, noDup:noDup});
      });
      return {selects:out, expTotal:ORG_MEMBERS.filter(m=>(m.departments||[]).includes(node.name)).length};
    })()""" % d['id'])
    print('  ', json.dumps(r2, ensure_ascii=False), flush=True)
    ok(r2.get('selects') and all(s['matchesExp'] and s['allDept'] and s['noDup'] for s in r2['selects']),
       '%d 个岗位下拉候选全部=部门成员∩未任同岗位' % len(r2.get('selects') or []))

    print('【③ 组节点候选 = 所属部门成员（最近 dept 祖先）】', flush=True)
    r3 = await ev("""(function(){
      const g=ORG_FLAT.find(x=>x.node_type==='group'&&
        (function(){const byId={};ORG_FLAT.forEach(x=>byId[x.id]=x);
         let p=x.parent_id;while(p&&byId[p]){if(byId[p].node_type==='dept')return byId[p].name;p=byId[p].parent_id;}return null;})()==='%s');
      if(!g)return {found:false};
      const cands=orgApptCandidates(g,'member');
      const expDept=orgApptDeptOf(g);
      return {found:true, dept:expDept,
              n:cands.length, allDept:cands.every(m=>(m.departments||[]).includes(expDept))};
    })()""" % d['name'])
    print('  ', json.dumps(r3, ensure_ascii=False), flush=True)
    if r3.get('found'):
        ok(r3.get('dept') == d['name'], '组节点解析出所属部门=%s' % r3.get('dept'))
        ok(r3.get('allDept'), '组节点候选全部属于该部门（%s 个）' % r3.get('n'))
    else:
        print('  （当前架构无挂在该部门下的小组，跳过）')

    print('【④ 不属于该部门的成员不在候选中】', flush=True)
    r4 = await ev("""(function(){
      const node=ORG_FLAT.find(x=>x.id===%d);
      const outsiders=ORG_MEMBERS.filter(m=>!(m.departments||[]).includes(node.name)).map(m=>m.id);
      const sel=document.querySelector('[id^=g_appt_sel_]');
      const optIds=sel?[...sel.options].map(o=>Number(o.value)).filter(v=>v):[];
      return {outsiderN:outsiders.length, leaked:outsiders.filter(id=>optIds.includes(id)).length};
    })()""" % d['id'])
    print('  ', json.dumps(r4, ensure_ascii=False), flush=True)
    ok(r4.get('outsiderN', 0) > 0 and r4.get('leaked') == 0,
       '非本部门成员 %s 人全部被排除（泄漏 0）' % r4.get('outsiderN'))

    print('【⑤ 中心节点不限制（候选=全员-已任同岗位）】', flush=True)
    r5 = await ev("""(function(){
      const c=ORG_FLAT.find(x=>x.node_type==='center');
      if(!c)return {found:false};
      const rk=(c.roles||[]).map(r=>r.role_key)[0];
      if(!rk)return {found:false};
      const cands=orgApptCandidates(c,rk);
      const appointedN=(c.appointments||[]).filter(a=>a.role_key===rk).length;
      return {found:true, n:cands.length,
              exp:ORG_MEMBERS.length-appointedN, allIn:cands.every(m=>!!ORG_MEMBERS.find(x=>x.id===m.id))};
    })()""")
    print('  ', json.dumps(r5, ensure_ascii=False), flush=True)
    if r5.get('found'):
        ok(r5.get('n') == r5.get('exp'), '中心候选=全员-已任（%s = %s）' % (r5.get('n'), r5.get('exp')))
    else:
        print('  （中心节点无角色定义，跳过）')

    await ev("(function(){try{closeModal('wgModal');}catch(e){}})()")
    print('结果: PASS=%d' % _PASSED, flush=True)

asyncio.run(main())
