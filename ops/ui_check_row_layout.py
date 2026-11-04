# -*- coding: utf-8 -*-
"""#55 布局优化 —— UI 实测（真实 Chrome + CDP）"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9577
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_l%d' % PORT)
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
            # 选一个有事项的看板
            await ev("""(async function(){
              var b=(typeof BC_BOARDS!=='undefined'&&BC_BOARDS[0])?BC_BOARDS[0].board_id:null;
              if(!b){var t=document.querySelector('#tbBoards button, #tbBoards .tab');if(t)t.click();}
              return true;
            })()""")
            await asyncio.sleep(3)

            # ── 1. 字段顺序与压缩 ──
            print('\n【1】字段顺序：周数在负责人左侧；压缩值')
            r = await ev("""(function(){
              const row=document.querySelector('.item-card');
              if(!row)return {found:false};
              const cols=[].slice.call(row.querySelectorAll('.fcol')).map(x=>x.textContent.trim());
              const fcols=row.querySelector('.fcols');
              return {found:true,cols:cols,width:fcols?Math.round(fcols.getBoundingClientRect().width):0};
            })()""")
            ok(r.get('found') is True, '事项行渲染')
            cols = r.get('cols') or []
            ok(cols.length if False else len(cols) >= 4, '四列字段渲染：%s' % cols)
            wi = cols.findIndex if False else next((k for k, c in enumerate(cols) if c.startswith('周数')), -1)
            oi = next((k for k, c in enumerate(cols) if c.startswith('负责人')), -1)
            ok(0 <= wi < oi, '周数在负责人左侧（周数@%d，负责人@%d）' % (wi, oi))
            ok(any('W' in c and '·' in c for c in cols), '周数压缩为「年·W周」形态：%s' % [c for c in cols if '周数' in c])
            ok(r.get('width', 0) <= 460, '字段列宽 ≤460（实测 %s，原 648）' % r.get('width'))

            # ── 2. 标题宽度翻倍 ──
            print('\n【2】标题宽度')
            r = await ev("""(function(){
              const t=document.querySelector('.item-card .item-title');
              return {w:t?Math.round(t.getBoundingClientRect().width):0};
            })()""")
            ok(r.get('w', 0) >= 400, '标题宽度 ≥400px（实测 %s，原先约 260）' % r.get('w'))

            # ── 3. 操作菜单合并 ──
            print('\n【3】操作菜单')
            r = await ev("""(function(){
              const row=document.querySelector('.item-card');
              const btn=row?row.querySelector('.slot-ops .ops-btn'):null;
              const oldPin=row?row.querySelector('.slot-pin'):null;
              const oldCopy=row?row.querySelector('.slot-copy'):null;
              return {btn:btn?btn.textContent.trim():'',noOldPin:!oldPin,noOldCopy:!oldCopy};
            })()""")
            ok(r.get('btn') == '操作 ▾', '「操作 ▾」按钮在（实测 %s）' % r.get('btn'))
            ok(r.get('noOldPin') and r.get('noOldCopy'), '旧 置顶/复制 按钮已移除')
            # 点开菜单
            await ev("(function(){const b=document.querySelector('.item-card .slot-ops .ops-btn');b.click();})()")
            await asyncio.sleep(0.6)
            r = await ev("""(function(){
              const m=document.getElementById('rowOpsMenu');
              return {open:!!m,items:m?[].slice.call(m.querySelectorAll('.row-ops-item')).map(x=>x.textContent.trim()):[]};
            })()""")
            ok(r.get('open') is True, '操作菜单打开')
            ok(any('置顶' in x for x in r.get('items') or []) and any('复制' in x for x in r.get('items') or []),
               '菜单含 置顶/复制：%s' % (r.get('items')))
            await ev("closeRowOps();")

            # ── 4. 子事项行同构 ──
            print('\n【4】子事项行')
            await ev("""(function(){
              const chev=document.querySelector('.item-chev');
              if(chev)chev.click();
            })()""")
            await asyncio.sleep(2)
            r = await ev("""(function(){
              const sub=document.querySelector('.sub-node');
              if(!sub)return {found:false};
              const cols=[].slice.call(sub.querySelectorAll('.fcol')).map(x=>x.textContent.trim());
              const btn=sub.querySelector('.slot-ops .ops-btn');
              const w=sub.querySelector('.fcols');
              return {found:true,cols:cols,btn:btn?btn.textContent.trim():'',
                      width:w?Math.round(w.getBoundingClientRect().width):0};
            })()""")
            ok(r.get('found') is True, '子事项行渲染（已展开目录）')
            scols = r.get('cols') or []
            swi = next((k for k, c in enumerate(scols) if c.startswith('周数')), -1)
            soi = next((k for k, c in enumerate(scols) if c.startswith('负责人')), -1)
            ok(0 <= swi < soi, '子事项周数也在负责人左侧')
            ok(r.get('btn') == '操作 ▾', '子事项也用「操作 ▾」')
            ok(r.get('width', 0) <= 460, '子事项字段列同宽（%s）' % r.get('width'))

            # ── 5. 板块行：字段 + 对齐 ──
            print('\n【5】板块行同构对齐')
            r = await ev("""(function(){
              const h=document.querySelector('.week-header');
              if(!h)return {found:false};
              const cols=[].slice.call(h.querySelectorAll('.week-fcols .fcol')).map(x=>x.textContent.trim());
              const bar=h.querySelector('.week-bar');
              const title=h.querySelector('.week-title');
              const fcols=h.querySelector('.week-fcols');
              const itemF=document.querySelector('.item-card .fcols');
              const itemT=document.querySelector('.item-card .item-title');
              const ops=h.querySelector('.slot-ops .ops-btn');
              const barR=bar?Math.round(bar.getBoundingClientRect().right):0;
              const barW=bar?Math.round(bar.getBoundingClientRect().width):0;
              const fL=fcols?Math.round(fcols.getBoundingClientRect().left):0;
              const itemTR=itemT?Math.round(itemT.getBoundingClientRect().right):0;
              const itemFL=itemF?Math.round(itemF.getBoundingClientRect().left):0;
              // 板块行的「负责人」列起点（进度条右端应与之对齐）
              const colOwner=h.querySelector('.week-fcols .fcol-owner');
              const ownerL=colOwner?Math.round(colOwner.getBoundingClientRect().left):0;
              // 事项行的「负责人」列起点（纵向对齐基准）
              const itemOwner=document.querySelector('.item-card .fcols .fcol-owner');
              const itemOwnerL=itemOwner?Math.round(itemOwner.getBoundingClientRect().left):0;
              const tailSlot=h.querySelectorAll('.item-tail .slot-overdue,.item-tail .slot-subtask,.item-tail .slot-status').length;
              return {found:true,cols:cols,barR:barR,barW:barW,fL:fL,itemTR:itemTR,itemFL:itemFL,
                      ownerL:ownerL,itemOwnerL:itemOwnerL,
                      ops:ops?ops.textContent.trim():'',tailSlot:tailSlot};
            })()""")
            ok(r.get('found') is True, '板块行渲染')
            ccols = r.get('cols') or []
            ok(any(c.startswith('负责人') for c in ccols) and any(c.startswith('创建') for c in ccols)
               and any(c.startswith('截止') for c in ccols),
               '板块行有 负责人/创建/截止 字段：%s' % ccols)
            # ⚠️ 2026-11-04 再调：进度条 96px（占满周数位格 + 左溢出 8px）；
            #    起点紧靠「n/N 完成」，终点距「负责人」16px。
            ok(abs(r.get('barW', 0) - 96) <= 2,
               '进度条长度 96px（实测 %s px）' % r.get('barW'))
            _bgap = r.get('ownerL', 0) - r.get('barR', 0)
            ok(12 <= _bgap <= 20,
               '进度条终点与负责人列间距 16px（实测 %s px）' % _bgap)
            # 板块行与事项行的「负责人」列仍纵向对齐（字段列起点一致）
            ok(abs(r.get('ownerL', 0) - r.get('itemOwnerL', 1)) <= 4,
               '板块负责人列与事项负责人列纵向对齐（%s vs %s）'
               % (r.get('ownerL'), r.get('itemOwnerL')))
            ok(r.get('ops') == '操作 ▾', '板块行也是「操作 ▾」（含 置顶/复制/折叠/展开）')
            ok(r.get('tailSlot') == 3, '板块行尾部 3 个空占位槽位与事项行同构')
            # 板块操作菜单含 折叠/展开
            await ev("(function(){const b=document.querySelector('.week-header .slot-ops .ops-btn');b.click();})()")
            await asyncio.sleep(0.6)
            r = await ev("(function(){const m=document.getElementById('rowOpsMenu');return m?[].slice.call(m.querySelectorAll('.row-ops-item')).map(x=>x.textContent.trim()):[];})()")
            ok(any('折叠' in x for x in r or []) and any('展开' in x for x in r or []),
               '板块菜单含 折叠/展开：%s' % r)
            await ev("closeRowOps();")

            # 截图留档
            await send('Page.captureScreenshot', {'format': 'png'})
            # 截图返回 base64，不落盘也行 —— 断言已覆盖
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
