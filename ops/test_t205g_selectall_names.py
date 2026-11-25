# -*- coding: utf-8 -*-
"""T-205g：① member-picker 全选 ② IME 选人清空 ③ 评论/操作记录人名渲染（零写库）"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9589
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205g')
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

        # ① 全选/取消全选（独立 picker 实例，30 人池）
        r1 = await ev("""(function(){
          const host=document.createElement('div');
          host.id='__pp_test__';
          document.body.appendChild(host);
          initPersonPicker('__pp_test__', [], null, '', false);
          const o=PP['__pp_test__'];
          // 模拟 IME：输入框输入筛选词
          o.inp.value='测试';
          ppToggle('__pp_test__', o.ALL[0]);           // 从下拉点选（IME 候选上屏后点选的等价路径）
          const clearedAfterToggle=(o.inp.value==='');
          ppToggleAll('__pp_test__', {checked:true});  // #205h 签名：cb 决定全选/清空
          const nAfterAll=o.arr.length, allIn=o.ALL.every(n=>o.arr.includes(n));
          ppToggleAll('__pp_test__', {checked:false}); // 再点 → 取消全选
          const nAfterUn=o.arr.length;
          return {clearedAfterToggle:clearedAfterToggle, nAfterAll:nAfterAll,
                  allIn:allIn, nAfterUn:nAfterUn, poolN:o.ALL.length,
                  tagN:host.querySelectorAll('.pp-tag').length};
        })()""")
        print('① 全选/IME:', json.dumps(r1, ensure_ascii=False))

        # ② 真实数据人名渲染：打开综合工作事项（测试）看板 → 找有评论的板块/事项
        await ev("pickBoard('1162069797001000238')")
        await asyncio.sleep(2.5)
        # 直接调渲染管线：取第一个板块的评论接口数据，检查 who 文本
        r2 = await ev("""(async function(){
          // 找一个有评论的 card（真实存量）
          const cs=await api('/api/cards?board_id=1162069797001000238').then(d=>d.cards||[]);
          const hit=[];
          for(const c of cs.slice(0,30)){
            try{
              const d=await api('/api/cards/'+c.card_id+'/comments');
              if(d.comments&&d.comments.length){hit.push({id:c.card_id,cs:d.comments});break;}
            }catch(e){}
          }
          if(!hit.length)return {noData:true};
          const x=hit[0].cs[0];
          return {acc:x.username, nameShown:bcMemberName(x.username),
                  same:(bcMemberName(x.username)!==x.username)||('映射缺失回退：'+x.username)};
        })()""", aw=True)
        print('② 真实评论人名映射:', json.dumps(r2, ensure_ascii=False))

        # ③ 板块浏览弹窗渲染（真实存量：综合工作事项（测试）第一个板块）
        r3 = await ev("""(function(){
          const titles=[].slice.call(document.querySelectorAll('.week-title'));
          const el=titles[0];
          if(!el)return {found:false};
          try{el.click();}catch(e){}
          return {found:true};
        })()""")
        await asyncio.sleep(2)
        r3b = await ev("""(function(){
          const who=[].slice.call(document.querySelectorAll('#cd_comments .who,#cd_actions .who'))
            .map(function(x){return x.textContent.trim();});
          const m=document.getElementById('columnDetailModal');
          return {open:!!(m&&m.style.display&&m.style.display!=='none'), who:who.slice(0,6)};
        })()""")
        print('③ 板块浏览 who 渲染:', json.dumps(r3b, ensure_ascii=False))
    finally:
        if w:
            try:
                await w.close()
            except Exception:
                pass
        from cdp_test_helper import kill_profile_chrome, force_offline_and_remove
        kill_profile_chrome('cdp_t205g')
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
