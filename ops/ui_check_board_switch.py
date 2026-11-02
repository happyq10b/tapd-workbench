#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""看板板块切换联动的浏览器专项测试（真实 Chrome + CDP）

覆盖用户提的 3 个需求：
  1) 板块切换不彻底 —— 选新部门后残留上一个部门的板块内容
  2) 空状态处理   —— 该板块无数据时显示明确提示，而非留白/占位
  3) 初始状态     —— 进入看板后未选板块时，内容区默认为空（请选择板块）

运行：ops/.localvenv/Scripts/python.exe ops/ui_check_board_switch.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:8100'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9460
USER, PWD = 'admin', 'At159357'

PASS, FAIL = [], []


def ok(cond, msg):
    if cond:
        PASS.append(msg)
        print('  PASS ' + msg)
    else:
        FAIL.append(msg)
        print('  ✗ ' + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT,
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen(
        'http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]

    import websockets
    async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate',
                           {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:400]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';"
                 "document.getElementById('btn').click();")
        await asyncio.sleep(5)

        STATE_JS = """(function(){
            function txt(sel){var e=document.querySelector(sel);
                return e?(e.innerText||'').replace(/\\s+/g,' ').trim():null;}
            var rows=document.querySelectorAll('.item-card').length;
            var owners=[].slice.call(document.querySelectorAll('.item-card .fcol-owner')).map(function(e){
                return e.textContent.replace(/^负责人：/,'').trim();});
            return {curBoard:curBoard||'',
                    content:txt('#boardContent')||'',
                    stat:txt('#progressOverview')||'',
                    rowCount:rows,
                    boardTabs:[].slice.call(document.querySelectorAll('#tbBoards .tab-btn'))
                                 .map(function(b){return b.textContent.trim();}),
                    deptOpen:Object.keys(DEPT_OPEN).filter(function(k){return DEPT_OPEN[k];}),
                    allEmpty:owners.length?owners.every(function(o){return !o||o==='—';}):null};
        })()"""

        def click_dept(name):
            return ("(function(){var els=[].slice.call(document.querySelectorAll('#tbDepts .tree-dept'));"
                    "var t=els.find(function(e){return e.textContent.indexOf('%s')>=0;});"
                    "if(t)t.click();})()" % name)

        # ---------- 用例 1：初始状态（需求3） ----------
        print('\n【用例1】初始状态：未选板块时内容区为空')
        r = await ev(STATE_JS)
        ok(r.get('curBoard') == '', '初始未选中任何板块（curBoard 为空）：%r' % r.get('curBoard'))
        ok(r.get('rowCount') == 0, '初始不渲染任何事项（.item-card = %s）' % r.get('rowCount'))
        ok('请选择板块' in (r.get('content') or ''),
           '初始内容区显示「请选择板块」：%s' % (r.get('content') or '')[:30])
        ok(len(r.get('boardTabs') or []) > 0,
           '板块 tab 已渲染（供用户选择）：%d 个' % len(r.get('boardTabs') or []))

        # ---------- 用例 2：选中板块后正常渲染 ----------
        print('\n【用例2】主动选择板块后渲染对应内容')
        await ev("(function(){var t=document.querySelectorAll('#tbBoards .tab-btn')[0];"
                 "if(t)t.click();})()")
        await asyncio.sleep(2.2)
        r = await ev(STATE_JS)
        ok(r.get('curBoard') != '', '已选中板块：%s' % r.get('curBoard'))
        ok(r.get('rowCount') > 0, '该板块的事项已渲染（%s 条）' % r.get('rowCount'))
        ok('请选择板块' not in (r.get('content') or ''), '内容区不再是空状态提示')

        # ---------- 用例 3：切到 0 板块的部门 → 无残留（需求1+2） ----------
        print('\n【用例3】切到无板块的部门：不残留上个板块内容')
        before_rows = r.get('rowCount')
        await ev(click_dept('总账部'))
        await asyncio.sleep(2.2)
        r = await ev(STATE_JS)
        ok(r.get('curBoard') == '', '切走后 curBoard 清空：%r' % r.get('curBoard'))
        ok(r.get('rowCount') == 0,
           '上一个板块的事项已清空（%s → %s）' % (before_rows, r.get('rowCount')))
        ok('该板块暂无数据' in (r.get('content') or ''),
           '显示「该板块暂无数据」：%s' % (r.get('content') or '')[:30])
        ok(not (r.get('boardTabs') or []), '板块 tab 也已清空（不残留上个部门的板块）')

        # ---------- 用例 4：切回有板块的部门 → 仍是空状态直到用户选 ----------
        print('\n【用例4】切回有板块的部门：仍需用户主动选择')
        await ev(click_dept('核算部'))
        await asyncio.sleep(2.2)
        r = await ev(STATE_JS)
        ok(len(r.get('boardTabs') or []) > 0, '新部门的板块 tab 已显示：%d 个' % len(r.get('boardTabs') or []))
        ok(r.get('rowCount') == 0, '未选板块前列表仍为空（%s 条）' % r.get('rowCount'))
        ok('请选择板块' in (r.get('content') or ''),
           '内容区提示「请选择板块」：%s' % (r.get('content') or '')[:30])

        # ---------- 用例 5：选另一个板块 → 统计与内容同步联动 ----------
        print('\n【用例5】切换板块：统计与内容同步联动')
        await ev("(function(){var t=document.querySelectorAll('#tbBoards .tab-btn')[1];"
                 "if(t)t.click();})()")
        await asyncio.sleep(2.2)
        r = await ev(STATE_JS)
        ok(r.get('rowCount') > 0, '新板块的事项已渲染（%s 条）' % r.get('rowCount'))
        ok(r.get('curBoard') != '', 'curBoard 指向新板块：%s' % r.get('curBoard'))
        # 统计带应与当前板块对应（不是全局汇总）
        stat_total = 0
        m = (r.get('stat') or '').replace('总事项', '').strip().split(' ')[0]
        if m.isdigit():
            stat_total = int(m)
        ok(0 < stat_total <= r.get('rowCount'),
           '统计带总数 %s 不超过该板块事项数 %s（= 按板块取数，非全局）'
           % (stat_total, r.get('rowCount')))

        # ---------- 用例 6：切回 0 板块部门 → 再次无残留 ----------
        print('\n【用例6】再切到无板块部门：再次确认无残留')
        await ev(click_dept('总账部'))
        await asyncio.sleep(2.2)
        r = await ev(STATE_JS)
        ok(r.get('rowCount') == 0, '事项已清空（%s 条）' % r.get('rowCount'))
        ok(r.get('curBoard') == '', 'curBoard 已清空')
        ok('该板块暂无数据' in (r.get('content') or ''),
           '显示「该板块暂无数据」：%s' % (r.get('content') or '')[:30])

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  FAIL: ' + f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'",
                        'get', 'CommandLine', '/FORMAT:CSV'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
