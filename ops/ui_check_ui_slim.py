#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【界面精简与看板管理弹窗】守卫脚本（UI设计师 · 2026-11-03）

用户提 5 项（附截图标注）：
  ① 看板管理弹窗「挤成一团」，右边宽松 → 左列加宽，卡片不再挤
  ② 看板管理列表里的身份徽标「超级管理员」没意义 → 移除
  ③ 筛选框只保留「人员」「周数」字样，placeholder「点击从架构树选择」「41 或 2026-41」去掉
  ④ 「统计概览」标题去掉（占位置）
  ⑤ 部门「主页」按钮前的 🏠 emoji 去掉

本脚本固化这 5 条，防止后续改动把它们加回来。

为什么单独建（而不是塞进现有脚本）：
  ops/test-filter-ui.js、ops/ui_check_filter.py、ops/ui_check_perm_render.py
  里有 3 条断言编码的是**旧需求**（「统计概览」标题保留 / placeholder 提示 /
  列表身份徽标），需求变更后必然失效 —— 那三个脚本归属主设计师（§0.3.1），
  本脚本不越权改它们（已登记 T-009），而是提供与新需求对齐的独立守卫。

用法：
    python ops/ui_check_ui_slim.py
    python ops/ui_check_ui_slim.py --json
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
PORT = 9483
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
  function bx(e){if(!e)return null;
    var el=(typeof e==='string')?document.querySelector(e):e; if(!el)return null;
    var b=el.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
            right:Math.round(b.right),bottom:Math.round(b.bottom)};}
  function chk(el){if(!el)return null;var b=el.getBoundingClientRect();
    return {w:Math.round(b.width),h:Math.round(b.height),
            scrollW:el.scrollWidth,clientW:el.clientWidth,
            trunc:el.scrollWidth>el.clientWidth+1};}
  var pi=document.getElementById('personFilterInput'), wi=document.getElementById('weekFilterInput');
  var homes=document.querySelectorAll('.dept-home');
  var out={};
  // ③ 筛选框 placeholder
  out.pPlaceholder=pi?pi.placeholder:'(缺)';
  out.wPlaceholder=wi?wi.placeholder:'(缺)';
  out.pLabel=(document.querySelector('#personFilterWrap .cf-label')||{}).textContent||'';
  out.wLabel=(document.querySelector('#weekFilterWrap .cf-label')||{}).textContent||'';
  out.pTitle=pi?pi.title:''; out.pAria=pi?(pi.getAttribute('aria-label')||''):'';
  out.wTitle=wi?wi.title:''; out.wAria=wi?(wi.getAttribute('aria-label')||''):'';
  // ④ 统计概览标题
  out.statTitleExists=!!document.querySelector('.tb-stat-band .tb-band-title');
  out.statCards=document.querySelectorAll('#progressOverview .stat-card').length;
  out.statBand=bx(document.querySelector('.tb-stat-band'));
  // ⑤ 主页 emoji
  out.homeCount=homes.length;
  out.homeTexts=[];
  Array.prototype.forEach.call(homes,function(h){out.homeTexts.push((h.textContent||'').trim());});
  out.homeHasEmoji=out.homeTexts.some(function(t){return /\u{1F3E0}|\u{1F3E1}/u.test(t);});
  out.homeTextIsPlain=out.homeTexts.every(function(t){return t==='主页';});
  // ④⑤ 顶部几何
  out.topbar=bx('#topbar'); out.statBandH=out.statBand?out.statBand.h:0;
  return JSON.stringify(out);
})()
"""

BC_PROBE = r"""
(function(){
  function bx(e){if(!e)return null;var b=e.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};}
  function chk(el){if(!el)return null;var b=el.getBoundingClientRect();
    return {w:Math.round(b.width),h:Math.round(b.height),
            scrollW:el.scrollWidth,clientW:el.clientWidth,
            trunc:el.scrollWidth>el.clientWidth+1};}
  var item=document.querySelector('.bc-item');
  var nm=item?item.querySelector('.nm'):null;
  var meta=item?item.querySelector('.meta'):null;
  var nameEl=nm?nm.querySelector('span:not(.bc-pick-wrap)'):null;
  var out={};
  out.leftW=bx(document.querySelector('.bc-left'));
  out.item=bx(item);
  out.nm=chk(nm); out.meta=chk(meta); out.name=chk(nameEl);
  out.nameText=nameEl?(nameEl.textContent||'').trim():'';
  out.roleTagCount=document.querySelectorAll('.bc-role-tag').length;
  out.badgeH=nm?Math.round(nm.querySelector('.badge-active,.badge-locked,.badge-muted').getBoundingClientRect().height):0;
  out.metaH=meta?Math.round(meta.getBoundingClientRect().height):0;
  out.copyBtn=chk(item?item.querySelector('.cp-copy-btn'):null);
  return JSON.stringify(out);
})()
"""


async def run():
    prof = os.path.join(tempfile.gettempdir(), 'cdp_slim_%d' % PORT)
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
        # 打开看板管理弹窗
        await ev("openBoardConfigModal();")
        await asyncio.sleep(3)
        raw = await ev(BC_PROBE)
        out['_bc'] = json.loads(raw) if isinstance(raw, str) else raw
    shutil.rmtree(prof, ignore_errors=True)
    return out


def main():
    print('【界面精简与看板管理弹窗】守卫脚本（UI设计师 · 2026-11-03）')
    d = asyncio.run(run())
    if not isinstance(d, dict) or d.get('__error__'):
        print('  （诊断）%s' % d)
        return 1
    bc = d.get('_bc') or {}

    print('\n【用例1】筛选框只保留「人员」「周数」字样（placeholder 已清空）')
    ok(not (d.get('pPlaceholder') or '').strip(), '人员框 placeholder 为空：%r' % d.get('pPlaceholder'))
    ok(not (d.get('wPlaceholder') or '').strip(), '周数框 placeholder 为空：%r' % d.get('wPlaceholder'))
    ok('人员' in (d.get('pLabel') or ''), '人员标签保留：%r' % d.get('pLabel'))
    ok('周数' in (d.get('wLabel') or ''), '周数标签保留：%r' % d.get('wLabel'))
    ok(bool(d.get('pTitle')) and bool(d.get('pAria')),
       '人员提示移至 title/aria-label：%r / %r' % (d.get('pTitle'), d.get('pAria')))
    ok(bool(d.get('wAria')), '周数提示保留在 aria-label：%r' % d.get('wAria'))

    print('\n【用例2】「统计概览」标题已去掉（统计卡保留）')
    ok(d.get('statTitleExists') is False, '统计带内无 .tb-band-title')
    ok(d.get('statCards') == 3, '3 张统计卡仍在：%s' % d.get('statCards'))

    print('\n【用例3】部门「主页」按钮无房子 emoji')
    ok(d.get('homeHasEmoji') is False, '无 🏠 emoji：%s' % (d.get('homeTexts') or [])[:3])
    ok(d.get('homeTextIsPlain') is True, '文案就是「主页」：%s' % (d.get('homeTexts') or [])[:3])

    print('\n【用例4】看板管理弹窗不再挤成一团')
    ok((bc.get('leftW') or {}).get('w', 0) >= 380,
       '左列已加宽（≥380px）：%s' % (bc.get('leftW') or {}).get('w'))
    ok((bc.get('name') or {}).get('h', 99) <= 24,
       '看板名称单行不换行（h≤24）：%s' % (bc.get('name') or {}).get('h'))
    ok(bc.get('badgeH', 99) <= 24, '状态徽标不被压竖排（h≤24）：%s' % bc.get('badgeH'))
    ok(bc.get('metaH', 99) <= 26, 'meta 行不换行（h≤26）：%s' % bc.get('metaH'))
    ok((bc.get('nm') or {}).get('trunc') is False, '标题行无横向溢出')
    ok((bc.get('meta') or {}).get('trunc') is False, 'meta 行无横向溢出')

    print('\n【用例5】看板列表不再显示身份徽标')
    ok(bc.get('roleTagCount') == 0, '列表内无 .bc-role-tag 节点：%s' % bc.get('roleTagCount'))

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
        if 'cdp_slim_%d' % PORT in l:
            pid = l.strip().split(',')[-1].strip()
            if pid.isdigit():
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
    sys.exit(main())
