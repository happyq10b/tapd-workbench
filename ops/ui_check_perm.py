# -*- coding: utf-8 -*-
"""真实浏览器（Chrome headless + CDP）验证：普通用户登录后看到的看板/板块是否与后端一致。

用法：python ops/ui_check_perm.py <账号> <密码>
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = int(os.environ.get('CDP_PORT', '9333'))
BASE = os.environ.get('TAPD_BASE', 'http://127.0.0.1:8100')


def start_chrome():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
                return True
        except Exception:
            time.sleep(0.5)
    return False


def target_ws():
    with urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5) as r:
        targets = json.loads(r.read())
    for t in targets:
        if t.get('type') == 'page' and t.get('webSocketDebuggerUrl'):
            return t['webSocketDebuggerUrl']
    raise RuntimeError('no page target')


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.id = 0

    async def send(self, method, params=None):
        self.id += 1
        mid = self.id
        await self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError(str(msg['error']))
                return msg.get('result', {})

    async def eval(self, expr, await_promise=False):
        r = await self.send('Runtime.evaluate', {
            'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise})
        res = r.get('result', {})
        if r.get('exceptionDetails'):
            return {'__error__': str(r['exceptionDetails'])[:300]}
        return res.get('value')


async def main():
    user = sys.argv[1] if len(sys.argv) > 1 else '__ui_user'
    pwd = sys.argv[2] if len(sys.argv) > 2 else 'UiTest123'
    if not start_chrome():
        print('chrome 启动失败')
        return 2
    ws_url = target_ws()
    async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
        c = CDP(ws)
        await c.send('Page.enable')
        await c.send('Runtime.enable')
        await c.send('Page.navigate', {'url': BASE + '/login'})
        await asyncio_sleep(2)
        await c.eval("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(user), json.dumps(pwd)))
        await asyncio_sleep(3)
        out = await c.eval("""(function(){
            var r={url:location.href, token:!!localStorage.getItem('tk')};
            try{ r.me_boards=(ME&&ME.boards||[]).map(function(b){return b.board_id;}); }catch(e){ r.me_boards='ERR '+e; }
            var t=document.getElementById('boardTabs');
            r.tabs=t?[].slice.call(t.querySelectorAll('.tab-btn')).map(function(e){return e.textContent.trim();}):[];
            r.depts=t?[].slice.call(t.querySelectorAll('.tree-dept')).map(function(e){return e.textContent.trim();}):[];
            var tip=t?t.querySelector('.tree-empty-tip'):null;
            r.empty_tip=tip?tip.textContent.trim():'';
            r.all_tips=t?[].slice.call(t.querySelectorAll('.tree-empty-tip')).map(function(e){return e.textContent.trim();}):[];
            r.role=(document.getElementById('roleTag')||{}).textContent||'';
            r.user=(document.getElementById('userName')||{}).textContent||'';
            return JSON.stringify(r);
        })()""")
        print(json.dumps(json.loads(out) if isinstance(out, str) else out, ensure_ascii=False, indent=2))
    return 0


async def asyncio_sleep(sec):
    import asyncio
    await asyncio.sleep(sec)


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
