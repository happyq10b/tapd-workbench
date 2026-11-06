#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#82 导入弹窗 + 模板样式校准 实测：

【A】导入弹窗（#82-2）
① openImportModal → 弹窗可见、拖拽区显示、开始导入禁用
② impSetFile（模拟点击选择/拖拽落点，两者最终都走同一入口）→ 文件名显示、
   开始导入启用；非 .xlsx 被拒
③ 拖拽事件（DataTransfer 模拟 drop）→ 文件被接收
④ 模板下载按钮在弹窗内存在；外部菜单不再有「下载导入模板」（hp_feat 已测）
⑤ submitImport → /api/import/xlsx 请求拦截（不发真请求，不写库）
【B】导入模板提示样式校准（#82-3）
⑥ GET /api/import/template → openpyxl 检查：表头填充 F2F2F2、必填列字色
   B42318、边框 D0D0D0、无红底重涂抹；字段说明表头同规范；使用说明标题主色
"""
import asyncio, base64, io, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9400
BASE = 'http://127.0.0.1:8100'
U, PWD = 'admin', 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'import_modal.png')

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

            print('\n【A】导入弹窗')
            await ev("openImportModal();")
            await asyncio.sleep(0.8)
            r = await ev("""(function(){
              const m=document.getElementById('importModal');
              return {shown:m&&m.style.display==='flex',
                      drop:!!document.getElementById('imp_drop')&&!document.getElementById('imp_drop').hidden,
                      goDisabled:document.getElementById('imp_go').disabled,
                      tplBtn:[...document.querySelectorAll('#importModal button')].some(b=>b.textContent.indexOf('下载导入模板')>=0)};
            })()""")
            ok(r.get('shown') is True, '导入弹窗打开')
            ok(r.get('drop') is True, '拖拽/点击上传区显示')
            ok(r.get('goDisabled') is True, '未选文件时「开始导入」禁用')
            ok(r.get('tplBtn') is True, '模板下载入口在弹窗内')

            # ② 选文件（模拟点击选择后的回调）
            await ev("impSetFile(new File(['x'],'测试数据.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));")
            r = await ev("""(function(){return {name:document.getElementById('imp_file_name').textContent,
                       shown:document.getElementById('imp_file').style.display,
                       goDisabled:document.getElementById('imp_go').disabled}})()""")
            ok(r.get('name') == '测试数据.xlsx' and r.get('shown') == 'flex', '文件选中态显示文件名')
            ok(r.get('goDisabled') is False, '选中后「开始导入」启用')

            # 非 xlsx 拒绝
            await ev("impSetFile(new File(['x'],'bad.csv',{type:'text/csv'}));")
            r = await ev("document.getElementById('imp_file_name').textContent")
            ok(r == '测试数据.xlsx', '非 .xlsx 文件被拒（文件名保持不变）')

            # ③ 拖拽 drop 模拟
            await ev("""(function(){
              const dt=new DataTransfer();
              dt.items.add(new File(['x'],'拖拽导入.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
              const dz=document.getElementById('imp_drop');
              dz.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));
            })()""")
            r = await ev("document.getElementById('imp_file_name').textContent")
            ok(r == '拖拽导入.xlsx', '拖拽落点接收文件（实际 %r）' % r)

            # ⑤ 请求拦截（不发真请求）
            await ev("""window.__cap=null;
              const of=window.fetch;window.__of=of;window.fetch=function(u,o){
                if(String(u).indexOf('/api/import/xlsx')>=0){window.__cap={url:String(u),method:(o&&o.method)||'GET'};
                  return new Promise(()=>{});}
                return of.apply(this,arguments);};
              submitImport();0;""")
            await asyncio.sleep(1)
            r = await ev("window.__cap")
            ok(r and r.get('method') == 'POST' and '/api/import/xlsx' in r.get('url', ''),
               'submitImport 走 POST /api/import/xlsx（拦截断言）')
            await ev("window.fetch=window.__of;")
            await ev("impShowResult('','');")

            # 截图（文件选中态）
            await ev("impSetFile(new File(['x'],'季度数据导入.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));")
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

    print('\n【B】导入模板提示样式校准')
    from app.app import make_token, XLSX_IMPORT_COLS, XLSX_REQUIRED
    tok = make_token('admin')
    req = urllib.request.Request(BASE + '/api/import/template', headers={'Authorization': 'Bearer ' + tok})
    body = urllib.request.urlopen(req, timeout=20).read()
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(body))
    ws = wb['导入数据']
    req_idx = XLSX_IMPORT_COLS.index('card_name') + 1        # 必填列（事项名称 *）
    opt_idx = XLSX_IMPORT_COLS.index('card_id') + 1          # 非必填列（第一列）
    h1 = ws.cell(1, req_idx)
    h2 = ws.cell(1, opt_idx)
    ok('事项名称' in str(h1.value) and '*' in str(h1.value), '必填表头带 * 号（实际 %r）' % h1.value)
    ok(h1.fill.fgColor.rgb in ('00F2F2F2', 'FFF2F2F2'), '必填表头填充 = 浅灰 F2F2F2（实际 %s）' % h1.fill.fgColor.rgb)
    ok((h1.font.color.rgb or '').endswith('B42318'), '必填列红字标注（实际 %s）' % (h1.font.color.rgb,))
    ok(h2.fill.fgColor.rgb in ('00F2F2F2', 'FFF2F2F2') and (h2.font.color.rgb or '').endswith('1F1F1F'),
       '非必填表头 = 浅灰底深色字（无红底重涂抹）')
    bd = h1.border.left.color.rgb if h1.border.left and h1.border.left.color else None
    ok(bd and bd.endswith('D0D0D0'), '边框 D0D0D0 与导出规范一致（实际 %s）' % bd)
    ws2 = wb['字段说明']
    ok(ws2.cell(1, 1).fill.fgColor.rgb in ('00F2F2F2', 'FFF2F2F2'), '字段说明表头同规范')
    ws3 = wb['使用说明']
    ok((ws3['A1'].font.color.rgb or '').endswith('002D74') and ws3['A1'].font.bold,
       '使用说明标题主色粗体')

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

asyncio.run(main())
