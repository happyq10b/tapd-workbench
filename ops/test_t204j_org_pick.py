# -*- coding: utf-8 -*-
"""T-204j（2026-11-17）架构管理·组员追加两项修复 —— CDP 实测：
  ① 勾选现任组长提交 → 拒绝提交 + 明确文案（组长与组员不可兼任）
  ② 勾选原有组员（预勾选态）提交 → 静默跳过，提示不列原有成员
  ③ 行数守恒：全程 org_appointments 零变化（拒绝路径无写操作）
数据安全守则 §3.4：本探针只走「被拒绝」分支，无任何写库动作。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, cleanup as cdp_cleanup  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9545
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def kill_profile_chrome():
    try:
        out = subprocess.run(
            ['wmic', 'process', "where", "name='chrome.exe'",
             "and CommandLine like '%%cdp_t204j%%'", 'get', 'ProcessId', '/FORMAT:VALUE'],
            capture_output=True, timeout=20).stdout.decode('gbk', errors='ignore')
        for line in out.splitlines():
            if line.startswith('ProcessId='):
                subprocess.run(['taskkill', '/PID', line.split('=')[1].strip(), '/F'],
                               capture_output=True, timeout=10)
    except Exception:
        pass


def appt_baseline(node_id):
    c = sqlite3.connect(DB)
    n_all = c.execute('SELECT COUNT(*) FROM org_appointments').fetchone()[0]
    n_node = c.execute('SELECT COUNT(*) FROM org_appointments WHERE node_id=?', (node_id,)).fetchone()[0]
    c.close()
    return n_all, n_node


async def main():
    import websockets
    # 基线：找成本组节点
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    grp = c.execute("SELECT id, name FROM org_nodes WHERE node_type='group' AND name='成本组'").fetchone()
    assert grp, '未找到成本组节点'
    nid = grp['id']
    leader = c.execute("SELECT m.name FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                       " WHERE a.node_id=? AND a.role_key='group_leader'", (nid,)).fetchone()
    member = c.execute("SELECT m.name FROM org_appointments a JOIN team_members m ON m.id=a.member_id"
                       " WHERE a.node_id=? AND a.role_key='member' LIMIT 1", (nid,)).fetchone()
    c.close()
    assert leader and member, '成本组缺少组长或组员任命（夹具前提不满足）'
    n_all0, n_node0 = appt_baseline(nid)
    print(f"基线：成本组(id={nid}) 组长={leader['name']} 样本组员={member['name']}；"
          f"org_appointments 全表={n_all0} 本节点={n_node0}", flush=True)

    tk = ensure_test_ui_account()   # #128：页面登录用一次性测试账号，不占 admin
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204j')
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
    try:
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
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
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
        cookie = 'tk=%s; path=/; Max-Age=86400' % tk
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'") is True:
                break
        await asyncio.sleep(1.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # 打开架构管理 + 打开成本组的组员树选人
        await ev("openWgModal()")
        await asyncio.sleep(1.5)
        r0 = await ev("""(function(){
          const node=ORG_FLAT.find(x=>x.id===%d);
          if(!node)return{found:false};
          openOrgMemberPick(node.id,'member',document.body);
          return {found:true};
        })()""" % nid)
        ok(r0.get('found') is True, '① 打开成本组组员树选人')
        await asyncio.sleep(0.8)

        # 场景 A：勾选现任组长 → 拒绝提交 + 明确文案（组长名取自 SQLite 基线）
        leader_name = leader['name']
        ok(bool(leader_name), f'①a 现任组长={leader_name}')
        await ev("TREE_PICK.selected=['%s'];" % ('__P__' + leader_name))
        await ev("treePickConfirm()")
        await asyncio.sleep(0.5)
        ta = await ev("document.getElementById('toast').textContent")
        ok('提交被拒绝' in (ta or '') and '组长与组员不可兼任' in (ta or ''),
           f'①b 组长兼任被拒绝且文案明确（实际：{ta}）')

        # 场景 B：勾选原有组员（预勾选态成员）→ 静默跳过，不提示原有成员
        await ev("openOrgMemberPick(%d,'member',document.body)" % nid)
        await asyncio.sleep(0.8)
        await ev("TREE_PICK.selected=['%s'];" % ('__P__' + member['name']))
        await ev("treePickConfirm()")
        await asyncio.sleep(0.5)
        tb = await ev("document.getElementById('toast').textContent")
        ok('未选择新增成员' in (tb or '') and '已是组员' not in (tb or ''),
           f'② 原有组员静默跳过、不进提示（实际：{tb}）')

        # 行数守恒（D3）：拒绝/跳过路径全程零写操作
        n_all1, n_node1 = appt_baseline(nid)
        ok(n_all0 == n_all1 and n_node0 == n_node1,
           f'③ 行数守恒：全表 {n_all0}→{n_all1}，本节点 {n_node0}→{n_node1}')

        errs = await ev("window.__errs")
        ok(not errs, f'④ 无 JS 错误（实际：{errs}）')
    finally:
        cdp_cleanup("cdp_t204j")
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
