# -*- coding: utf-8 -*-
"""#116 实测：操作记录仅显示最近 12 条 + 超出提示行。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
RES = []
def ok(c, n):
    RES.append((bool(c), n)); print(('  PASS ' if c else '  x FAIL ') + n)

# ---- 造数据：建测试卡 + 13 次 update（每次写一条日志）----
tok = make_token('admin')
def req(path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=10).read() or '{}'), 200
    except urllib.error.HTTPError as e:
        return e.read().decode()[:150], e.code

me, _ = req('/api/me')
bid = me['boards'][0]['board_id']
d, c = req('/api/cards', 'POST', {'board_id': bid, 'card_name': '__t116', 'column_name': '测试',
                                  'created_at': '2026-11-09'})
con_ok = 'card_id' in json.dumps(d)[:200] or c == 200
# 取 card_id（直接查库最稳）
import sqlite3
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
cid = con.execute("SELECT card_id FROM cards WHERE card_name='__t116'").fetchone()
con.close()
if cid:
    cid = cid[0]
    for i in range(13):
        req('/api/cards/' + cid, 'PUT', {'fields': {'description': 'probe %d' % i}})
    n = json.loads(urllib.request.urlopen(urllib.request.Request(
        BASE + '/api/cards/%s/actions' % cid, headers={'Authorization': 'Bearer ' + tok}), timeout=10).read())['actions']
    print('  测试卡日志条数（后端给 %d，上限 30）' % len(n))
else:
    print('  测试卡创建失败:', c, str(d)[:100])
    sys.exit(1)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d116')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9492', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = 'http://127.0.0.1:9492'
    for _ in range(60):
        try:
            urllib.request.urlopen(cdp + '/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen(cdp + '/json', timeout=5).read())
    ws_url = [t for t in targets if t.get('type') == 'page'][0]['webSocketDebuggerUrl']
    async with websockets.connect(ws_url, max_size=30*1024*1024) as w:
        i = 0
        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid: return msg.get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__err__': str(r['exceptionDetails'].get('exception', {}).get('description', ''))[:200]}
            return r.get('result', {}).get('value')
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2)
        await ev("openDetail('%s');" % cid)
        await asyncio.sleep(1.5)
        items = await ev("[...document.querySelectorAll('#d_actions .comment-item')].length")
        ok(items == 12, '操作记录仅显示 12 条（实测 %s）' % items)
        tip = await ev("(function(){const t=[...document.querySelectorAll('#d_actions div')].find(x=>x.textContent.includes('仅显示最近 12 条'));return t?t.textContent:null})()")
        ok(bool(tip), '超出时尾部显示提示行（%s…）' % (tip or ''))
        ok('操作日志' in (tip or '') and '管理员权限' in (tip or ''), '提示引导到操作日志并注明管理员权限')
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        open(r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d116_actions12.png', 'wb').write(__import__('base64').b64decode(shot['data']))
    subprocess.Popen(['taskkill', '/F', '/IM', 'chrome.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
# 清理测试卡
req('/api/cards/' + cid, 'DELETE')
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
con.execute("DELETE FROM actions WHERE card_id=?", (cid,))
con.execute("DELETE FROM cards WHERE card_id=?", (cid,))
con.commit(); con.close()
print('  测试卡与日志已清理')
print('结果： %d/%d' % (sum(1 for c, _ in RES if c), len(RES)))
sys.exit(0 if all(c for c, _ in RES) else 1)
