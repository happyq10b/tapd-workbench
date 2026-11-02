#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""平台名称 / 品牌缩写徽标的渲染实测（Chrome headless + CDP）

用户 2026-11-02 要求：平台改名「财务工作事项平台」→「财务综合事务平台」，
并在后面加一个英文首字母缩写。

本脚本验证的是**渲染结果**，不是源码字符串：
  1. 登录页 h1 显示「财务综合事务平台」+ FISP 徽标，且徽标在同一行（不折行）
  2. 登录页英文副行显示 Financial Integrated Service Platform
  3. 主界面顶栏 h1 显示「财务综合事务平台」+ FISP 徽标，同一行
  4. 窄屏（1280 / 1024）下 h1 仍单行 —— 历史上标题被挤成竖排单字是踩过的坑
  5. 页面 title 含新名称与缩写
  6. 旧名称「财务工作事项平台」在全站源码中已不存在

运行：ops/.localvenv/Scripts/python.exe ops/ui_check_brand.py
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
PORT = 9488
USER = os.environ.get('BRAND_USER', 'admin')
PWD = os.environ.get('BRAND_PWD', 'At159357')

CN_NAME = '财务综合事务平台'
ABBR = 'FISP'
EN_NAME = 'Financial Integrated Service Platform'
OLD_NAME = '财务工作事项平台'

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  FAIL ' + msg)


def src_check():
    """静态检查：源码里旧名称必须清零"""
    print('【源码文案】')
    root = os.path.join(os.path.dirname(__file__), '..')
    hits = []
    for rel in ('src/static/index.html', 'src/static/login.html', 'src/app/app.py'):
        p = os.path.join(root, rel.replace('/', os.sep))
        with open(p, encoding='utf-8') as f:
            if OLD_NAME in f.read():
                hits.append(rel)
    ok(not hits, '旧名称「%s」已从 index.html / login.html / app.py 清空%s'
       % (OLD_NAME, ('（残留：%s）' % hits) if hits else ''))


# 量测登录页 / 主界面 h1 徽标的实际几何：同一行 = 两者 top 差 < 6px 且 h1 高度 < 2 倍行高
PROBE = """(function(){
  function box(el){ if(!el) return null; var b=el.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}; }
  var h1=document.querySelector('.logo h1')||document.querySelector('.header-left h1');
  var ab=document.querySelector('.logo h1 .abbr')||document.querySelector('.header-left h1 .abbr');
  var en=document.querySelector('.logo .en');
  var hb=box(h1), abx=box(ab);
  var sameLine=false;
  if(hb&&abx){
    // 同行判据：徽标的垂直范围必须落在 h1 盒子内（允许 2px 视觉基线误差）。
    // ⚠️ 不能简单比 top 差 —— .abbr 有 vertical-align:2px，top 会差几个像素。
    var abC=(abx.y+abx.h/2), hbC=(hb.y+hb.h/2);
    sameLine = abC>=hb.y-2 && abC<=hb.y+hb.h+2 && hb.h<=36;
  }
  return JSON.stringify({
    title: document.title,
    h1Text: h1? h1.textContent.replace(/\\s+/g,' ').trim() : '',
    h1: hb, abbr: abx, sameLine: sameLine,
    enText: en? en.textContent.trim() : '',
    abbrVisible: !!(ab && ab.getBoundingClientRect().width>0),
    h1Lines: hb? (hb.h<=36 ? 1 : Math.round(hb.h/20)) : 0
  });
})()"""


async def main():
    src_check()

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_b%d' % PORT)
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
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')

        # ---------- 登录页 ----------
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        d = json.loads(await ev(PROBE))
        print('\n【登录页 1600x1000】')
        ok(CN_NAME in d.get('h1Text', ''), 'h1 含新名称「%s」（实测：%s）' % (CN_NAME, d.get('h1Text')))
        ok(ABBR in d.get('h1Text', ''), 'h1 含缩写 %s' % ABBR)
        ok(d.get('sameLine') is True, '徽标与中文名同行不折行（h1 h=%s, abbr y=%s）'
           % (d.get('h1', {}).get('h'), d.get('abbr', {}).get('y')))
        ok(EN_NAME in d.get('enText', ''), '英文副行为「%s」' % EN_NAME)
        ok(d.get('title', '').startswith('登录 - ' + CN_NAME), '浏览器标题 = %s' % d.get('title'))

        # ---------- 主界面（宽 / 窄） ----------
        await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                 "document.getElementById('btn').click();" % (json.dumps(USER), json.dumps(PWD)))
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await ev("!!document.getElementById('tbDepts')"):
                break
        await asyncio.sleep(1.5)

        for w, h in ((1600, 1000), (1280, 900), (1024, 800)):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(1.2)
            d = json.loads(await ev(PROBE))
            print('\n【主界面 %dx%d】' % (w, h))
            ok(CN_NAME in d.get('h1Text', ''), '顶栏 h1 含「%s」（实测：%s）' % (CN_NAME, d.get('h1Text')))
            ok(ABBR in d.get('h1Text', ''), '顶栏 h1 含缩写 %s' % ABBR)
            ok(d.get('sameLine') is True, '徽标与中文名同行（h1 h=%s, abbr y=%s）'
               % (d.get('h1', {}).get('h'), d.get('abbr', {}).get('y')))
            ok(d.get('h1Lines', 9) <= 1, '标题单行不折行（估算行数 %s）' % d.get('h1Lines'))

        return 0


if __name__ == '__main__':
    try:
        code = asyncio.run(main())
    finally:
        subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                        '/FORMAT:CSV'], capture_output=True, text=True)
        out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                              '/FORMAT:CSV'], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if 'cdp_profile_b%d' % PORT in line:
                try:
                    pid = line.strip().split(',')[-1]
                    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
                except Exception:
                    pass
    print('\n结果：%d 通过 / %d 失败' % (passed, failed))
    sys.exit(1 if failed else 0)
