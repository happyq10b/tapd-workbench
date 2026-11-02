#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""顶部栏（架构部门 / 可选板块）+ 筛选栏布局测量工具（Chrome headless + CDP）。

用途：UI 改动前后跑一遍，输出关键几何数据做对比。只测量，不修改任何文件。

用法：
    python ops/ui_measure_topbar.py            # 默认 1600x1000 视口
    python ops/ui_measure_topbar.py 1280 800   # 指定视口宽高
    python ops/ui_measure_topbar.py 1600 1000 --json   # 输出 JSON（便于 diff）

登录凭据可用环境变量覆盖：UI_MEASURE_USER / UI_MEASURE_PWD
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9347
BASE = 'http://127.0.0.1:8100'
USER = os.environ.get('UI_MEASURE_USER', 'admin')
PWD = os.environ.get('UI_MEASURE_PWD', 'At159357')

VIEW_W = int(sys.argv[1]) if len(sys.argv) > 1 else 1600
VIEW_H = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
AS_JSON = '--json' in sys.argv

# 测量脚本（在页面上下文中执行）
PROBE = r"""
(function(){
  function box(el){ if(!el) return null; var b=el.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
            right:Math.round(b.right),bottom:Math.round(b.bottom)}; }
  function items(sel){ return Array.from(document.querySelectorAll(sel)).map(function(e){
      var b=box(e);
      return {t:e.textContent.replace(/\s+/g,' ').trim().slice(0,16), x:b.x,y:b.y,w:b.w,h:b.h,
              cx:Math.round(b.x+b.w/2), cy:Math.round(b.y+b.h/2)}; }); }

  var r={};
  var de=document.documentElement;
  r.viewport={w:innerWidth,h:innerHeight};
  r.doc={scrollW:de.scrollWidth,clientW:de.clientWidth,scrollH:de.scrollHeight,clientH:de.clientHeight};
  r.overflowX = de.scrollWidth > de.clientWidth+1;

  // ---- 顶部栏三带 ----
  r.topbar=box(document.getElementById('topbar'));
  r.topbarMain=box(document.getElementById('boardTabs'));
  r.aside=box(document.getElementById('topbarAside'));

  r.deptBand=box(document.querySelector('.tb-dept-band'));
  r.deptTitle=box(document.querySelector('.tb-dept-band .tb-band-title'));
  r.deptGrid=box(document.getElementById('tbDepts'));
  r.deptItems=items('#tbDepts > *');
  r.deptCols=getComputedStyle(document.getElementById('tbDepts')).gridTemplateColumns;

  r.boardBand=box(document.querySelector('.tb-board-band'));
  r.boardGrid=box(document.getElementById('tbBoards'));
  r.boardItems=items('#tbBoards > *');
  r.boardCols=getComputedStyle(document.getElementById('tbBoards')).gridTemplateColumns;

  r.statBand=box(document.querySelector('.tb-stat-band'));

  // 部门网格：是否按行优先（同一行 y 相同）
  // ⚠️ 每行内必须按 **x 升序**排列，才是真正的「视觉左→右」顺序。
  //    若按 DOM 顺序收集，CSS order 重排过的行会显示成错乱的序列。
  function rowProfile(arr){
    var rows={};
    arr.forEach(function(it){ (rows[it.y]=rows[it.y]||[]).push(it); });
    return Object.keys(rows).sort(function(a,b){return a-b;}).map(function(k){
      return rows[k].sort(function(a,b){return a.x-b.x;}).map(function(it){return it.t;});
    });
  }
  r.deptRows=rowProfile(r.deptItems);
  r.boardRows=rowProfile(r.boardItems);

  // ---- 筛选栏 ----
  r.toolbar=box(document.querySelector('.toolbar'));
  r.toolbarLeft=box(document.querySelector('.toolbar-left'));
  r.toolbarRight=box(document.querySelector('.toolbar-right'));
  r.tbKids=items('.toolbar-left > *');
  r.personWrap=box(document.getElementById('personFilterWrap'));
  r.personField=box(document.querySelector('#personFilterWrap .cf-field'));
  r.personChips=box(document.getElementById('personFilterChips'));
  r.personChipCount=document.querySelectorAll('#personFilterChips > *').length;
  r.weekField=box(document.querySelector('#weekFilterWrap .cf-field'));
  r.dateFilter=box(document.getElementById('dateFilterBox'));
  r.filterHint=box(document.getElementById('filterHint'));

  // 筛选栏子元素是否重叠 / 溢出
  var kids=r.tbKids, ov=[], out=[];
  for(var i=0;i<kids.length-1;i++){
    var a=kids[i],b=kids[i+1];
    if(a.right>b.x+1) ov.push({a:a.t,b:b.t,px:a.right-b.x});
  }
  if(r.toolbar) r.tbOverlaps=ov;
  r.tbOverflow=r.tbKids.filter(function(c){ return r.toolbar && c.right > r.toolbar.right-1; })
                     .map(function(c){ return {t:c.t, over:c.right-r.toolbar.right}; });

  // 整页是否有横向溢出
  var wide=[];
  document.querySelectorAll('body *').forEach(function(el){
    var b=el.getBoundingClientRect();
    if(b.width>0 && b.right > de.clientWidth+2 && el.offsetParent!==null){
      var st=getComputedStyle(el);
      if(st.position==='fixed') return;
      wide.push({tag:el.tagName, cls:(el.className||'').toString().slice(0,40), right:Math.round(b.right)});
    }
  });
  r.offScreen=wide.slice(0,12);
  r.offScreenCount=wide.length;

  return JSON.stringify(r);
})()
"""


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_m%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)

    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]

    try:
        async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1; mid = i
                await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:400]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': VIEW_W, 'height': VIEW_H, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(USER), json.dumps(PWD)))
            for _ in range(30):
                await asyncio.sleep(0.5)
                if await ev("!!document.getElementById('tbDepts')"):
                    break
            await asyncio.sleep(1.5)

            raw = await ev(PROBE)
            if isinstance(raw, dict):
                print('测量失败：' + str(raw.get('__error__')))
                return 1
            data = json.loads(raw)

            if AS_JSON:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print('=' * 62)
                print('视口 %dx%d   文档 scrollW=%s clientW=%s  横向溢出=%s'
                      % (VIEW_W, VIEW_H, data['doc']['scrollW'], data['doc']['clientW'],
                         '是 ⚠' if data['overflowX'] else '否'))
                print('=' * 62)
                print('\n【顶部栏】')
                tb = data['topbar'] or {}
                print('  topbar      %s' % tb)
                print('  左半 main   %s' % data['topbarMain'])
                print('  右半 aside  %s' % data['aside'])
                print('\n【架构部门】cols=%s' % data['deptCols'])
                print('  带          %s' % data['deptBand'])
                print('  网格        %s' % data['deptGrid'])
                for i, row in enumerate(data['deptRows']):
                    print('  第%d行: %s' % (i + 1, ' | '.join(row)))
                print('\n【可选板块】cols=%s  条目数=%d' % (data['boardCols'], len(data['boardItems'])))
                print('  带          %s' % data['boardBand'])
                print('  网格        %s' % data['boardGrid'])
                for i, row in enumerate(data['boardRows']):
                    print('  第%d行: %s' % (i + 1, ' | '.join(row)))
                print('\n【统计概览】%s' % data['statBand'])
                print('\n【筛选栏】')
                print('  toolbar     %s' % data['toolbar'])
                print('  left        %s' % data['toolbarLeft'])
                print('  right       %s' % data['toolbarRight'])
                for k in data['tbKids']:
                    print('    - %-22s x=%-5s w=%-5s h=%-4s' % (k['t'], k['x'], k['w'], k['h']))
                print('  人员框 %s' % data['personField'])
                print('  人员chips %s 个' % data['personChipCount'])
                print('  重叠: %s' % (data['tbOverlaps'] or '无 ✓'))
                print('  溢出工具栏: %s' % (data['tbOverflow'] or '无 ✓'))
                print('\n【横向溢出】共 %d 个元素超出视口右缘' % data['offScreenCount'])
                for o in data['offScreen'][:8]:
                    print('    - %s.%s right=%s' % (o['tag'], o['cls'], o['right']))
            return 0
    finally:
        subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                        '/FORMAT:CSV'], capture_output=True, text=True)
        out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                              '/FORMAT:CSV'], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if 'cdp_profile_m%d' % PORT in line:
                pid = line.strip().split(',')[-1].strip()
                if pid.isdigit():
                    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
