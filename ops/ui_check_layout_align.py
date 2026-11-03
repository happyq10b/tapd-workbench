"""布局对齐守卫（2026-11-03）
固化四项需求 + 两轮追加：
  ① 主页按钮靠右（部门块右缘）
  ② 统计**卡片**底边 == 左侧**白底卡片**（.tb-navgroup）底边
     —— 不是「可选看板带」底、也不是「带 + 间隔」底
  ③ 公告标题字体 == 架构部门标题字体
  ④ 搜索栏加宽、导入导出右侧无多余空白
  ⑤ 窄屏一致性（需求5：1200→500 锁定区间几何不变）

只读工具，不修改任何文件。
"""
import asyncio, json, os, shutil, subprocess, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9529
prof = os.path.join(os.environ.get('TEMP', '.'), 'cdp_la2%d' % PORT)
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
  var out={};
  var gaps=[];
  Array.prototype.slice.call(document.querySelectorAll('.tb-dept-band .tree-dept'),0,6).forEach(function(d){
    var hb=d.querySelector('.dept-home');
    if(hb)gaps.push(Math.round(d.getBoundingClientRect().right-hb.getBoundingClientRect().right));
  });
  out.homeGaps=gaps;
  var nav=document.querySelector('.tb-navgroup');
  var band=document.querySelector('.tb-board-band');
  var grid=document.getElementById('tbBoards');
  var statBand=document.querySelector('.tb-stat-band');
  var topbar=document.getElementById('topbar');
  var cards=document.querySelectorAll('.tb-stat-band .stat-card');
  var cardBottoms=[],cardTops=[];
  Array.prototype.forEach.call(cards,function(c){
    var b=c.getBoundingClientRect();
    cardBottoms.push(Math.round(b.bottom)); cardTops.push(Math.round(b.top));});
  out.cardBottoms=cardBottoms; out.cardTops=cardTops; out.cardCount=cards.length;
  out.nav=bx('.tb-navgroup'); out.band=bx('.tb-board-band'); out.grid=bx('#tbBoards');
  out.statBand=bx('.tb-stat-band'); out.topbar=bx('#topbar'); out.notice=bx('.notice-bar');
  var ov=document.querySelector('.tb-stat-band .progress-overview');
  var ovcs=ov?getComputedStyle(ov):null;
  out.ovMargin=ovcs?ovcs.margin:null;
  out.bandPad=statBand?getComputedStyle(statBand).padding:null;
  out.navPadBottom=nav?getComputedStyle(nav).paddingBottom:null;
  out.navBorderBottom=nav?getComputedStyle(nav).borderBottomWidth:null;
  var bandTitle=document.querySelector('.tb-dept-band .tb-band-title');
  var noticeT=document.querySelector('.notice-head .t');
  function fs(el){var c=getComputedStyle(el);
    return c.fontSize+'/'+c.fontWeight+'/'+c.color+'/'+c.letterSpacing;}
  out.bandFont=bandTitle?fs(bandTitle):null;
  out.noticeFont=noticeT?fs(noticeT):null;
  var tb=document.querySelector('.toolbar');
  var tbcs=getComputedStyle(tb);
  var ie=document.getElementById('headerImportExport');
  var si=document.getElementById('searchInput');
  out.search=si?Math.round(si.getBoundingClientRect().width):null;
  out.searchTrunc=si?si.scrollWidth>si.clientWidth+1:null;
  out.blankAfterIE=(ie&&tb)?Math.round(tb.getBoundingClientRect().right-parseFloat(tbcs.paddingRight)-ie.getBoundingClientRect().right):null;
  out.toolbar=bx('.toolbar');
  var nb=(nav?nav.getBoundingClientRect().bottom:0);
  var tb0=(topbar?topbar.getBoundingClientRect().bottom:0);
  var cb=cardBottoms.length?cardBottoms[cardBottoms.length-1]:null;
  out.navBottom=Math.round(nb); out.topbarBottom=Math.round(tb0); out.cardBottom=cb;
  out.cardVsNav=(cb!==null)?cb-Math.round(nb):null;
  out.cardVsTopbar=(cb!==null)?cb-Math.round(tb0):null;
  out.statBandVsNav=Math.round(statBand.getBoundingClientRect().bottom-nb);
  out.cardVsBand=(cb!==null)?cb-Math.round(band.getBoundingClientRect().bottom):null;
  out.navPadGap=(cb!==null)?Math.round(nb-cb):null;
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
        await ev("(function(){var t=document.querySelector('#tbBoards .tab-btn');if(t)t.click();})();")
        await asyncio.sleep(3)

        print('【用例1】主页按钮靠右')
        d = json.loads(await ev(PROBE))
        gaps = d['homeGaps']
        ok(len(gaps) > 0, '取到 %d 个部门块' % len(gaps))
        ok(all(0 <= g <= 24 for g in gaps),
           '主页按钮距部门块右缘 %s px（应 ≤24，即紧贴右缘）' % gaps)

        print('\n【用例2】统计**卡片**底边 == 左侧**白底卡片**底边（用户明确要求的基准）')
        ok(d['cardCount'] == 3, '取到 %d 张统计卡片' % d['cardCount'])
        ok(d['cardVsNav'] == 0,
           '★ 卡片底(%s) − 白卡底(%s) = %s px（应为 0）' % (d['cardBottom'], d['navBottom'], d['cardVsNav']))
        ok(len(set(d['cardBottoms'])) == 1, '三张卡片底边彼此齐平：%s' % d['cardBottoms'])
        ok(d['cardVsTopbar'] == 0, '卡片底 − topbar 底 = %s px（应为 0）' % d['cardVsTopbar'])
        ok(d['statBandVsNav'] == 0, '统计带底 − 白卡底 = %s px（应为 0）' % d['statBandVsNav'])
        exp_gap = int(float((d['navPadBottom'] or '0px').replace('px', ''))) + \
            int(float((d['navBorderBottom'] or '0px').replace('px', '')))
        ok(d['navPadGap'] == 0,
           '白卡底 − 卡片底 = %s px（应为 0：卡片底与白卡底齐平）' % d['navPadGap'])
        ok(d['ovMargin'] == '0px', 'overview margin=%s（须为 0）' % d['ovMargin'])
        ok(d['bandPad'] == '0px', '统计带 padding=%s（须为 0）' % d['bandPad'])
        ok(d['cardVsBand'] == exp_gap,
           '卡片底 − 可选看板带底 = %s px（= 白卡下留白 %s，说明对齐的是白卡而非带）'
           % (d['cardVsBand'], exp_gap))

        print('\n【用例3】公告标题字体 == 架构部门标题字体')
        ok(d['bandFont'] == d['noticeFont'],
           '架构部门=%s / 公告=%s' % (d['bandFont'], d['noticeFont']))
        ok(d['bandFont'] is not None and d['bandFont'].startswith('13px/700/'),
           '字号字重为 13px/700：%s' % d['bandFont'])

        print('\n【用例4】搜索栏加宽 + 导入导出右侧无空白')
        ok(d['search'] >= 167, '搜索框宽 %s px（≥167 基线，已加宽）' % d['search'])
        ok(d['searchTrunc'] is False, '搜索框文字未被截断')
        ok(d['blankAfterIE'] <= 2, '导入导出右侧空白 %s px（应 ≤2）' % d['blankAfterIE'])

        print('\n【用例5】窄屏一致性（需求5：1200→500 锁定区间几何不变）')
        bad = 0
        base = None
        for w in (1200, 1100, 1000, 900, 800, 700, 600, 500):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.7)
            r = json.loads(await ev(PROBE))
            if base is None:
                base = r
                print('  视口 %-5d 基准' % w)
                continue
            diff = []
            for k in ('nav', 'band', 'grid', 'statBand', 'notice'):
                for f in ('x', 'y', 'w', 'h'):
                    if r[k][f] != base[k][f]:
                        diff.append(k + '.' + f)
            for key in ('cardVsNav', 'cardVsTopbar', 'navPadGap', 'cardVsBand'):
                if r[key] != base[key]:
                    diff.append('%s %s→%s' % (key, base[key], r[key]))
            if r['cardBottoms'] != base['cardBottoms']:
                diff.append('cardBottoms')
            if diff:
                bad += 1
                print('  视口 %-5d 差异: %s' % (w, ','.join(diff)))
            else:
                print('  视口 %-5d 一致 ✓' % w)
        ok(bad == 0, '锁定区间 1200→500 共 8 个视口，几何与对齐关系全部一致')

        print('\n【用例6】宽屏（>1440 容器 max-width 生效，宽度本就会展开）→ 只校验对齐不破')
        wide_bad = []
        for w in (1600, 1440):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.7)
            r = json.loads(await ev(PROBE))
            if r['cardVsNav'] != 0:
                wide_bad.append('视口%d 卡片底−白卡底=%s' % (w, r['cardVsNav']))
            if r['blankAfterIE'] > 2:
                wide_bad.append('视口%d 导入导出后空白=%s' % (w, r['blankAfterIE']))
            print('  宽屏 %-5d 卡片底−白卡底=%s 导入导出后空白=%s 搜索框=%s'
                  % (w, r['cardVsNav'], r['blankAfterIE'], r['search']))
        ok(not wide_bad, '宽屏 1600/1440：卡片与白卡底对齐、导入导出后无空白仍成立')


asyncio.run(m())

out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
                     capture_output=True, text=True).stdout
for l in out.splitlines():
    if 'cdp_la2%d' % PORT in l:
        pid = l.strip().split(',')[-1].strip()
        if pid.isdigit():
            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)

passed = sum(1 for okv, _ in RESULTS if okv)
print('\n结果：通过 %d / 失败 %d' % (passed, len(RESULTS) - passed))
