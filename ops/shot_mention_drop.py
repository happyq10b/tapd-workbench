#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图留档：事项详情弹窗评论 @ 候选下拉完整展示修复（#75）。

管理员登录 → 打开真实事项详情 → 评论框输入「测试@」触发候选 →
探针（展开方向/可见性/宽度）+ 截图。不参与断言。
"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9395
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
U = 'admin'
PWD = 'At159357'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.shots', 'mention_drop.png')


def pick_card():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    row = c.execute("SELECT card_id FROM cards WHERE deleted=0 ORDER BY rowid DESC LIMIT 1").fetchone()
    c.close()
    return row['card_id'] if row else None


async def main():
    card = pick_card()
    print('样本事项:', card)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_s2%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1
                mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1080, 'height': 720, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            await ev("openDetail(%s);" % json.dumps(card), aw=True)
            await asyncio.sleep(1.5)
            # 模拟用户输入「测试@」触发候选
            r = await ev("var i=document.getElementById('d_new_comment');"
                         "i.value='测试@';i.focus();onCommentInput(i);'ok'")
            print('触发:', r)
            await asyncio.sleep(1)
            # 探针：方向 / 是否完整在弹窗可视区内 / 宽度
            st = await ev("""(function(){
              var d=document.getElementById('d_mention_drop');
              var b=document.querySelector('#detailModal .modal-body');
              if(!d||d.hidden)return {shown:false};
              var dr=d.getBoundingClientRect(),br=b.getBoundingClientRect();
              return {shown:true,dir:(d.style.bottom&&d.style.bottom!=='auto')?'up':'down',
                      opts:d.querySelectorAll('.mention-opt').length,
                      inView:dr.top>=br.top&&dr.bottom<=br.bottom,
                      w:Math.round(dr.width),h:Math.round(dr.height)};
            })()""")
            print('探针:', json.dumps(st, ensure_ascii=False))
            shot = await send('Page.captureScreenshot', {'format': 'png'})
            data = shot.get('data')
            if data:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, 'wb') as f:
                    f.write(base64.b64decode(data))
                print('截图已保存：%s' % OUT)
            else:
                print('截图失败')
    finally:
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
