#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#80 导出模板 UI 实测（2026-11-06 用户需求）：

① 导出弹窗乱序勾选 → 存为模板 → 下拉出现
② 应用模板 → EXP_PICKS = 模板序 + 徽标渲染
③ 管理弹窗列表 → 名称/版式/字段 chips
④ 编辑 → 更新模式（按钮变「更新模板」）→ 改名保存生效
⑤ 删除（confirm 覆写为 true）→ 列表清空
⑥ 截图（管理列表 + 导出弹窗模板区）
不落库（测试创建的模板经 API 删除）。
"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9397
BASE = 'http://127.0.0.1:8100'
U, PWD = 'admin', 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'export_tpl.png')

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
    created = []
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

            # 清理上次运行残留（幂等保障）
            await ev("(async()=>{const d=await api('/api/export/templates');"
                     "for(const t of (d.templates||[])){await api('/api/export/templates/'+t.id,{method:'DELETE'})}"
                     "return 'ok'})()", aw=True)

            # ① 乱序勾选 → 存为模板
            await ev("openExportModal();")
            await asyncio.sleep(1)
            await ev("expNone();expToggle('week_no');expToggle('owner');expToggle('card_name');"
                     "document.getElementById('exp_tpl_name').value='__uitpl_季报';"
                     "saveExpTpl();")
            await asyncio.sleep(1)
            r = await ev("(function(){return {n:EXP_TPLS.length,t:EXP_TPLS[0],"
                         "opt:document.getElementById('exp_tpl_sel').options.length}})()")
            ok(r.get('n') == 1 and r.get('t', {}).get('name') == '__uitpl_季报', '模板已保存并出现在列表')
            created.append(r['t']['id'])
            ok(r.get('opt') == 2, '下拉出现模板选项（实际 %s 个 option）' % r.get('opt'))

            # ② 清空后应用模板 → EXP_PICKS = 模板序
            await ev("expNone();document.getElementById('exp_tpl_sel').value=EXP_TPLS[0].id;applyExpTpl();")
            r = await ev("EXP_PICKS.slice()")
            ok(r == ['week_no', 'owner', 'card_name'], '应用模板 → 勾选按模板序（实际 %s）' % r)
            r = await ev("""(function(){
              const on=[...document.querySelectorAll('#exp_fields .exp-field.on')];
              // DOM 顺序 = 弹窗展示顺序；徽标值 = 勾选顺序 → 断言看徽标集合
              return on.map(f=>f.querySelector('.exp-idx').textContent).sort().join(',');
            })()""")
            ok(r == '1,2,3', '序号徽标集合 = 1..3（展示序与勾选序解耦，实际 %s）' % r)

            # ③ 管理弹窗列表
            await ev("openExportTplManager();")
            await asyncio.sleep(1)
            r = await ev("""(function(){
              const rows=[...document.querySelectorAll('#exp_tpl_list > div')];
              return {rows:rows.length,chip:rows[0]?rows[0].querySelectorAll('span[style*=eef5ff]').length:0,
                      hasFmt:rows[0]?(rows[0].textContent.indexOf('xlsx')>=0):false};
            })()""")
            ok(r.get('rows') == 1, '管理列表 1 行（实际 %s）' % r.get('rows'))
            ok(r.get('chip') == 3, '字段 chips 3 个')
            ok(r.get('hasFmt') is True, '版式信息（xlsx）展示')

            # ④ 编辑 → 更新模式
            await ev("tplEdit(EXP_TPLS[0].id);")
            r = await ev("(function(){return {editing:EXP_EDITING_ID===EXP_TPLS[0].id,"
                         "btn:document.getElementById('exp_tpl_save').textContent,"
                         "name:document.getElementById('exp_tpl_name').value}})()")
            ok(r.get('editing') is True and r.get('btn') == '更新模板' and r.get('name') == '__uitpl_季报',
               '编辑模式：按钮变「更新模板」、名称回填')
            await ev("document.getElementById('exp_tpl_name').value='__uitpl_季报v2';saveExpTpl();")
            await asyncio.sleep(1)
            r = await ev("(function(){return {name:EXP_TPLS[0].name,editing:EXP_EDITING_ID,"
                         "btn:document.getElementById('exp_tpl_save').textContent}})()")
            ok(r.get('name') == '__uitpl_季报v2' and r.get('editing') == 0 and r.get('btn') == '保存为模板',
               '更新保存后名称生效、退出编辑模式（实际 %s）' % json.dumps(r, ensure_ascii=False))

            # ⑤ 删除（confirm 覆写）
            await ev("window.confirm=()=>true;openExportTplManager();")
            await asyncio.sleep(0.5)
            await ev("tplDelete(EXP_TPLS[0].id);")
            await asyncio.sleep(1)
            r = await ev("(function(){return {n:EXP_TPLS.length,empty:document.getElementById('exp_tpl_list').textContent.indexOf('暂无模板')>=0}})()")
            ok(r.get('n') == 0 and r.get('empty') is True, '删除后列表清空（暂无模板提示，实际 %s）' % json.dumps(r, ensure_ascii=False))
            created = []

            # ⑥ 截图：造 2 个模板 → 管理列表
            await ev("closeModal('exportTplModal');openExportModal();")
            await asyncio.sleep(0.8)
            await ev("expNone();expToggle('week_no');expToggle('card_name');"
                     "document.getElementById('exp_tpl_name').value='__uitpl_周报';saveExpTpl();")
            await asyncio.sleep(0.8)
            await ev("expNone();expToggle('owner');expToggle('cc');expToggle('label');"
                     "document.getElementById('exp_tpl_name').value='__uitpl_人员盘点';saveExpTpl();")
            await asyncio.sleep(0.8)
            await ev("openExportTplManager();")
            await asyncio.sleep(1)
            shot = await send('Page.captureScreenshot', {'format': 'png'})
            data = shot.get('data')
            if data:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, 'wb') as f:
                    f.write(base64.b64decode(data))
                print('截图已保存：%s' % OUT)
            # 清理测试模板
            r = await ev("(async()=>{for(const t of EXP_TPLS){await api('/api/export/templates/'+t.id,{method:'DELETE'})}return 'ok'})()", aw=True)
            print('清理:', r)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

asyncio.run(main())
