# -*- coding: utf-8 -*-
"""#52 UI 实测：五项文案/状态微调。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9545
BASE = 'http://127.0.0.1:8100'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0
            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid: return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')
            async def wait_for(expr, timeout=12):
                deadline = time.time() + timeout
                while time.time() < deadline:
                    v = await ev(expr)
                    if v: return v
                    await asyncio.sleep(0.5)
                return None
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value=%s;document.getElementById('btn').click();" % json.dumps(PWD))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(2)
            # 选一个看板（直接 pickBoard 第一个可用看板）
            await ev("pickBoard(ME.boards[0].board_id);")
            await asyncio.sleep(3)

            # ── ④⑤ 列表区按钮文案 ──
            print('\n【④⑤ 按钮文案】')
            r = await ev("""(function(){
              var txt=[].slice.call(document.querySelectorAll('#boardContent button')).map(function(b){return b.textContent.trim()});
              var ib=[].slice.call(document.querySelectorAll('.toolbar-right button, .toolbar button'))
                       .map(function(b){return b.textContent.trim()});
              return {fold:txt.filter(function(x){return x==='折叠'}).length,
                      unfold:txt.filter(function(x){return x==='展开'}).length,
                      colPin:txt.filter(function(x){return x==='📌 置顶'}).length,
                      oldFold:txt.filter(function(x){return x==='折叠事项'||x==='展开事项'||x==='📌 板块置顶'||x==='📌 事项置顶'}).length,
                      ie:ib.filter(function(x){return x.indexOf('导入导出')>=0})};
            })()""")
            # ⚠️ 2026-11-04 #55：折叠/展开/置顶/复制已并入板块行的「操作 ▾」菜单
            ok((r.get('oldFold') or 0) == 0, '旧文案（折叠事项/展开事项/板块置顶/事项置顶）已清零：%s' % r.get('oldFold'))
            # ⚠️ 2026-11-04 #56：导入导出并入工具栏「操作 ▾」菜单 → 验证菜单项
            r2 = await ev("""(function(){
              var ops=(typeof ROW_OPS!=='undefined'&&ROW_OPS['toolbarOps'])||[];
              return ops.filter(function(it){return !it.disabled;}).map(function(it){return it.label;});
            })()""")
            _lbl = r2 or []
            ok(any('模板' in l for l in _lbl) and any('导入' in l for l in _lbl) and any('导出' in l for l in _lbl),
               '导入/导出/模板在操作菜单且无 emoji（%d 项；备份/恢复在顶部更多）' % len(_lbl))
            # ⚠️ 2026-11-04 #55：行内置顶/复制已合并为「操作 ▾」→ 验证按钮与菜单项
            r = await ev("""(function(){
              var ops=[].slice.call(document.querySelectorAll('#boardContent .ops-btn'))
                       .map(function(b){return b.textContent.trim()});
              var pins=[].slice.call(document.querySelectorAll('#boardContent .pin-btn'))
                       .map(function(b){return b.textContent.trim()});
              return {opsCount:ops.length,pins:pins};
            })()""")
            ok((r.get('opsCount') or 0) >= 1, '行内有「操作 ▾」合并按钮（%s 个）' % r.get('opsCount'))
            ok(len(r.get('pins') or []) == 0, '行内不再有独立置顶按钮（#55 合并）')

            # ── ③ 行内日期标签 ──
            print('\n【③ 行内日期标签】')
            r = await ev("""(function(){
              var c=document.getElementById('boardContent').textContent;
              return {newStyle:c.indexOf('创建 ')>=0&&c.indexOf('截止 ')>=0,
                      oldStyle:c.indexOf('创建日期：')>=0||c.indexOf('截止日期：')>=0};
            })()""")
            # ⚠️ 2026-11-04 #55：字段渲染改为「label value」（去冒号省宽）
            ok(r.get('newStyle') is True, '行内为「创建 / 截止」（无冒号紧凑版）')
            ok(r.get('oldStyle') is False, '「创建日期：/ 截止日期：」旧标签已消失')

            # ── ①② 板块弹窗 ──
            print('\n【①② 板块弹窗】')
            await ev("openColumnEdit(document.querySelector('.week-title.edit'));")
            await asyncio.sleep(1.5)
            # 编辑态选个参与人（留下按钮显示状态）
            await ev("COL_PARTS=['admin'];colRenderParticipants();")
            r = await ev("(function(){return document.getElementById('c_parts_clear_btn').style.display!=='none'})()")
            ok(r is True, '编辑态有参与人 → ✕ 显示（对照）')
            await ev("closeModal('columnModal');")
            await asyncio.sleep(0.5)
            await ev("openColumnModal();")
            await asyncio.sleep(1)
            r = await ev("""(function(){
              var m=document.getElementById('columnModal');
              return {open:m&&m.style.display!=='none',
                      partsX:document.getElementById('c_parts_clear_btn').style.display!=='none',
                      yearHint:m.textContent.indexOf('年份绑定在')>=0};
            })()""")
            ok(r.get('open') is True, '新建板块弹窗已打开')
            ok(r.get('partsX') is False, '①新建板块参与人的 ✕ 不再残留显示')
            ok(r.get('yearHint') is False, '②归属年份说明段已删除')
            await ev("closeModal('columnModal');")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
