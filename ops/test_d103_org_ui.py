# -*- coding: utf-8 -*-
"""#103 UI 实测：架构排序按钮 + 操作记录限高（CDP）"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


async def main():
    from app.app import make_token
    tok = make_token('admin')
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    orig = [r[0] for r in con.execute(
        "SELECT id FROM org_nodes WHERE parent_id=1 ORDER BY sort, id")]
    # 找一张有操作记录的卡
    cid = con.execute("SELECT card_id FROM actions WHERE action='update' "
                      "GROUP BY card_id HAVING COUNT(*)>=5 LIMIT 1").fetchone()[0]
    con.close()

    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d103')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                      '--disable-gpu', '--no-first-run', '--remote-debugging-port=9455',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9455/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9455/json', timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__err__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)

        print('【A】操作记录框限高')
        con2 = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        pboard = con2.execute("SELECT board_id FROM cards WHERE card_id=?", (cid,)).fetchone()[0]
        con2.close()
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(3)
        await ev("openDetail('" + cid + "'); 'x'", aw=True)
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
          const el=document.getElementById('d_actions');
          if(!el) return {none:true};
          const cs=getComputedStyle(el);
          return {mh:cs.maxHeight, oy:cs.overflowY, ch:el.clientHeight, sh:el.scrollHeight,
                  items:el.querySelectorAll('.comment-item').length};
        })()""")
        print('  探针:', r)
        ok(r.get('mh') == '140px', 'max-height=140px（约 4 行）')
        ok(r.get('oy') == 'auto', '独立滚动条（overflow-y:auto）')
        ok(r.get('ch', 0) <= 140 and r.get('sh', 0) > r.get('ch', 0),
           '内容超出 4 行 → 框不再拉长，可滚动（client %s / scroll %s）' % (r.get('ch'), r.get('sh')))
        await ev("closeModal('detailModal');")

        print('【B】架构管理 ↑↓ 排序')
        await ev("openWgModal(); 'x'", aw=True)
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
          const rows=[...document.querySelectorAll('#wgList .org-node-row')];
          const btns=[...document.querySelectorAll('#wgList .org-node-row button[title*=上移],#wgList .org-node-row button[title*=下移]')];
          const names=rows.map(x=>(x.querySelector('.wgt-label')||x.querySelector('span[style*=font-weight]')||{}).textContent);
          return {rows:rows.length, btns:btns.length, names:names.slice(0,7)};
        })()""")
        print('  探针:', r)
        ok(r.get('rows', 0) > 3, '架构树渲染（%s 行）' % r.get('rows'))
        ok(r.get('btns', 0) >= r.get('rows', 1) * 2, '↑↓ 按钮齐全（%s 个）' % r.get('btns'))
        # 点击第一行部门（财务中心下的第一个子节点 = 管理部）的下移
        r = await ev("""(function(){
          const first=ORG_TREE[0].children[0];
          const before=ORG_TREE[0].children.map(x=>x.name).join(',');
          return {first:first.name, before:before};
        })()""")
        first_name, before = r['first'], r['before']
        await ev("orgMoveNode(ORG_TREE[0].children[0].id,'down'); 'x'", aw=True)
        for _ in range(20):
            await asyncio.sleep(0.5)
            r2 = await ev("ORG_TREE[0].children.map(x=>x.name).join(',')")
            if r2 != before:
                break
        expect = before.split(',')
        expect[0], expect[1] = expect[1], expect[0]
        ok(r2 == expect.join(',') if isinstance(r2, str) and False else r2 == ','.join(expect),
           '点击 ↓ → 与相邻兄弟交换（%s → %s）' % (before, r2))
        # 服务器端持久化
        req = urllib.request.Request(BASE + '/api/org/tree', headers={'Authorization': 'Bearer ' + tok})
        srv = [c['name'] for c in json.loads(urllib.request.urlopen(req, timeout=10).read())['tree'][0]['children']]
        ok(srv == expect, '服务器端顺序一致（%s）' % srv)
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d103_org_sort.png', 'wb').write(base64.b64decode(shot['data']))
    shutil.rmtree(profile, ignore_errors=True)

    # 还原 org 顺序
    for nid in reversed(orig):
        pass  # 归一化后 sort=0..n-1，直接按 orig 顺序逐个上移到顶代价高 → 直接 SQL 还原
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    for idx, nid in enumerate(orig):
        con.execute('UPDATE org_nodes SET sort=? WHERE id=?', (idx, nid))
    con.commit()
    con.close()
    print('  （org 顺序已还原）')

    npass = sum(1 for c, _ in RES if c)
    print('结果： %d/%d' % (npass, len(RES)))
    sys.exit(0 if npass == len(RES) else 1)


asyncio.run(main())
