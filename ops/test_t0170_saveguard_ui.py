# -*- coding: utf-8 -*-
"""T-0170 全局保存守卫 CDP 实测：遮罩/禁用/防重复/beforeunload/释放。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9470
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0170')
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

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % make_token('admin')
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    ok_login = False
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            ok_login = True
            break
    if not ok_login:
        snap = await ev("({url:location.href, api:typeof api, me:typeof ME})")
        print('   登录现场:', json.dumps(snap, ensure_ascii=False), flush=True)
    ok(ok_login, 'admin 登录成功')
    await asyncio.sleep(1.5)

    print('【① 保存资料：请求期间遮罩+禁用+beforeunload】', flush=True)
    await ev("openProfileModal()")
    await asyncio.sleep(2)
    # 延迟 /api/profile 响应 900ms，制造可观测的保存窗口；并计数 POST
    await ev("""(function(){
      window.__posts=0;
      const _f=window.fetch;
      window.fetch=function(u,o){
        const s=String(u);
        if(s.indexOf('/api/profile')>=0&&(o||{}).method==='POST')window.__posts++;
        const pr=_f.apply(this,arguments);
        if(s.indexOf('/api/profile')>=0&&(o||{}).method==='POST'){
          return new Promise(function(res){setTimeout(function(){res(pr)},900)});
        }
        return pr;
      };
    })()""")
    btn = await ev("!!document.querySelector('button[onclick*=\\'saveProfile\\']')")
    ok(btn, '找到「保存资料」按钮')
    await ev("document.querySelector('button[onclick*=\\'saveProfile\\']').click()")
    await asyncio.sleep(0.25)
    mid = await ev("""(function(){
      const ov=document.getElementById('saveGuard');
      const b=document.querySelector('button[onclick*=\\'saveProfile\\']');
      const evv=new Event('beforeunload',{cancelable:true});
      window.dispatchEvent(evv);
      const at=document.elementFromPoint(400,400);
      return {n:SG_N, ov:!!ov, z:ov?getComputedStyle(ov).zIndex:null,
              saving:document.documentElement.getAttribute('data-saving'),
              dis:b?b.disabled:null, busy:b?b.className.indexOf('sg-busy')>=0:null,
              unloadPrevented:evv.defaultPrevented, blocked:at?at.id=== 'saveGuard':false};
    })()""")
    print('  ', json.dumps(mid, ensure_ascii=False), flush=True)
    ok(mid.get('n', 0) > 0, '守卫计数激活（SG_N=%s）' % mid.get('n'))
    ok(mid.get('ov') and mid.get('z') == '5000', '全屏遮罩出现且压顶（z=5000）')
    ok(mid.get('saving') == '1', 'data-saving 标记')
    ok(mid.get('dis') is True and mid.get('busy'), '保存按钮已禁用并加忙碌态')
    ok(mid.get('unloadPrevented'), 'beforeunload 已注册（关闭/刷新会弹确认）')
    ok(mid.get('blocked'), '遮罩拦截页面交互（elementFromPoint 命中遮罩）')

    print('【② 请求期间重复点击 → 不发第二次请求】', flush=True)
    await ev("document.querySelector('button[onclick*=\\'saveProfile\\']').click()")
    await asyncio.sleep(1.8)
    end = await ev("""(function(){
      const evv=new Event('beforeunload',{cancelable:true});
      window.dispatchEvent(evv);
      const b=document.querySelector('button[onclick*=\\'saveProfile\\']');
      return {posts:window.__posts, n:SG_N, ov:!!document.getElementById('saveGuard'),
              saving:document.documentElement.getAttribute('data-saving'),
              reEnabled:b?!b.disabled:null, unloadClean:!evv.defaultPrevented};
    })()""")
    print('  ', json.dumps(end, ensure_ascii=False), flush=True)
    ok(end.get('posts') == 1, '保存请求只发出一次（防重复提交）')
    ok(end.get('n', 1) == 0 and not end.get('ov'), '请求返回后遮罩释放、计数归零')
    ok(end.get('saving') is None, 'data-saving 标记清除')
    ok(end.get('reEnabled'), '按钮恢复可用')
    ok(end.get('unloadClean'), 'beforeunload 守卫已解除（正常离开不再拦截）')

    print('【③ 守卫未激活时后台写请求（编辑锁心跳）不弹遮罩】', flush=True)
    await ev("api('/api/cards/__t_none__/heartbeat',{method:'POST'}).catch(function(){})")
    await asyncio.sleep(0.6)
    r3 = await ev("({n:SG_N, ov:!!document.getElementById('saveGuard')})")
    ok(r3.get('n', 1) == 0 and not r3.get('ov'), '心跳类后台写请求不触发守卫（零开销）')

    print('【④ 守卫包装清单已接线（抽样）】', flush=True)
    r4 = await ev("(function(){return {a:typeof saveProfile,b:typeof saveAllTeamMembers,c:typeof bulkDeleteChecked,d:typeof submitImport};})()")
    ok(all(v == 'function' for v in (r4.get('a'), r4.get('b'), r4.get('c'), r4.get('d'))),
       '保存入口函数均为可调用（包装后）')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
asyncio.run(main())

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
