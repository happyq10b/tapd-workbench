# -*- coding: utf-8 -*-
"""T-205h：member-picker 勾选多选交互 CDP 实测（零写库）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9595
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205h')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', f'--remote-debugging-port={PORT}',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}

        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done():
                        f.set_result(m)

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2.5)

        r1 = await ev("""(function(){
          const host=document.createElement('div');
          host.id='__chk_test__';
          document.body.appendChild(host);
          initPersonPicker('__chk_test__', [], null, '', false);
          const o=PP['__chk_test__'];
          // 打开下拉
          o.rd('');
          const drop=o.drop;
          const open0=drop.style.display==='block';
          // ① 勾选形态：下拉项 = 行 + checkbox（#T-231 起 div+span 直调，label 移除）
          const labels=[].slice.call(drop.querySelectorAll('.pp-opt:not(.pp-all)'));
          const hasCb=labels.length>0&&labels.every(function(l){return !!l.querySelector('input[type=checkbox]');});
          const checked0=drop.querySelectorAll('input:checked').length;
          // ② 连续勾选 3 个（模拟点击 checkbox）→ 面板应保持打开、arr 同步、tags 更新
          labels.slice(0,3).forEach(function(l){l.querySelector('input[type=checkbox]').click();});
          const open1=drop.style.display==='block';
          const arrN=o.arr.length;
          const tagsN=host.querySelectorAll('.pp-tag').length;
          const cbChecked=drop.querySelectorAll('input:checked').length;
          // ③ 取消一个勾选 → arr 同步移除
          labels.slice(0,3)[0].querySelector('input[type=checkbox]').click();
          const arrAfterUn=o.arr.length;
          // ④ 全选条 → 全部勾选（真实路径：点击全选 checkbox → onchange → ppToggleAll）
          const allBar=drop.querySelector('.pp-all');
          allBar.querySelector('input[type=checkbox]').click();
          const arrAll=o.arr.length, allIn=o.ALL.every(n=>o.arr.includes(n));
          const allLabel=allBar.textContent.trim();
          // ⑤ 再点全选 → 取消（rd 重绘后 allBar 是新节点，须重查——真实用户每次点的都是新 DOM）
          const allBar2=drop.querySelector('.pp-all');
          allBar2.querySelector('input[type=checkbox]').click();
          const arrUn=o.arr.length, unLabel=allBar2.textContent.trim();
          // ⑥ 数据层与表单提交同源：arr 即 PP 容器数组（saveEdit 读同一数组）
          return {open0:open0, labelsN:labels.length, hasCb:hasCb, checked0:checked0,
                  open1:open1, arrN:arrN, tagsN:tagsN, cbChecked:cbChecked,
                  arrAfterUn:arrAfterUn, arrAll:arrAll, allIn:allIn, allLabel:allLabel,
                  arrUn:arrUn, unLabel:unLabel, poolN:o.ALL.length};
        })()""")
        print(json.dumps(r1, ensure_ascii=False, indent=1))
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205h')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
