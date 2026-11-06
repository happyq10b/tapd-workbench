#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#79 导出字段选择弹窗 UI 实测（2026-11-06 用户需求）：

① 弹窗打开 → 26 个字段、默认全选、序号 1..26
② 取消勾选靠前字段 → 后续字段序号**实时重排**（徽标 = 最新勾选顺序）
③ 重新勾选 → 追加为末序号
④ 乱序勾选 → EXP_PICKS 顺序 = 勾选先后（非弹窗展示顺序）
⑤ 清空后点导出 → toast「请至少勾选一个导出字段」
⑥ 勾选若干点导出 → exportXlsx 收到按序 fields 参数（拦截 fetch 断言）

附截图。不落库、无夹具。
"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9396
BASE = 'http://127.0.0.1:8100'
U, PWD = 'admin', 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'export_fields.png')

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_s2%d' % PORT)
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
                nonlocal i
                i += 1
                mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1080, 'height': 860, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)

            # ① 打开弹窗
            await ev("openExportModal();")
            await asyncio.sleep(1)
            r = await ev("""(function(){
              const m=document.getElementById('exportModal');
              const fs=[...document.querySelectorAll('#exp_fields .exp-field')];
              const on=fs.filter(f=>f.classList.contains('on'));
              return {shown:m&&m.style.display==='flex',total:fs.length,on:on.length,
                      firstIdx:on[0]?on[0].querySelector('.exp-idx').textContent:null,
                      lastIdx:on[on.length-1]?on[on.length-1].querySelector('.exp-idx').textContent:null};
            })()""")
            ok(r.get('shown') is True, '弹窗打开')
            ok(r.get('total') == 26 and r.get('on') == 26, '26 个字段、默认全选')
            ok(r.get('firstIdx') == '1' and r.get('lastIdx') == '26', '序号 1..26')

            # ② 取消勾选第 1 项（事项名称）→ 后续序号实时重排
            await ev("expToggle('card_name');")
            r = await ev("""(function(){
              const fs=[...document.querySelectorAll('#exp_fields .exp-field')];
              const on=fs.filter(f=>f.classList.contains('on'));
              return {on:on.length,newFirst:on[0].querySelector('.exp-idx').textContent,
                      pick0:EXP_PICKS[0]};
            })()""")
            ok(r.get('on') == 25 and r.get('newFirst') == '1',
               '取消第 1 项后序号实时重排（原第 2 项变 1）')
            ok(r.get('pick0') != 'card_name', 'EXP_PICKS 移除已取消项')

            # ③ 重新勾选 → 追加为末序号
            await ev("expToggle('card_name');")
            r = await ev("(function(){return {n:EXP_PICKS.length,last:EXP_PICKS[25],idx:document.querySelectorAll('#exp_fields .exp-field')[0].querySelector('.exp-idx').textContent}})()")
            ok(r.get('n') == 26 and r.get('last') == 'card_name' and r.get('idx') == '26',
               '重新勾选追加为末序号 26')

            # ④ 乱序勾选：清空后按「周数→负责人→事项名称」顺序点
            await ev("expNone();expToggle('week_no');expToggle('owner');expToggle('card_name');")
            r = await ev("EXP_PICKS.slice()")
            ok(r == ['week_no', 'owner', 'card_name'],
               'EXP_PICKS 顺序 = 勾选先后（非展示顺序）：%s' % r)

            # ⑤ 清空后导出 → toast 拦截
            await ev("expNone();document.getElementById('toast').textContent='';submitExport();")
            r = await ev("document.getElementById('toast').textContent")
            ok(r == '请至少勾选一个导出字段', '未勾选导出 → toast 提示（实际 %r）' % r)

            # ⑥ 勾选后导出 → fetch 带 fields 且顺序正确（拦截请求，不真下载）
            await ev("expToggle('card_name');expToggle('owner');")
            await ev("""window.__cap=null;
              const of=window.fetch;window.fetch=function(u,o){
                if(String(u).indexOf('/api/export/xlsx')>=0){window.__cap=String(u);return new Promise(()=>{});}
                return of.apply(this,arguments);};
              submitExport();0;""")
            await asyncio.sleep(1)
            r = await ev("(function(){if(!window.__cap)return null;const m=window.__cap.match(/fields=([^&]+)/);return m?decodeURIComponent(m[1]):null;})()")
            ok(r == 'card_name,owner', '导出请求 fields 参数按勾选顺序（实际 %r）' % r)

            # 截图（乱序勾选 3 项状态；⑥ 的导出动作已关弹窗 → 重新打开）
            await ev("expNone();expToggle('week_no');expToggle('owner');expToggle('card_name');"
                     "renderExpFields();document.getElementById('exportModal').style.display='flex';")
            await asyncio.sleep(0.5)
            shot = await send('Page.captureScreenshot', {'format': 'png'})
            data = shot.get('data')
            if data:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, 'wb') as f:
                    f.write(base64.b64decode(data))
                print('截图已保存：%s' % OUT)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

asyncio.run(main())
