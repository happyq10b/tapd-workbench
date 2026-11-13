# -*- coding: utf-8 -*-
"""T-204b 诊断探针：板块预览「操作记录」在真实板块上的行为
  ① 打开真实板块预览 → cd_actions 内容
  ② 走「✏️ 编辑 → 保存 → 回到预览」（backToColumnDetail）→ 操作记录是否刷新
  ③ 控制台 JS 错误
只读 + 一次真实保存（不改任何字段值 = 重写原值，可接受）。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
PORT = 9543
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204b')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        res = await asyncio.wait_for(fut, timeout=30)
        return res.get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Emulation.setDeviceMetricsOverride',
               {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
    await send('Log.enable')
    errors = []
    await send('Runtime.consoleAPICalled')  # no-op keepalive

    cookie = 'tk=%s; path=/; Max-Age=86400' % tk
    await send('Page.navigate', {'url': BASE + '/'})
    await asyncio.sleep(1)
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    for _ in range(90):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            break
    print('admin 登录就绪', flush=True)
    await asyncio.sleep(2.5)

    # 捕获 JS 异常
    await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

    # ⓪ 切到第一个真实看板
    r0 = await ev("""(function(){
      const bs=(ME.boards||[]);
      if(!bs.length)return {found:false};
      curBoard=bs[0].board_id;curBoards=new Set([bs[0].board_id]);
      reload(1);
      return {found:true, board:bs[0].board_name};
    })()""")
    print('⓪ ', json.dumps(r0, ensure_ascii=False), flush=True)
    await asyncio.sleep(3)

    # ① 打开第一个真实板块预览
    r1 = await ev("""(function(){
      const t=document.querySelector('#boardContent .week-title.edit[data-colkey]');
      if(!t)return {found:false, html:document.getElementById('boardContent').textContent.slice(0,80)};
      openColumnDetail(t);
      return {found:true, colkey:t.dataset.colkey, cname:t.textContent};
    })()""")
    print('① ', json.dumps(r1, ensure_ascii=False), flush=True)
    await asyncio.sleep(1.5)
    r2 = await ev("""(function(){
      const box=document.getElementById('cd_actions');
      return {exists:!!box, text:(box?box.textContent:'').slice(0,120)};
    })()""")
    print('① cd_actions:', json.dumps(r2, ensure_ascii=False), flush=True)

    # ② 编辑 → 保存 → 回预览
    await ev("openColumnDetailEdit()")
    await asyncio.sleep(1.5)
    r3 = await ev("""(function(){
      const m=document.getElementById('columnModal');
      return {editOpen:m.style.display==='flex', key:COLUMN_EDIT_KEY};
    })()""")
    print('② 编辑弹窗:', json.dumps(r3, ensure_ascii=False), flush=True)
    await ev("saveColumn()")   # 重写原值
    await asyncio.sleep(2.5)
    r4 = await ev("""(function(){
      const m=document.getElementById('columnDetailModal');
      const box=document.getElementById('cd_actions');
      return {backToDetail:m.style.display==='flex', actions:(box?box.textContent:'').slice(0,160)};
    })()""")
    print('② 回预览后 cd_actions:', json.dumps(r4, ensure_ascii=False), flush=True)

    # ③ 服务端核对：该板块 column_actions 是否有刚写入的 update
    r5 = await ev("(function(){const k=COLUMN_DETAIL.colkey;return api('/api/columns/actions?col_key='+encodeURIComponent(k)).then(function(d){return JSON.stringify((d.actions||[]).slice(0,3))})})()", True)
    print('③ 服务端 actions:', json.dumps(r5, ensure_ascii=False), flush=True)
    r6 = await ev("window.__errs")
    print('③ JS 错误:', json.dumps(r6, ensure_ascii=False), flush=True)
    await ev("closeModal('columnDetailModal')")
    return 0


if __name__ == '__main__':
    try:
        rc = asyncio.run(main()) or 0
    finally:
        # T-204c 教训：残留 headless Chrome 会以登录账号身份持续心跳 → 在线列表永远「未下线」
        import re as _re
        try:
            _out = subprocess.run(
                ['wmic', 'process', 'where',
                 "name='chrome.exe' and CommandLine like '%cdp_t204b%'",
                 'get', 'ProcessId', '/FORMAT:VALUE'],
                capture_output=True, text=True, timeout=20).stdout
            for _pid in _re.findall(r'ProcessId=(\d+)', _out):
                subprocess.run(['taskkill', '/PID', _pid, '/F'], capture_output=True)
        except Exception:
            pass
    sys.exit(rc)
