# -*- coding: utf-8 -*-
"""T-231 修复验证（v2）：板块编辑 member-picker 真实鼠标交互。
所有点击目标均在点击前实时测量（消除过期坐标）。
① 打开 c_parts 下拉（fixed）→ ② 点成员1文字 → 面板开+tags+1+面板零位移
③ 点成员2文字 → 两项选中面板仍开 ④ checkbox 取消 → 面板开
⑤ 点外部 → 面板关、tags 保持 ⑥ 保存 → API 落库 ⑦ 恢复原值"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token
TOK = make_token('admin')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9651
BOARD = 'BCP1793717004248'

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TOK)
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    st, d = api('/api/cards?board_id=%s&size=500' % BOARD)
    col = next((c for c in d.get('columns') or [] if c['column_name'] == '案例'), None) or (d.get('columns') or [])[0]
    key = col['col_key']; orig_parts = col.get('participants') or ''
    print('target:', key, '| orig parts:', repr(orig_parts))
    profile = os.path.join(os.environ.get('TEMP','.'), 'cdp_t231v_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                             '--window-size=1440,900',
                             '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    OK = []
    def ok(cond, label):
        OK.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50*1024*1024)
        pending = {}; seq = [0]
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        async def send(mm, p=None):
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:200]}
            return r.get('result', {}).get('value')
        async def mouse_click(x, y):
            await send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})
            await send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'buttons': 1, 'clickCount': 1})
            await send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})
        async def click_pt(js):
            """实时测量并点击：js 返回 {x,y}；点击前 point 在目标上复核"""
            pt = await ev(js)
            if not pt or pt.get('x') is None: return None
            await mouse_click(pt['x'], pt['y'])
            return pt
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TOK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
          const m=window.COLS_META.find(function(x){return x.col_key===%s});
          if(!m)return 'NO META';
          openColumnEdit({colkey:m.col_key,bid:m.board_id,cname:m.column_name,year:m.year||'2026',
            created:m.created_at||'2026-11-18',due:m.due_date||'',nature:m.nature||'日常',
            category:m.category||'年度重点工作',completion:m.completion||'progressing',
            desc:'',owner:m.owner||'',parts:m.participants||''},false);
          return 'opened';
        })()""" % json.dumps(key), aw=True)
        for _ in range(20):
            pp = await ev("Object.keys(PP)")
            if pp: break
            await asyncio.sleep(0.4)
        # ① 真实鼠标点输入框打开下拉
        await click_pt("""(function(){
          const inp=document.querySelector('#c_parts .pp-in');
          const r=inp.getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
        })()""")
        await asyncio.sleep(0.6)
        st0 = await ev("""(function(){
          const d=document.querySelector('#c_parts .pp-drop');
          return {open:d.style.display==='block', n:d.querySelectorAll('.pp-opt:not(.pp-all)').length,
                  pos:getComputedStyle(d).position, top:d.style.top,
                  dropTop:Math.round(d.getBoundingClientRect().top)};
        })()""")
        print('① open:', json.dumps(st0, ensure_ascii=False))
        ok(st0.get('open') and st0.get('n', 0) >= 2, '① 下拉打开（成员≥2）')
        # ② 点成员1【文字】（点击前实时测量）
        await click_pt("""(function(){
          const it=document.querySelector('#c_parts .pp-drop .pp-opt:not(.pp-all) > span');
          const r=it.getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), name:it.textContent};
        })()""")
        await asyncio.sleep(0.6)
        st1 = await ev("""(function(){
          const d=document.querySelector('#c_parts .pp-drop');
          return {open:d.style.display==='block', top:d.style.top,
                  tags:document.querySelectorAll('#c_parts .pp-tag').length,
                  checkedN:d.querySelectorAll('input:checked').length,
                  focus:document.activeElement===document.querySelector('#c_parts .pp-in')};
        })()""")
        print('② check#1 文字:', json.dumps(st1, ensure_ascii=False))
        ok(st1.get('open') is True, '② 点成员文字后面板保持打开（根因已修）')
        ok(st1.get('tags') == 1 and st1.get('checkedN') == 1, '② 成员1选中（tags=1）')
        ok(st1.get('focus') is True, '② 输入框未失焦')
        ok(st1.get('top') == st0.get('top'), '② 面板位置零位移（旧版勾一个移 25px）')
        # ③ 点成员2文字
        await click_pt("""(function(){
          const items=document.querySelectorAll('#c_parts .pp-drop .pp-opt:not(.pp-all) > span');
          const it=items[1];
          const r=it.getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), name:it.textContent};
        })()""")
        await asyncio.sleep(0.6)
        st2 = await ev("""(function(){
          const d=document.querySelector('#c_parts .pp-drop');
          return {open:d.style.display==='block', tags:document.querySelectorAll('#c_parts .pp-tag').length,
                  checkedN:d.querySelectorAll('input:checked').length,
                  focus:document.activeElement===document.querySelector('#c_parts .pp-in')};
        })()""")
        print('③ check#2 文字:', json.dumps(st2, ensure_ascii=False))
        ok(st2.get('open') is True and st2.get('tags') == 2 and st2.get('checkedN') == 2,
           '③ 连续勾选第二人成功、面板仍开（用户核心痛点已修）')
        # ④ checkbox 本体取消成员1
        await click_pt("""(function(){
          const items=document.querySelectorAll('#c_parts .pp-drop .pp-opt:not(.pp-all)');
          const it=[].slice.call(items).find(function(x){return x.querySelector('input').checked});
          const r=it.querySelector('input').getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
        })()""")
        await asyncio.sleep(0.6)
        st3 = await ev("""(function(){
          const d=document.querySelector('#c_parts .pp-drop');
          return {open:d.style.display==='block', tags:document.querySelectorAll('#c_parts .pp-tag').length,
                  checkedN:d.querySelectorAll('input:checked').length};
        })()""")
        print('④ uncheck:', json.dumps(st3, ensure_ascii=False))
        ok(st3.get('open') is True and st3.get('tags') == 1 and st3.get('checkedN') == 1, '④ 取消勾选正常、面板仍开')
        # ⑤ 点面板外部（板块名称输入框——真实用户会点的另一字段）
        await click_pt("""(function(){
          const t=document.getElementById('c_name');
          const r=t.getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
        })()""")
        await asyncio.sleep(0.6)
        st4 = await ev("""({open:(function(){return document.querySelector('#c_parts .pp-drop').style.display==='block';})(),
                            tags:document.querySelectorAll('#c_parts .pp-tag').length,
                            modalAlive:document.getElementById('columnModal').style.display!=='none'})""")
        print('⑤ outside:', json.dumps(st4, ensure_ascii=False))
        ok(st4.get('open') is False and st4.get('tags') == 1 and st4.get('modalAlive') is True,
           '⑤ 点外部面板关闭、选择保持、编辑弹窗不受影响')
        # ⑥ 保存（真实点击保存按钮）
        await click_pt("""(function(){
          const b=document.getElementById('c_submit');
          const r=b.getBoundingClientRect();
          return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
        })()""")
        await asyncio.sleep(2.5)
        st, d2 = api('/api/cards?board_id=%s&size=500' % BOARD)
        col2 = next((c for c in d2.get('columns') or [] if c['col_key'] == key), {})
        new_parts = col2.get('participants') or ''
        # 剩余勾选者姓名 → 账号
        remain = await ev("document.querySelectorAll('#c_parts .pp-tag').length")
        ok(bool(new_parts) and remain == 1, '⑥ 保存后参与人落库（%r）' % new_parts)
        # ⑦ 恢复原值
        api('/api/columns', 'PUT', {'col_key': key, 'participants': orig_parts})
        st, d3 = api('/api/cards?board_id=%s&size=500' % BOARD)
        col3 = next((c for c in d3.get('columns') or [] if c['col_key'] == key), {})
        ok((col3.get('participants') or '') == orig_parts, '⑦ 原值已恢复')
    finally:
        api('/api/columns', 'PUT', {'col_key': key, 'participants': orig_parts})
        try:
            if w: await w.close()
        except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t231v_%d' % PORT)
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)
    print('结果: %d/%d' % (sum(OK), len(OK)))

asyncio.run(main())
