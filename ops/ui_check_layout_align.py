"""四项布局需求验证（2026-11-03）
1. 主页按钮靠右（部门块右缘）
2. 统计卡底边 == 可选看板带底边
3. 公告标题字体 == 架构部门标题字体
4. 搜索栏加宽、导入导出右侧无多余空白
只读工具，不修改任何文件。
"""
import asyncio, json, os, shutil, subprocess, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9511
prof = os.path.join(os.environ.get('TEMP', '.'), 'cdp_la%d' % PORT)
shutil.rmtree(prof, ignore_errors=True)
subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--remote-debugging-port=%d' % PORT,
                  '--user-data-dir=' + prof, 'about:blank'],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(60):
    try:
        urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2).read()
        break
    except Exception:
        time.sleep(0.5)
import websockets
tg = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
url = [t['webSocketDebuggerUrl'] for t in tg if t.get('type') == 'page'][0]

PROBE = r"""
(function(){
  function bx(e){if(!e)return null;if(typeof e==='string')e=document.querySelector(e);
    if(!e)return null;var b=e.getBoundingClientRect();
    return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
            right:Math.round(b.right),bottom:Math.round(b.bottom)};}
  function fs(el){var c=getComputedStyle(el);
    return c.fontSize+'/'+c.fontWeight+'/'+c.color+'/'+c.letterSpacing;}
  var out={};
  // 1) 主页按钮右对齐
  var gaps=[];
  Array.prototype.slice.call(document.querySelectorAll('.tb-dept-band .tree-dept'),0,6).forEach(function(d){
    var hb=d.querySelector('.dept-home');
    if(hb)gaps.push(Math.round(d.getBoundingClientRect().right-hb.getBoundingClientRect().right));
  });
  out.homeGaps=gaps;
  // 2) 高度对齐
  var stat=document.querySelector('.tb-stat-band');
  var boardBand=document.querySelector('.tb-board-band');
  var boardGrid=document.getElementById('tbBoards');
  out.stat=bx('.tb-stat-band'); out.boardBand=bx('.tb-board-band'); out.boardGrid=bx('#tbBoards');
  out.statVsBand=(stat&&boardBand)?Math.round(stat.getBoundingClientRect().bottom-boardBand.getBoundingClientRect().bottom):null;
  out.statVsGrid=(stat&&boardGrid)?Math.round(stat.getBoundingClientRect().bottom-boardGrid.getBoundingClientRect().bottom):null;
  out.statW=(stat&&boardBand)?Math.round(stat.getBoundingClientRect().width-document.querySelector('.notice-bar').getBoundingClientRect().width):null;
  out.notice=bx('.notice-bar');
  // 3) 字体对比
  var bandTitle=document.querySelector('.tb-dept-band .tb-band-title');
  var noticeT=document.querySelector('.notice-head .t');
  out.bandFont=bandTitle?fs(bandTitle):null;
  out.noticeFont=noticeT?fs(noticeT):null;
  out.bandText=bandTitle?(bandTitle.textContent||'').trim():null;
  out.noticeText=noticeT?(noticeT.textContent||'').trim():null;
  // 4) 工具栏
  var tb=document.querySelector('.toolbar');
  var tbcs=getComputedStyle(tb);
  var ie=document.getElementById('headerImportExport');
  var si=document.getElementById('searchInput');
  out.toolbar=bx('.toolbar'); out.tl=bx('.toolbar-left'); out.tr=bx('.toolbar-right');
  out.search=si?Math.round(si.getBoundingClientRect().width):null;
  out.searchTrunc=si?si.scrollWidth>si.clientWidth+1:null;
  out.blankAfterIE=(ie&&tb)?Math.round(tb.getBoundingClientRect().right-parseFloat(tbcs.paddingRight)-ie.getBoundingClientRect().right):null;
  out.ieRight=ie?Math.round(ie.getBoundingClientRect().right):null;
  out.tbInnerRight=tb?Math.round(tb.getBoundingClientRect().right-parseFloat(tbcs.paddingRight)):null;
  return JSON.stringify(out);
})()
"""

RESULTS = []


def ok(cond, msg):
    RESULTS.append((bool(cond), msg))
    print(('  OK   ' if cond else '  FAIL ') + msg)


