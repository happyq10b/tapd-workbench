# -*- coding: utf-8 -*-
"""#120 实测：看板管理筛选样式统一 + 顶栏入口调整（架构管理→更多菜单，看板管理移除）

验证口径：
  ① 负责人筛选控件 = 原生 <select>（与归属部门/属性/状态同款外观，宽度高度一致）
  ② 负责人筛选交互保留：mousedown → 组织架构树弹窗打开（.tree-pick）
  ③ 顶栏：架构部门/可选看板两带标题行不再有入口按钮（archEntryBand/boardEntryBand 已删）
  ④ 【更多】菜单含「架构管理」(#wgBtn)，管理员可见、点击能打开架构管理弹窗
  ⑤ 无负责人筛选仍可用（label 回显 + 列表过滤口径不变）
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9420
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d121t')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=50 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:400]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)

        print('【① 顶栏入口调整】')
        r1 = await ev("""(function(){
          const more=document.getElementById('headerMoreMenu');
          const wg=document.getElementById('wgBtn');
          return {bandGone:!document.getElementById('archEntryBand')&&!document.getElementById('boardEntryBand'),
                  wgInMore:!!(more&&wg&&more.contains(wg)),
                  wgVisible:wg?wg.style.display!=='none':false,
                  bandText:(document.querySelector('.tb-board-band .tb-band-head')||{}).textContent||''};
        })()""")
        ok(r1.get('bandGone'), '两带标题行的入口槽已移除（archEntryBand/boardEntryBand 不存在）')
        ok(r1.get('wgInMore') and r1.get('wgVisible'), '「架构管理」在【更多】菜单内且管理员可见')
        ok((r1.get('bandText') or '').find('看板管理') < 0, '可选看板带标题行不再有「看板管理」按钮')

        print('【② 更多菜单打开 → 架构管理可用】')
        await ev("document.getElementById('headerMoreMenu').hidden=false;")
        await asyncio.sleep(0.5)
        vis = await ev("document.getElementById('headerMoreMenu').hidden===false && document.getElementById('wgBtn').offsetParent!==null")
        ok(vis, '菜单展开后架构管理项可见')
        await ev("openWgModal()")
        await asyncio.sleep(1.5)
        wgOpen = await ev("document.getElementById('wgModal').style.display==='flex'")
        ok(wgOpen, '点击架构管理 → 弹窗打开（功能不受位置变化影响）')
        await ev("closeModal('wgModal')")

        print('【③ 负责人筛选样式统一】')
        await ev("openBoardConfigModal()")
        await asyncio.sleep(3)
        r3 = await ev("""(function(){
          const own=document.getElementById('bcf_owner');
          const dept=document.getElementById('bcf_dept');
          if(!own||!dept)return {missing:true};
          const a=own.getBoundingClientRect(),b=dept.getBoundingClientRect();
          const ca=getComputedStyle(own),cb=getComputedStyle(dept);
          return {tag:own.tagName,w1:Math.round(a.width),h1:Math.round(a.height),
                  w2:Math.round(b.width),h2:Math.round(b.height),
                  fs1:ca.fontSize,fs2:cb.fontSize,bd1:ca.borderColor,bd2:cb.borderColor,
                  inFilterRow:!!own.closest('.bc-filter-row')};
        })()""")
        if r3.get('missing'):
            ok(False, '负责人控件缺失：%s' % r3)
        else:
            ok(r3.get('tag') == 'SELECT', '负责人筛选为原生 select（与归属部门/属性/状态同款）')
            ok(abs(r3['w1'] - r3['w2']) <= 2 and abs(r3['h1'] - r3['h2']) <= 2,
               '宽高一致：负责人 %sx%s vs 部门 %sx%s' % (r3['w1'], r3['h1'], r3['w2'], r3['h2']))
            ok(r3.get('fs1') == r3.get('fs2') and r3.get('bd1') == r3.get('bd2'),
               '字号/边框色一致（%s / %s）' % (r3.get('fs1'), r3.get('bd1')))

        print('【④ 负责人筛选交互保留（树弹窗）】')
        await ev("document.getElementById('bcf_owner').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
        await asyncio.sleep(1)
        treeOpen = await ev("!!document.querySelector('body>.tree-pick')")
        ok(treeOpen, 'mousedown → 组织架构树弹窗打开（原生下拉被拦截，交互不变）')
        await ev("closeTreePick()")
        # 「无负责人」筛选仍可用
        await ev("BC_FILTER.owner='__no_owner__';renderOwnerFilterBtn();renderBoardList();")
        await asyncio.sleep(1)
        r4 = await ev("""(function(){
          const own=document.getElementById('bcf_owner');
          const first=document.querySelector('#bcList .bc-item .cnt');
          return {label:own?(own.options[own.selectedIndex]||{}).textContent:'',
                  items:document.querySelectorAll('#bcList .bc-item').length};
        })()""")
        ok(r4.get('label') == '无负责人', '无负责人 label 回显正确：%s' % r4.get('label'))
        # 还原筛选
        await ev("BC_FILTER.owner='';renderOwnerFilterBtn();renderBoardList();")
        await ev("closeModal('boardConfigModal')")

        print('【⑤ 截图留档】')
        shot = await send('Page.captureScreenshot', {'format': 'png', 'clip': {'x': 0, 'y': 0, 'width': 1440, 'height': 950, 'scale': 1}})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d121_bc_after.png', 'wb').write(
            __import__('base64').b64decode(shot['data']))
        print('  截图: ops/.shots/d121_bc_after.png')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
