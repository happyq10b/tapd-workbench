# -*- coding: utf-8 -*-
"""#121 实测：全局搜索（未选看板可用）+ 搜索按钮 + 看板卡片标题单行省略 + 移除备份/恢复
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.parse
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9421
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


def api_get(path, token):
    safe = path.split('?')[0]
    query = urllib.parse.quote(path.split('?', 1)[1], safe='=&,') if '?' in path else ''
    path = safe + ('?' + query if query else '')
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + token})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


async def main():
    from app.app import make_token
    tok = make_token('admin')
    d = api_get('/api/cards?size=500', tok)
    cards = [c for c in d['cards'] if not (c.get('parent_id') or '')]
    kw = cards[0]['card_name'].strip()[:6] if cards else '测试'
    # 全局口径预期值（不带 board_ids）
    g = api_get('/api/cards?size=1&q=' + kw, tok)
    expect_total = g['total']

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d122')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=50 * 1024 * 1024) as w:
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

        async def search_and_read(word):
            await ev("document.getElementById('searchInput').value=%s;reload(1);'fired'" % json.dumps(word, ensure_ascii=False))
            await asyncio.sleep(2)
            return await ev("""(function(){
              const c=document.getElementById('boardContent');
              const head=c.querySelector('.sr-head');
              return {isSearch:!!c.querySelector('.sr-wrap'),
                      head:head?head.textContent:'',
                      empty:!!c.querySelector(':scope>.empty')};
            })()""")

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
        # 强制回到「未选看板」状态
        await ev("clearBoardSelection('已取消选择');renderTabs();renderProgress();")
        await asyncio.sleep(1)

        print('【① 未选看板时的全局搜索】')
        ph = await ev("document.getElementById('searchInput').placeholder")
        ok('看板' not in ph and '事项 / 板块' in ph, '占位语已限定为「事项 / 板块」：%s' % ph)
        r1 = await search_and_read(kw)
        ok(r1.get('isSearch'), '未选看板时搜索出结果（统一搜索结果视图）')
        ok(('共 %d 条结果' % expect_total) in (r1.get('head') or ''),
           '结果数与全局权限口径一致：页面「%s」 vs API total=%d' % ((r1.get('head') or '').split('：')[-1], expect_total))

        print('【② 搜索按钮触发】')
        await ev("document.getElementById('searchInput').value='';reload(1);")
        await asyncio.sleep(1.5)
        r2 = await ev("""(function(){
          document.getElementById('searchInput').value=%s;
          const btn=document.querySelector('.toolbar-left button.btn-default');
          if(!btn)return {noBtn:true};
          btn.click();
          return {hasBtn:true};
        })()""" % json.dumps(kw, ensure_ascii=False))
        await asyncio.sleep(2)
        after = await ev("!!document.querySelector('#boardContent .sr-wrap')")
        ok(r2.get('hasBtn') and after, '搜索按钮存在且点击后触发搜索（结果视图出现）')

        print('【③ 清空搜索词 → 恢复空状态】')
        await ev("document.getElementById('searchInput').value='';reload(1);")
        await asyncio.sleep(1.5)
        back = await ev("!!document.querySelector('#boardContent>.empty')")
        ok(back, '清空搜索词后回到「请选择看板」空状态（未误拉全局数据）')

        print('【④ 选中看板时搜索回归】')
        await ev("(function(){const g=groupBoardsByDept();const d=g.depts.find(x=>x.boards.length);if(d)pickBoard(d.boards[0].board_id);})()")
        await asyncio.sleep(2)
        r4 = await search_and_read(kw)
        ok(r4.get('isSearch'), '选中看板后搜索正常（回归）')

        print('【⑤ 看板卡片标题单行省略】')
        r5 = await ev("""(function(){
          const n=document.querySelector('#tbBoards .tab-btn .tab-name');
          if(!n)return {missing:true};
          const cs=getComputedStyle(n);
          const h0=n.offsetHeight;
          const old=n.textContent;
          n.textContent='超长标题测试'.repeat(30);
          const h1=n.offsetHeight;
          n.textContent=old;
          return {missing:false,ws:cs.whiteSpace,te:cs.textOverflow,h0:h0,h1:h1};
        })()""")
        if r5.get('missing'):
            ok(False, '未找到 .tab-name（无展开看板）：%s' % r5)
        else:
            ok(r5.get('ws') == 'nowrap' and r5.get('te') == 'ellipsis',
               '单行省略样式生效（white-space=nowrap, text-overflow=ellipsis）')
            ok(r5.get('h0') == r5.get('h1'), '超长标题不撑大卡片（高度 %s→%s 不变）' % (r5.get('h0'), r5.get('h1')))

        print('【⑥ 备份/恢复已移除】')
        r6 = await ev("""(function(){
          const more=document.getElementById('headerMoreMenu');
          return {noBackup:!document.getElementById('backupBtn')&&!document.getElementById('jsonImportBtn'),
                  keepWg:!!document.getElementById('wgBtn'),keepTeam:!!document.getElementById('teamBtn'),
                  keepAudit:!!document.getElementById('auditBtn'),
                  textNoBackup:(more.textContent||'').indexOf('备份')<0&&(more.textContent||'').indexOf('恢复')<0};
        })()""")
        ok(r6.get('noBackup') and r6.get('textNoBackup'), '【更多】菜单已无备份/恢复按钮')
        ok(r6.get('keepWg') and r6.get('keepTeam') and r6.get('keepAudit'), '其余菜单项保留（架构管理/账号管理/操作日志）')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
