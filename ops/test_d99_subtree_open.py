# -*- coding: utf-8 -*-
"""#99 实测：reload 后子树自动恢复展开 + 一次点击子事项即弹窗"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    from app.app import make_token
    tok = make_token('admin')
    import sqlite3
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'); con.row_factory = sqlite3.Row
    sub = con.execute("SELECT card_id,parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid = sub['parent_id'], sub['card_id']
    con.close()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d99')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9434', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9434/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9434/json', timeout=5).read())
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
                desc = r['exceptionDetails'].get('exception', {}).get('description', '') or r['exceptionDetails'].get('text', '')
                return {'__err__': desc[:200]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2)
        con2 = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        pboard = con2.execute("SELECT board_id FROM cards WHERE card_id=?", (pid,)).fetchone()[0]
        con2.close()
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(3)

        print('【A】展开子树 → 触发 reload → 子树自动恢复展开')
        await ev("toggleSubTree('" + pid + "', true); 'x'", aw=True)
        await asyncio.sleep(1.5)
        # 触发一次 reload（模拟任意保存/操作后的刷新）：编辑保存最真实——直接改个无关字段
        await ev("openEdit('" + sid + "'); 'x'", aw=True)
        await asyncio.sleep(1.2)
        await ev("saveEdit(); 'x'", aw=True)
        await asyncio.sleep(2.5)   # reload 完成
        # reload 后子树应自动恢复展开（DOM 里有渲染行）
        restored = await ev("document.querySelectorAll('#subtree_" + pid + " .sub-node').length")
        open_state = await ev("(document.getElementById('subtree_" + pid + "')||{style:{}}).style.display")
        ok(restored > 0, 'reload 后子树自动恢复展开（%s 行，display=%s）' % (restored, open_state))
        ok(open_state == 'block', '子树可见（display=block）')

        print('【B】一次点击子事项 → 详情弹窗立即出现')
        await ev("(function(){const t=document.querySelector('#subtree_" + pid + " .s-title');if(t)t.click();})()")
        await asyncio.sleep(1.5)
        st = await ev("document.getElementById('detailModal').style.display")
        title = await ev("document.getElementById('d_title')?document.getElementById('d_title').textContent:''")
        ok(st == 'flex' and bool(title), '一次点击即弹出详情（%s）' % (title or '')[:20])
        await ev("closeModal('detailModal');")

        print('【C】再次 reload（切走再切回看板）后展开状态保持')
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(2.5)
        restored2 = 0
        for _ in range(20):   # 轮询等待重绘+子树 fetch 完成（最多 10s）
            restored2 = await ev("document.querySelectorAll('#subtree_" + pid + " .sub-node').length")
            if restored2 > 0:
                break
            await asyncio.sleep(0.5)
        ok(restored2 > 0, '切回看板后子树仍恢复展开（%s 行）' % restored2)

        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d99_subtree_open.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图:', out)
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
