#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【管理入口位置】守卫脚本（UI设计师 · 2026-11-03）

需求来源：用户要求「调整按钮位置」——
  ① 【架构管理】入口从独立带移入【架构部门】带的**标题行右侧**
  ② 【看板管理】入口从独立带移入【可选看板】带的**标题行右侧**
  ③ 按钮文字去掉「打开」二字（纯废话）

本脚本固化这三条需求，防止后续改动把入口又挪回独立带或加回「打开」。

为什么单独建脚本（而不是塞进现有脚本）：
  - ops/ui_check_perm_render.py 与 ops/ui_check_filter.py 的「带数量/带顺序」断言
    编码的是**旧结构**（四带 / 五带），结构变更后必然失效。
    那两个脚本归属主设计师（§0.3.1），本脚本不越权改它们，
    而是提供**与新结构对齐的独立守卫**。
  - 本脚本只读，不修改任何文件。

用法：
    python ops/ui_check_entry_pos.py
    python ops/ui_check_entry_pos.py --json     # 机器可读输出
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9461
BASE = "http://127.0.0.1:8100"
ADMIN = "admin"
PWD = "At159357"

FAILED = []


def ok(cond, msg):
    print(('  PASS ' if cond else '  FAIL ') + msg)
    if not cond:
        FAILED.append(msg)


PROBE = r"""
(function(){
  function bx(s){var e=document.querySelector(s);if(!e)return null;var b=e.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
            right:Math.round(b.right),bottom:Math.round(b.bottom)};}
  function sameRow(a,b){
    if(!a||!b)return false;
    return !(a.bottom<=b.y+2 || b.bottom<=a.y+2);
  }
  var wg=document.getElementById('wgBtn');
  var cfg=document.getElementById('boardConfigBtn');
  var deptTitle=document.querySelector('.tb-dept-band .tb-band-title');
  var boardTitle=document.querySelector('.tb-board-band .tb-band-title');
  var deptBand=document.querySelector('.tb-dept-band');
  var boardBand=document.querySelector('.tb-board-band');
  return JSON.stringify({
    bands:document.querySelectorAll('.tb-navgroup .tb-band').length,
    bandTitles:Array.prototype.map.call(
        document.querySelectorAll('.tb-navgroup .tb-band'),
        function(e){return (e.querySelector('.tb-band-title')||{}).textContent||'';}),
    // 旧的独立入口带必须已消失
    oldArchBand:!!document.querySelector('.tb-entry-band'),
    wgText:wg?wg.textContent:'',
    cfgText:cfg?cfg.textContent:'',
    wgRect:bx('#wgBtn'), cfgRect:bx('#boardConfigBtn'),
    deptTitleRect:bx('.tb-dept-band .tb-band-title'),
    boardTitleRect:bx('.tb-board-band .tb-band-title'),
    deptBandRect:bx('.tb-dept-band'),
    boardBandRect:bx('.tb-board-band'),
    wgSameRow:sameRow(bx('#wgBtn'),bx('.tb-dept-band .tb-band-title')),
    cfgSameRow:sameRow(bx('#boardConfigBtn'),bx('.tb-board-band .tb-band-title')),
    wgRightOfTitle:bx('#wgBtn')&&bx('.tb-dept-band .tb-band-title')
        ? bx('#wgBtn').x > bx('.tb-dept-band .tb-band-title').right : false,
    cfgRightOfTitle:bx('#boardConfigBtn')&&bx('.tb-board-band .tb-band-title')
        ? bx('#boardConfigBtn').x > bx('.tb-board-band .tb-band-title').right : false,
    wgInBand:bx('#wgBtn')&&bx('.tb-dept-band')
        ? (bx('#wgBtn').right<=bx('.tb-dept-band').right+1 && bx('#wgBtn').x>=bx('.tb-dept-band').x-1) : false,
    cfgInBand:bx('#boardConfigBtn')&&bx('.tb-board-band')
        ? (bx('#boardConfigBtn').right<=bx('.tb-board-band').right+1 && bx('#boardConfigBtn').x>=bx('.tb-board-band').x-1) : false,
    archNote:(document.querySelector('#archEntryRow .tb-entry-note')||{}).textContent||'',
    boardNote:(document.querySelector('#boardEntryRow .tb-entry-note')||{}).textContent||'',
    archNoteAbsent:!document.querySelector('#archEntryRow .tb-entry-note'),
    boardNoteAbsent:!document.querySelector('#boardEntryRow .tb-entry-note'),
    // 源码级：该说明文字的渲染入口已彻底移除（防止被改回来）
    noNoteInSource:(document.documentElement.innerHTML.indexOf('tb-entry-note')<0)
  });
})()
"""