async def m():
    async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
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

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await ev("!!document.getElementById('tbDepts')"):
                break
        await asyncio.sleep(2.5)

        print('【用例1】主页按钮靠右')
        d = json.loads(await ev(PROBE))
        gaps = d['homeGaps']
        ok(len(gaps) > 0, '取到 %d 个部门块' % len(gaps))
        ok(all(0 <= g <= 24 for g in gaps),
           '主页按钮距部门块右缘 %s px（应 ≤24，即紧贴右缘）' % gaps)

        print('\n【用例2】统计卡底边 == 可选看板带底边')
        ok(d['statVsBand'] == 0, '统计带底 - 可选看板带底 = %s px（应为 0）' % d['statVsBand'])
        ok(d['statVsGrid'] == 0, '统计带底 - 可选看板网格底 = %s px（应为 0）' % d['statVsGrid'])
        # 宽度基准：统计带与公告栏同属右半一列 → 宽度必须相等（不超出公告栏）
        ok(d['statW'] == 0, '统计带宽 - 公告栏宽 = %s px（应为 0，不超出公告栏）' % d['statW'])

        print('\n【用例3】公告标题字体 == 架构部门标题字体')
        ok(d['bandFont'] == d['noticeFont'],
           '架构部门=%s / 公告=%s' % (d['bandFont'], d['noticeFont']))
        ok(d['bandFont'] is not None and d['bandFont'].startswith('13px/700/'),
           '字号字重为 13px/700：%s' % d['bandFont'])

        print('\n【用例4】搜索栏加宽 + 导入导出右侧无空白')
        ok(d['search'] >= 167, '搜索框宽 %s px（≥167 基线，已加宽）' % d['search'])
        ok(d['searchTrunc'] is False, '搜索框文字未被截断')
        ok(d['blankAfterIE'] <= 2, '导入导出右侧空白 %s px（应 ≤2）' % d['blankAfterIE'])

        # 5a 锁定区间 1200→500：几何必须完全一致（需求5 的既定范围）
        bad = 0
        base = None
        for w in (1200, 1100, 1000, 900, 800, 700, 600, 500):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.7)
            r = json.loads(await ev(PROBE))
            if base is None:
                base = r          # 1200 为基准
                print('  视口 %-5d 基准' % w)
                continue
            diff = []
            for k in ('stat', 'boardBand', 'boardGrid', 'notice'):
                for f in ('x', 'y', 'w', 'h'):
                    if r[k][f] != base[k][f]:
                        diff.append(k + '.' + f)
            if r['statVsBand'] != 0:
                diff.append('statVsBand=%s' % r['statVsBand'])
            if diff:
                bad += 1
                print('  视口 %-5d 差异: %s' % (w, ','.join(diff)))
            else:
                print('  视口 %-5d 一致 ✓' % w)
        ok(bad == 0, '锁定区间 1200→500 共 8 个视口，几何与对齐关系全部一致')

        # 5b 宽屏（>1440 时 .wrap 的 max-width 生效，容器本就会展开 → 宽度变化是设计使然）
        #     这里只校验「对齐关系不破」+「导入导出右侧仍无空白」
        wide_bad = []
        for w in (1600, 1440):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.7)
            r = json.loads(await ev(PROBE))
            if r['statVsBand'] != 0:
                wide_bad.append('视口%d statVsBand=%s' % (w, r['statVsBand']))
            if r['blankAfterIE'] > 2:
                wide_bad.append('视口%d 导入导出后空白=%s' % (w, r['blankAfterIE']))
            print('  宽屏 %-5d 底边对齐差=%s 导入导出后空白=%s 搜索框=%s'
                  % (w, r['statVsBand'], r['blankAfterIE'], r['search']))
        ok(not wide_bad, '宽屏 1600/1440：底边对齐与导入导出后无空白仍成立')


asyncio.run(m())

out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
                     capture_output=True, text=True).stdout
for l in out.splitlines():
    if 'cdp_la%d' % PORT in l:
        pid = l.strip().split(',')[-1].strip()
        if pid.isdigit():
            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)

passed = sum(1 for okv, _ in RESULTS if okv)
print('\n结果：通过 %d / 失败 %d' % (passed, len(RESULTS) - passed))
