# -*- coding: utf-8 -*-
"""#56 操作归拢 —— UI 实测"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9529
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_m%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
            break
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
                    return {'__error__': str(r['exceptionDetails'])[:400]}
                return r.get('result', {}).get('value')

            await send('Page.enable')
            await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            await ev("(function(){var t=document.querySelector('#tbBoards button, #tbBoards .tab');if(t)t.click();})()")
            await asyncio.sleep(3)

            # ── 1. 事项行：＋子事项并入菜单，tail 无 slot-sub ──
            print('\n【1】事项行操作归拢')
            r = await ev("""(function(){
              const row=document.querySelector('.item-card');
              if(!row)return {found:false};
              return {found:true,
                      noSubBtn:!row.querySelector('.sub-toggle'),
                      noSubSlot:!row.querySelector('.slot-sub'),
                      ops:row.querySelector('.slot-ops .ops-btn')?row.querySelector('.slot-ops .ops-btn').textContent.trim():''};
            })()""")
            ok(r.get('found') is True, '事项行渲染')
            ok(r.get('noSubBtn') is True, '「＋ 子事项」独立按钮已移除')
            ok(r.get('noSubSlot') is True, 'slot-sub 槽位已移除（宽度让给标题）')
            ok(r.get('ops') == '操作 ▾', '「操作 ▾」在')
            await ev("(function(){document.querySelector('.item-card .slot-ops .ops-btn').click();})()")
            await asyncio.sleep(0.6)
            r = await ev("(function(){const m=document.getElementById('rowOpsMenu');return m?[].slice.call(m.querySelectorAll('.row-ops-item')).map(x=>x.textContent.trim()):[];})()")
            ok(any('子事项' in x for x in r or []), '菜单含「＋ 子事项」：%s' % r)
            ok(any('置顶' in x for x in r or []) and any('复制' in x for x in r or []), '菜单含 置顶/复制')
            await ev("closeRowOps();")

            # ── 2. 子事项行 tail 同构 ──
            print('\n【2】子事项行')
            await ev("(function(){const c=document.querySelector('.item-chev');if(c)c.click();})()")
            await asyncio.sleep(2)
            r = await ev("""(function(){
              const sub=document.querySelector('.sub-node');
              if(!sub)return {found:false};
              return {found:true,noSubSlot:!sub.querySelector('.slot-sub'),
                      ops:!!sub.querySelector('.slot-ops .ops-btn')};
            })()""")
            ok(r.get('found') is True and r.get('noSubSlot') is True and r.get('ops') is True,
               '子事项行 tail 与父行同构（无 slot-sub、有操作按钮）')

            # ── 3. 板块行：＋事项并入菜单 ──
            print('\n【3】板块行')
            r = await ev("""(function(){
              const h=document.querySelector('.week-header');
              if(!h)return {found:false};
              return {found:true,noAddBtn:!h.querySelector('.add-item-btn'),
                      noSubSlot:!h.querySelector('.slot-sub'),
                      ops:h.querySelector('.slot-ops .ops-btn')?h.querySelector('.slot-ops .ops-btn').textContent.trim():''};
            })()""")
            ok(r.get('found') is True, '板块行渲染')
            ok(r.get('noAddBtn') is True, '「＋ 事项」独立按钮已移除')
            ok(r.get('noSubSlot') is True, 'slot-sub 槽位已移除')
            await ev("(function(){document.querySelector('.week-header .slot-ops .ops-btn').click();})()")
            await asyncio.sleep(0.6)
            r = await ev("(function(){const m=document.getElementById('rowOpsMenu');return m?[].slice.call(m.querySelectorAll('.row-ops-item')).map(x=>x.textContent.trim()):[];})()")
            ok(any('新建事项' in x for x in r or []), '板块菜单含「＋ 新建事项」：%s' % r)
            await ev("closeRowOps();")

            # ── 4. 工具栏：四按钮 → 一个操作菜单 ──
            print('\n【4】工具栏操作归拢')
            r = await ev("""(function(){
              const tr=document.querySelector('.toolbar-right');
              const btns=[].slice.call(tr.querySelectorAll('button')).map(b=>b.textContent.trim());
              const old=[].slice.call(tr.querySelectorAll('.fold-btn,.cp-copy-btn,.add-item-btn,#newBtn')).length;
              const search=document.getElementById('searchInput');
              return {btns:btns,old:old,
                      sw:Math.round(search.getBoundingClientRect().width),
                      gapFilled:(search.getBoundingClientRect().right<=tr.getBoundingClientRect().left+160)};
            })()""")
            btns = r.get('btns') or []
            ok(btns == ['清空筛选', '操作 ▾'], '工具栏只剩「清空筛选 + 操作 ▾」：%s' % btns)
            ok(r.get('old') == 0, '旧按钮（展开/折叠/导入导出/新建板块）已移除')
            # ⚠️ 搜索框吃掉 toolbar-left 全部剩余空间：L1190 - 固定控件616 - gap32 ≈ 550
            ok(r.get('sw', 0) >= 540, '搜索框拉宽并吃满剩余空间（实测 %s px，原上限 520）' % r.get('sw'))
            # 工具栏菜单内容
            await ev("(function(){document.getElementById('toolbarOpsBtn').click();})()")
            await asyncio.sleep(0.6)
            r = await ev("""(function(){
              const m=document.getElementById('rowOpsMenu');
              return m?[].slice.call(m.querySelectorAll('.row-ops-item,.row-ops-sep')).map(x=>x.textContent.trim()):[];
            })()""")
            items = r or []
            ok(any('新建板块' in x for x in items), '菜单含「＋ 新建板块」')
            ok(any('展开板块' in x for x in items) and any('折叠板块' in x for x in items), '菜单含 展开/折叠板块')
            # ⚠️ 2026-11-04 #56 最终口径：模板/导入/导出留在本菜单；备份/恢复在顶部【更多】（管理员级）
            ok(any('模板' in x for x in items) and any('导入' in x for x in items) and any('导出 Excel' in x for x in items),
               '菜单含 模板/导入/导出：%s' % items)
            ok(not any('备份' in x for x in items) and not any('恢复' in x for x in items),
               '本菜单不含 备份/恢复（已移到顶部更多，管理员级）：%s' % items)
            r2 = await ev("""(function(){
              var m=document.getElementById('headerMoreMenu');
              return m?[].slice.call(m.querySelectorAll('button')).map(function(b){return (b.id||'')+b.textContent.trim();}):[];
            })()""")
            hm = r2 or []
            ok(any('备份' in x for x in hm) and any('恢复' in x for x in hm), '顶部【更多】含 备份/恢复：%s' % hm)
            ok(not any('模板' in x for x in hm), '顶部【更多】不含 模板/导入/导出（留在筛选操作里）：%s' % hm)
            await ev("closeRowOps();")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
