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
PORT = 9533
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
            // ⚠️ 2026-11-04 #56：工具栏四按钮（展开/折叠/导入导出/新建板块）并入
            //    「操作 ▾」菜单，菜单项由 refreshToolbarOps 按 ME 权限**注册时过滤**
            //    → 权限断言改为检查 ROW_OPS['toolbarOps'] 的 label 集合。
            var ops=(typeof ROW_OPS!=='undefined'&&ROW_OPS['toolbarOps'])||[];
            var labels=ops.filter(function(it){return !it.disabled;}).map(function(it){return it.label;});
            var items={};
            labels.forEach(function(l){
                var t=l.replace(/^[^一-龥]*/,'');
                items[t]='V';
            });
            // ⚠️ #56 最终口径：备份/恢复在顶部【更多】（headerMoreMenu，管理员级显隐）
            var hm=document.getElementById('headerMoreMenu');
            var more={};
            if(hm)[].slice.call(hm.querySelectorAll('button')).forEach(function(b){
                var t=b.textContent.trim().replace(/^[^一-龥]*/,'');
                more[t]=(b.style.display==='none'||getComputedStyle(b).display==='none')?'H':'V';});
            return {role:(document.getElementById('roleTag')||{}).textContent,
                    team:vis('teamBtn'),wg:vis('wgBtn'),boardCfg:vis('boardConfigBtn'),
                    audit:vis('auditBtn'),
                    newCol:labels.some(function(l){return l.indexOf('新建板块')>=0;})?'V':'H',
                    labels:labels,items:items,more:more,
                    archBand:vis('archEntryBand'),boardBand:vis('boardEntryBand')};
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
                await ev("(function(){var b=document.querySelector('#headerImportExport .header-btn');"
                         "if(b)b.click();})()")
                await asyncio.sleep(0.8)
                results[user] = await ev(PROBE)

            print('\n【用例1】管理员：全部入口可见')
            r = results[U_ADMIN]
            ok(r.get('team') == 'V', '成员与账号管理：%s' % r.get('team'))
            ok(r.get('archBand') == 'V', '架构管理入口带（架构部门之后）：%s' % r.get('archBand'))
            ok(r.get('wg') == 'V', '架构管理按钮：%s' % r.get('wg'))
            ok(r.get('boardBand') == 'V', '看板管理入口带（可选看板之后）：%s' % r.get('boardBand'))
            ok(r.get('boardCfg') == 'V', '看板管理按钮：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'V', '操作日志：%s' % r.get('audit'))
            ok(r.get('newCol') == 'V', '新建板块：%s' % r.get('newCol'))
            _lbl = r.get('labels') or []
            _more = r.get('more') or {}
            ok(_more.get('备份') == 'V' and _more.get('恢复') == 'V',
               '顶部【更多】含 备份/恢复（admin）：%s' % _more)
            ok(any('模板' in l for l in _lbl) and any('导入' in l for l in _lbl)
               and any('导出 Excel' in l for l in _lbl),
               '工具栏操作菜单含 模板/导入/导出（admin）：%s' % _lbl)

            print('\n【用例2】可编辑：管理员专属入口隐藏，其余可见')
            r = results[U_EDITOR]
            ok(r.get('team') == 'H', '成员与账号管理隐藏：%s' % r.get('team'))
            # ⚠️ 2026-11-03：入口移到导航带后，无权限时**整带隐藏**（按钮从 DOM 移除）
            ok(r.get('archBand') == 'H', '架构管理入口带隐藏：%s' % r.get('archBand'))
            ok(r.get('wg') in ('H', 'MISSING'), '架构管理按钮隐藏：%s' % r.get('wg'))
            ok(r.get('boardBand') == 'H', '看板管理入口带隐藏：%s' % r.get('boardBand'))
            ok(r.get('boardCfg') in ('H', 'MISSING'), '看板管理按钮隐藏：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'H', '操作日志隐藏：%s' % r.get('audit'))
            ok(r.get('newCol') == 'V', '新建板块可见（菜单项）：%s' % r.get('newCol'))
            _lbl = r.get('labels') or []
            _more = r.get('more') or {}
            ok(_more.get('备份') == 'H' and _more.get('恢复') == 'H',
               '顶部【更多】备份/恢复对非管理员隐藏（admin 级）：%s' % _more)
            ok(any('模板' in l for l in _lbl) and any('导入' in l for l in _lbl)
               and any('导出 Excel' in l for l in _lbl),
               '工具栏操作菜单含 模板/导入/导出（editor）：%s' % _lbl)

            print('\n【用例3】只读：写操作入口隐藏，只读可用的保留')
            r = results[U_VIEWER]
            ok(r.get('team') == 'H', '成员与账号管理隐藏：%s' % r.get('team'))
            ok(r.get('archBand') == 'H', '架构管理入口带隐藏：%s' % r.get('archBand'))
            ok(r.get('wg') in ('H', 'MISSING'), '架构管理按钮隐藏：%s' % r.get('wg'))
            ok(r.get('boardBand') == 'H', '看板管理入口带隐藏：%s' % r.get('boardBand'))
            ok(r.get('boardCfg') in ('H', 'MISSING'), '看板管理按钮隐藏：%s' % r.get('boardCfg'))
            ok(r.get('audit') == 'H', '操作日志隐藏：%s' % r.get('audit'))
            ok(r.get('newCol') == 'H', '新建板块隐藏（菜单项被权限过滤）：%s' % r.get('newCol'))
            _lbl = r.get('labels') or []
            _more = r.get('more') or {}
            ok(_more.get('备份') == 'H' and _more.get('恢复') == 'H',
               '顶部【更多】备份/恢复对非管理员隐藏（admin 级）：%s' % _more)
            ok(r.get('newCol') == 'H' and not any('导入' in l and '模板' not in l for l in _lbl),
               '新建板块/导入 对 viewer 隐藏（editor 门槛）：%s / %s' % (r.get('newCol'), _lbl))
            ok(any('模板' in l for l in _lbl) and any('导出 Excel' in l for l in _lbl),
               '模板/导出 对 viewer 保留（require_auth）：%s' % _lbl)
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