async def run():
    prof = os.path.join(tempfile.gettempdir(), 'cdp_entrypos_%d' % PORT)
    shutil.rmtree(prof, ignore_errors=True)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + prof, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
                break
        except Exception:
            time.sleep(0.5)
    import websockets

    tg = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in tg if t.get('type') == 'page'][0]
    out = {}
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        i = 0

        async def send(mm, p=None):
            nonlocal i
            i += 1
            mid = i
            await ws.send(json.dumps({'id': mid, 'method': mm, 'params': p or {}}))
            while True:
                m2 = json.loads(await ws.recv())
                if m2.get('id') == mid:
                    return m2.get('result', {})

        async def ev(e):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='%s';document.getElementById('p').value='%s';"
                 "document.getElementById('btn').click();" % (ADMIN, PWD))
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await ev("!!document.getElementById('tbDepts')"):
                break
        await asyncio.sleep(2.5)
        raw = await ev(PROBE)
        out = json.loads(raw) if isinstance(raw, str) else raw
    shutil.rmtree(prof, ignore_errors=True)
    return out


def main():
    print('【管理入口位置】守卫脚本（UI设计师 · 2026-11-03）')
    d = asyncio.run(run())
    if not isinstance(d, dict) or d.get('__error__'):
        print('  （诊断）%s' % d)
        return 1

    print('\n【用例1】入口已并入所属带的标题行右侧')
    ok(d.get('bands') == 2, '导航区为两带（架构部门 / 可选看板）：%s' % d.get('bands'))
    ok(d.get('bandTitles') == ['架构部门', '可选看板'],
       '带标题顺序：%s' % ' / '.join(d.get('bandTitles') or []))
    ok(d.get('oldArchBand') is False, '旧的独立入口带（.tb-entry-band）已不存在')
    ok(d.get('wgSameRow') is True, '架构管理按钮与「架构部门」标题同行')
    ok(d.get('cfgSameRow') is True, '看板管理按钮与「可选看板」标题同行')
    ok(d.get('wgRightOfTitle') is True, '架构管理按钮在标题右侧')
    ok(d.get('cfgRightOfTitle') is True, '看板管理按钮在标题右侧')
    ok(d.get('wgInBand') is True, '架构管理按钮未越出架构部门带')
    ok(d.get('cfgInBand') is True, '看板管理按钮未越出可选看板带')

    print('\n【用例2】按钮文字不带「打开」')
    ok('打开' not in (d.get('wgText') or ''), '架构管理按钮无「打开」：%r' % d.get('wgText'))
    ok('打开' not in (d.get('cfgText') or ''), '看板管理按钮无「打开」：%r' % d.get('cfgText'))

    print('\n【用例3】**任何角色**都不显示权限范围说明（2026-11-03 用户要求：各用户界面都删掉）')
    ok(not (d.get('archNote') or '').strip(), '架构管理旁无说明文字：%r' % d.get('archNote'))
    ok(not (d.get('boardNote') or '').strip(), '看板管理旁无说明文字：%r' % d.get('boardNote'))
    ok(d.get('archNoteAbsent') is True, '架构管理未渲染 .tb-entry-note 节点')
    ok(d.get('boardNoteAbsent') is True, '看板管理未渲染 .tb-entry-note 节点')
    # 结构性断言：代码里已不再存在该说明的渲染入口（防止被改回来）
    ok(d.get('noNoteInSource') is True,
       '源码中已无 .tb-entry-note 渲染入口（任何角色都不会再出现该说明）')

    print('\n【结果】%s' % ('全部通过' if not FAILED else '失败 %d 项' % len(FAILED)))
    for f in FAILED:
        print('  FAILED: %s' % f)
    if '--json' in sys.argv:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    return 1 if FAILED else 0


if __name__ == '__main__':
    out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'",
                          'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
                         capture_output=True, text=True).stdout
    for l in out.splitlines():
        if 'cdp_entrypos_%d' % PORT in l:
            pid = l.strip().split(',')[-1].strip()
            if pid.isdigit():
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
    sys.exit(main())
