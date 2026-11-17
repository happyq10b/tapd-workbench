# -*- coding: utf-8 -*-
"""T-204z CDP 真机验证（只读）：导入按钮仅超级管理员可见

① __cdp_ui（role=admin **普通管理员**）登录 → toolbarOps 菜单不含「导入（xlsx）」
② admin token 注入（超级管理员）→ 菜单含「导入（xlsx）」
③ 两种身份下「导出勾选（xlsx）」均可见（导出不受影响）
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
from app.app import make_token  # noqa: E402

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9555
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


async def main():
    import websockets
    tk_admin = make_token('admin')

    async def login_and_check(token, who):
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204z')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                          f'--remote-debugging-port={PORT}', '--user-data-dir=' + profile,
                          'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        try:
            t = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=5).read())
            ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
            w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
            pending = {}

            async def reader():
                while True:
                    m = json.loads(await w.recv())
                    if m.get('id') is not None and m['id'] in pending:
                        f = pending.pop(m['id'])
                        if f and not f.done():
                            f.set_result(m)

            seq = [0]

            async def send(method, params=None):
                seq[0] += 1
                fut = asyncio.get_event_loop().create_future()
                pending[seq[0]] = fut
                await w.send(json.dumps({'id': seq[0], 'method': method, 'params': params or {}}))
                return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

            async def ev(expr, aw=False):
                r = await send('Runtime.evaluate',
                               {'expression': expr, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}),
                                                    ensure_ascii=False)}
                return r.get('result', {}).get('value')

            asyncio.get_event_loop().create_task(reader())
            await send('Page.enable')
            await send('Runtime.enable')
            await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
            await asyncio.sleep(1)
            await ev("document.cookie=%s;location.href='/';" %
                     json.dumps('tk=%s; path=/; Max-Age=86400' % token))
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True:
                    break
            for _ in range(30):
                await asyncio.sleep(1)
                if await ev("Array.isArray((window.ROW_OPS||{}).toolbarOps)") is True:
                    break
            labels = await ev("(ROW_OPS.toolbarOps||[]).map(function(x){return x.label}).join('|')")
            me = await ev("({u:ME.username,super:!!ME.is_super,role:ME.role})")
            return who, me, labels
        finally:
            kill_profile_chrome('cdp_t204z')
            shutil.rmtree(profile, ignore_errors=True)

    # ① 普通管理员（__cdp_ui, role=admin）
    who, me, labels = await login_and_check(ensure_test_ui_account(), '普通管理员')
    ok(me and me.get('super') is False and me.get('role') == 'admin',
       f'① {who} 身份确认：role=admin 且非超管（{me}）')
    ok('导入（xlsx）' not in (labels or ''), f'① {who} 菜单不含「导入（xlsx）」')
    ok('导出勾选（xlsx）' in (labels or ''), f'① {who} 导出按钮不受影响')

    # ② 超级管理员（admin token）
    who, me, labels = await login_and_check(tk_admin, '超级管理员')
    ok(me and me.get('super') is True, f'② {who} 身份确认（{me}）')
    ok('导入（xlsx）' in (labels or ''), f'② {who} 菜单含「导入（xlsx）」')

    force_offline_and_remove('__cdp_ui')


asyncio.run(main())
fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
