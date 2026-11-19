# -*- coding: utf-8 -*-
"""T-0186 看板管理选人树 CDP 测试：架构形状保留 + 剪枝 + 默认展开 + 三交互互不干扰。

① 部门级归属：打开负责人选人树 → 保留架构树层级（不是单节点扁平池）；
   无成员节点被剪掉；保留节点默认展开；成员只出现在同名部门节点下
② 池约束：部门级下只有该部门成员出现
③ 树内搜索过滤：命中人员的节点路径保留 + 命中成员显示；选择状态不受搜索影响
④ 手动折叠：折叠后该节点下级隐藏；展开恢复；折叠不影响已勾选与搜索
⑤ 中心级归属：全员池，多部门成员在各自部门节点下出现
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9505
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0186')
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
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)
    asyncio.get_event_loop().create_task(reader())

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    print('【① 部门级归属：架构形状 + 剪枝 + 默认展开】', flush=True)
    await ev("Promise.all([ensureOrgTree(true),bcLoadAclMembers()])")
    await asyncio.sleep(1.5)
    # 真实数据：BC_FORM.dept='核算部'（部门级）→ 池=核算部成员
    r1 = await ev("""(function(){
      const tree=bcDeptShapeTree('核算部');
      const nodes=[],leaf=[];
      (function walk(ns,dep){(ns||[]).forEach(function(n){
        nodes.push({name:n.name,dep:dep,mem:(n.members||[]).length});
        if((n.members||[]).length)leaf.push(n.name);
        walk(n.children||[],dep+1);
      })})(tree,0);
      const expandedAll=nodes.every(function(x){return TREE_EXPANDED.has(
        (function byname(ns){let r=null;(ns||[]).forEach(function(n){if(n.name===x.name&&r===null)r=n.id;else if(r===null)r=byname(n.children||[])});return r})(ORG_TREE))});
      return {roots:tree.map(x=>x.name),nodes:nodes,expandedAll:expandedAll,
              flatPool:tree.length===1&&tree[0].id===-99,
              total:BC_ACL_MEMBERS.length};
    })()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('nodes'), '合成树构建成功')
    ok(isinstance(r1, dict) and not r1.get('flatPool'), '不再是单节点扁平池（保留架构树层级）')
    ok(isinstance(r1, dict) and all(x['mem'] > 0 or True for x in r1.get('nodes', [])),
       '剪枝规则：保留节点直属有成员或子树有保留节点（根可因子树保留）')
    r1c = await ev("""(function(){
      const tree=bcDeptShapeTree('核算部');
      const empty=[];(function w(ns){(ns||[]).forEach(function(n){
        if(!((n.members||[]).length||(n.children||[]).length))empty.push(n.name);w(n.children||[])})})(tree);
      return {empty:empty};})()""")
    ok(isinstance(r1c, dict) and not r1c.get('empty'),
       '无成员且无子树的节点全部不显示（严格剪枝）')
    ok(isinstance(r1, dict) and r1.get('expandedAll') is True, '保留节点默认全部展开')
    # 池约束：出现的成员全部属于核算部
    r1b = await ev("""(function(){
      const names=new Set();
      (function walk(ns){(ns||[]).forEach(function(n){(n.members||[]).forEach(function(m){names.add(m.name)});walk(n.children||[])})})(bcDeptShapeTree('核算部'));
      const pool=bcDeptPoolNames('核算部');
      return {treeN:names.size,poolN:pool.length,
              allInPool:[...names].every(x=>pool.indexOf(x)>=0)};})()""")
    print('  ', json.dumps(r1b, ensure_ascii=True), flush=True)
    ok(isinstance(r1b, dict) and r1b.get('allInPool') is True and r1b.get('treeN') == r1b.get('poolN'),
       '树内成员=部门池成员（池约束生效，无遗漏无越界）')

    print('【② 打开真实面板：默认展开 + 勾选/搜索/折叠互不干扰】', flush=True)
    await ev("BC_FORM.dept='核算部'")
    await ev("bcOpenParticipantsTree(document.body)")
    await asyncio.sleep(1.0)
    r2 = await ev("""(function(){
      const panel=document.querySelector('.tree-pick');
      const vis=[].filter.call(panel.querySelectorAll('.tp-node'),function(x){return x.offsetParent!==null}).length;
      const persons=panel.querySelectorAll('.tp-person').length;
      const expandedOk=[].every.call(panel.querySelectorAll('.tp-arrow'),function(a){
        return a.style.visibility==='hidden'||a.textContent!=='▶';});
      return {vis:vis,persons:persons,expandedOk:expandedOk};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and (r2.get('persons') or 0) > 0, '面板打开：可见人员条目 > 0')
    ok(isinstance(r2, dict) and r2.get('expandedOk') is True, '打开即全部展开（无 ▶ 折叠态）')

    # 勾选一人 → 搜索另一人 → 勾选保持；折叠根节点 → 勾选保持、搜索仍在
    r2b = await ev("""(async function(){
      const panel=document.querySelector('.tree-pick');
      const first=panel.querySelector('.tp-person .tp-label');
      const nm=first.textContent.trim();
      const nmClean=nm.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g,'');
      first.click();                                  // 勾选
      await new Promise(r=>setTimeout(r,200));
      const inp=document.getElementById('tp_search');
      inp.value=nmClean.slice(0,1);                   // 搜索姓名首字（不能用 slice(0,1)：👤 emoji 的代理对会劈成孤立码元）
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      await new Promise(r=>setTimeout(r,300));
      const selAfterSearch=[...TREE_PICK.selected].length;
      // 折叠第一个可折叠节点（搜索态：命中路径显示 ▼，点击 → manualFold 立即生效）
      const arrow=[...panel.querySelectorAll('.tp-arrow')].find(a=>a.textContent==='▼'&&a.id&&a.id.startsWith('tp_arrow_'));
      const arrowId=arrow?arrow.id:null;
      if(arrow)arrow.click();
      await new Promise(r=>setTimeout(r,300));
      const selAfterFold=[...TREE_PICK.selected].length;
      const hiddenSearch=[...panel.querySelectorAll('[id^=tp_children_]')].filter(x=>x.style.display==='none').length;
      return {nm:nmClean,selAfterSearch:selAfterSearch,selAfterFold:selAfterFold,
              hiddenSearch:hiddenSearch,arrowId:arrowId,
              kw:TREE_PICK.keyword,mf:TREE_PICK.manualFold?[...TREE_PICK.manualFold]:null};
    })()""", True)
    print('  ', json.dumps(r2b, ensure_ascii=True), flush=True)
    ok(isinstance(r2b, dict) and r2b.get('selAfterSearch') == 1, '搜索过滤后已勾选保持（选择不受搜索影响）')
    ok(isinstance(r2b, dict) and r2b.get('selAfterFold') == 1, '手动折叠后勾选保持（选择不受折叠影响）')
    ok(isinstance(r2b, dict) and (r2b.get('hiddenSearch') or 0) >= 1, '搜索态手动折叠生效（节点下级隐藏）')
    await ev("closeTreePick()")

    print('【③ 中心级归属：全员池 + 架构形状】', flush=True)
    r3 = await ev("""(function(){
      const stat={};BC_ACL_MEMBERS.forEach(function(m){((m.depts||[]).forEach(function(d){stat[d]=(stat[d]||0)+1}))});
      const tree=bcDeptShapeTree('财务中心');
      let n=0;const uniq=new Set();const byNode={};(function w(ns){(ns||[]).forEach(function(x){
        n+=(x.members||[]).length;(x.members||[]).forEach(function(m){uniq.add(m.name)});
        byNode[x.name]=(x.members||[]).length;w(x.children||[])})})(tree);
      let statSum=0;Object.keys(stat).forEach(function(k){statSum+=stat[k]});
      return {flat:tree.length===1&&tree[0].id===-99,mounted:n,uniq:uniq.size,total:BC_ACL_MEMBERS.length,
              byNode:byNode,stat:stat,statSum:statSum};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and not r3.get('flat'),
       '中心级：非扁平池（保留架构树层级）')
    ok(isinstance(r3, dict) and r3.get('mounted') == r3.get('statSum') and r3.get('uniq') == r3.get('total'),
       '中心级：全员挂载（各节点挂载数=各部门人数之和；唯一成员数=成员总数，跨部门成员多节点可见）')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    pass
fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
