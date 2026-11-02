#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""顶栏入口的权限可见性测试（真实 Chrome + CDP）

用户要求：**用户没有权限的功能入口，就不用显示了**。

验证矩阵（对应后端接口的 require_admin / require_editor）：
  管理员 admin  → 成员/架构/看板管理/日志 全部显示；新建板块显示；更多菜单 5 项全显示
  可编辑 editor → 管理员专属 4 项隐藏；新建板块显示；更多菜单 5 项全显示
  只读 viewer  → 管理员专属 4 项隐藏；新建板块隐藏；更多菜单里「恢复」「导入」隐藏，
                 「备份」「模板」「导出」保留（这三项是 require_auth，只读可用）

运行：ops/.localvenv/Scripts/python.exe ops/ui_check_perm_entries.py
"""
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9462
PREFIX = '__pe_'
U_ADMIN, U_EDITOR, U_VIEWER = PREFIX + 'admin', PREFIX + 'editor', PREFIX + 'viewer'

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  ✗ ' + msg)


def setup():
    c = sqlite3.connect(DB)
    now = "2026-11-02 12:00:00"
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    for acct, role in ((U_ADMIN, 'admin'), (U_EDITOR, 'editor'), (U_VIEWER, 'viewer')):
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,?,?,?,?)""",
                  (acct, hash_pw('At159357'), role, '*', '*', now))
    c.commit()
    c.close()


def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.commit()
    c.close()


async def main():
    setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT,
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen(
        'http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]

    import websockets
    async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate',
                           {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})

        PROBE = """(function(){
            function vis(id){var e=document.getElementById(id);if(!e)return 'MISSING';
                return (e.style.display==='none'||getComputedStyle(e).display==='none')?'H':'V';}
            var menu=document.getElementById('headerMoreMenu');
            var items={};
            if(menu)[].slice.call(menu.querySelectorAll('button')).forEach(function(b){
                var t=b.textContent.trim().replace(/^[^\\u4e00-\\u9fa5]*/,'');
                items[t]=(b.style.display==='none'||getComputedStyle(b).display==='none')?'H':'V';});
            return {role:(document.getElementById('roleTag')||{}).textContent,
                    team:vis('teamBtn'),wg:vis('wgBtn'),boardCfg:vis('boardConfigBtn'),
                    audit:vis('auditBtn'),newCol:vis('newBtn'),items:items};
        })()"""

        try:
            results = {}
            for user in (U_ADMIN, U_EDITOR, U_VIEWER):
                await send('Page.navigate', {'url': BASE + '/login'})
                await asyncio.sleep(2)
                await ev("document.getElementById('u').value=%s;"
                         "document.getElementById('p').value='At159357';"
                         "document.getElementById('btn').click();" % json.dumps(user))
                await asyncio.sleep(5)
                await ev("(function(){var b=document.querySelector('#headerMore .header-btn');"
                         "if(b)b.click();})()")
                await asyncio.sleep(0.8)
                results[user] = await ev(PROBE)

            print('\n【用例1】管理员：全部入口可见')
            r = results[U_ADMIN]
            ok(r.get('team') == 'V', '成员与账号管理：%s' % r.get('team'))
            ok(r.get('wg') == 'V', '架构管理：%s' % r.get('wg'))
            ok(r.get('boardCfg') == 'V', '看板管理：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'V', '操作日志：%s' % r.get('audit'))
            ok(r.get('newCol') == 'V', '新建板块：%s' % r.get('newCol'))
            ok(all(v == 'V' for v in (r.get('items') or {}).values()),
               '更多菜单 5 项全显示：%s' % (r.get('items') or {}))

            print('\n【用例2】可编辑：管理员专属入口隐藏，其余可见')
            r = results[U_EDITOR]
            ok(r.get('team') == 'H', '成员与账号管理隐藏：%s' % r.get('team'))
            ok(r.get('wg') == 'H', '架构管理隐藏：%s' % r.get('wg'))
            ok(r.get('boardCfg') == 'H', '看板管理隐藏：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'H', '操作日志隐藏：%s' % r.get('audit'))
            ok(r.get('newCol') == 'V', '新建板块可见：%s' % r.get('newCol'))
            ok(all(v == 'V' for v in (r.get('items') or {}).values()),
               '更多菜单 5 项全显示（备份/恢复/模板/导入/导出）：%s' % (r.get('items') or {}))

            print('\n【用例3】只读：写操作入口隐藏，只读可用的保留')
            r = results[U_VIEWER]
            ok(r.get('team') == 'H', '成员与账号管理隐藏：%s' % r.get('team'))
            ok(r.get('wg') == 'H', '架构管理隐藏：%s' % r.get('wg'))
            ok(r.get('boardCfg') == 'H', '看板管理隐藏：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'H', '操作日志隐藏：%s' % r.get('audit'))
            ok(r.get('newCol') == 'H', '新建板块隐藏：%s' % r.get('newCol'))
            it = r.get('items') or {}
            ok(it.get('恢复') == 'H', '「恢复」(JSON 导入, require_editor) 隐藏：%s' % it.get('恢复'))
            ok(it.get('导入') == 'H', '「导入」(xlsx, require_editor) 隐藏：%s' % it.get('导入'))
            ok(it.get('备份') == 'V', '「备份」(导出 JSON, require_auth) 保留：%s' % it.get('备份'))
            ok(it.get('模板') == 'V', '「模板」(require_auth) 保留：%s' % it.get('模板'))
            ok(it.get('导出') == 'V', '「导出」(require_auth) 保留：%s' % it.get('导出'))
        finally:
            cleanup()

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (passed, failed))
    for f in FAIL_LIST:
        print('  FAIL: ' + f)
    return 1 if failed else 0


FAIL_LIST = []

if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'",
                        'get', 'CommandLine', '/FORMAT:CSV'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
