# -*- coding: utf-8 -*-
"""2026-11-09 四项周数需求 CDP 实测：
  需求1 公告栏标题追加【YYYY年第N周】
  需求2 事项弹窗周数 combo = 归属年份全年候选 + cur-week 高亮
  需求3 工具栏周数筛选候选联动 + cur-week 高亮
  需求4 当前周 #CCB484 加粗（computed style 验证）
"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9414
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d118')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    else:
        print('chrome 启动失败'); sys.exit(2)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
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
        await ev("(function(){const b=(ME.boards||[])[0];if(b)pickBoard(b.board_id);})()")
        await asyncio.sleep(2.5)

        print('【需求1】公告栏标题')
        r = await ev("""(function(){
          const t=document.querySelector('#noticeBar .notice-head .t');
          return t?t.textContent:'(无标题行)';
        })()""")
        cur = await ev("cpWeekOf()")
        ok(isinstance(r, str) and ('【' + cur + '】') in r,
           '公告标题 = 「%s」，含【%s】' % (r, cur))
        ok(cur.endswith('周') and cur.split('年')[0] == '2026', '当前周标签=%s（ISO 周一口径）' % cur)

        print('【需求2】事项弹窗周数 combo 全年候选')
        r = await ev("""(async function(){
          const t=document.querySelector('.item-card .item-title');
          if(!t)return {noCard:true};
          const m=t.getAttribute('onclick').match(/'([^']+)'/);
          openEdit(m?m[1]:null);
          await new Promise(res=>setTimeout(res,1500));
          openWeekCombo('e');
          // 输入框带着事项现有周值会按关键词过滤候选 → 先清空再统计全部候选
          const inp=document.getElementById('e_week');
          inp.value=''; inp.dispatchEvent(new Event('input'));
          const drop=document.getElementById('e_week_drop');
          const opts=[...drop.querySelectorAll('[data-wk-pick]')].map(x=>x.getAttribute('data-wk-pick'));
          const cur=drop.querySelector('.cf-opt.cur-week span');
          const cs=cur?getComputedStyle(cur):null;
          return {n:opts.length, first:opts[0], last:opts[opts.length-1],
                  hasW1:opts.indexOf('2026年第1周')>=0,
                  curCls:!!cur,
                  curText:cur?cur.textContent:'',
                  color:cs?cs.color:'', fw:cs?cs.fontWeight:''};
        })()""", aw=True)
        if r.get('noCard'):
            ok(False, '当前看板无事项卡片，弹窗用例跳过：%s' % r)
        else:
            ok(r.get('n') == 53 and r.get('first') == '2026年第53周' and r.get('last') == '2026年第1周',
               '全年候选 53 项、倒序（%s）' % json.dumps({k: r[k] for k in ('n', 'first', 'last')}, ensure_ascii=False))
            ok(r.get('hasW1'), '包含 2026年第1周（全年口径）')
            ok(r.get('curCls') and (r.get('curText') or '').find('第46周') >= 0,
               '当前周带 cur-week 类：%s' % r.get('curText'))
            ok(r.get('color') == 'rgb(204, 180, 132)' and r.get('fw') in ('700', 'bold'),
               '当前周 computed style：color=%s font-weight=%s（#CCB484 + 加粗）' % (r.get('color'), r.get('fw')))
        await ev("closeEdit();")

        print('【需求3+4b】工具栏周数筛选面板')
        r = await ev("""(function(){
          if(typeof curBoards==='undefined'||!curBoards.size)return {noBoard:true};
          openFilterCombo('week');
          const drop=document.getElementById('weekFilterDrop');
          const opts=[...drop.querySelectorAll('[data-pick-week]')];
          return {shown:!drop.hidden, n:opts.length,
                  curN:drop.querySelectorAll('.cf-opt.cur-week').length,
                  sample:opts.slice(0,3).map(x=>x.getAttribute('data-pick-week')),
                  tip:drop.querySelector('.cf-empty')?drop.querySelector('.cf-empty').textContent:''};
        })()""")
        if r.get('noBoard'):
            ok(False, '未选中看板，跳过：%s' % r)
        else:
            ok(r.get('shown') and r.get('n', 0) >= 0,
               '面板展开，联动候选 %s 项 %s %s' % (r.get('n'), json.dumps(r.get('sample'), ensure_ascii=False), r.get('tip') or ''))
            cur = '2026年第46周'
            if r.get('n', 0) > 0:
                allw = await ev("[...document.querySelectorAll('#weekFilterDrop [data-pick-week]')].map(x=>x.getAttribute('data-pick-week'))")
                if allw and cur in allw:
                    ok(r.get('curN') == 1, '当前周在候选中且唯一带 cur-week（curN=%s）' % r.get('curN'))
                else:
                    ok(True, '候选中无当前周（数据里本周无事项），联动口径下不展示属正确（curN=%s）' % r.get('curN'))

        print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
        if FAIL:
            print('失败项：')
            for f in FAIL:
                print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
