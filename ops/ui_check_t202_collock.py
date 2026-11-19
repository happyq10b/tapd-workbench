# -*- coding: utf-8 -*-
"""T-202 板块编辑锁标识 CDP 校验。

场景：管理员浏览器打开夹具看板 → 另一账号（fixture 用户）经 API 认领板块编辑锁
（key=column:<col_key>）→ WS edit_lock 广播 → 管理员页面板块标题后方实时出现
「🔒 <姓名> 已锁定」标识（样式复用事项行 .lock-tag）→ 释放后标识实时消失。
同时校验 /api/cards 的板块元信息下发 locked_by/locked_by_name。
"""
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9551
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

N = []
P = '__t202_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'
LOCK_KEY = 'column:' + COLKEY


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def cleanup():
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    c = sqlite3.connect(DB, timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    c.execute("DELETE FROM team_members WHERE account LIKE ? ESCAPE '{}'".format(e), (P + '%',))
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('users', 'username')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('users', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'",
                       (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def setup():
    cleanup()
    c = sqlite3.connect(DB, timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    c.execute("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
              (P + 'u_ed', hash_pw('At159357'), 'editor'))
    c.execute("INSERT OR REPLACE INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
              (P + '钱编辑', P + 'u_ed', P + '部门D9', '2026-11-13 12:00:00'))
    c.execute("INSERT OR REPLACE INTO boards(board_id,board_name,owner,created_at) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', '2026-11-13 12:00:00'))
    c.execute("INSERT OR REPLACE INTO board_columns(col_key,column_id,board_id,column_name,"
              "created_at,creator,nature,year,completion) VALUES(?,?,?,?,?,?,?,?,?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-13 12:00:00', 'admin',
               '日常', '2026', 'open'))
    c.commit()
    c.close()


def api_call(method, path, token, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


async def main():
    t_admin = make_token('admin')
    t_ed = make_token(P + 'u_ed')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t202')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile,
                      'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending, seq = {}, [0]

    async def send(m, p=None):
        seq[0] += 1
        fut = asyncio.get_event_loop().create_future()
        pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:200])
            return {'__err__': True}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t_admin))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)
    await ev("""(async function(){curBoards=new Set(['%s']);curBoard='%s';await reload(1);return 'ok'})()"""
             % (BID, BID), True)
    await asyncio.sleep(1.5)

    print('【① 初始：无锁定标识】', flush=True)
    r1 = await ev("""(function(){
      return {n:document.querySelectorAll('.col-lock-tag').length,
        meta:!!(window.COLS_META||[]).find(x=>x.col_key==='%s'&&!x.locked_by)};})()""" % COLKEY.replace('"', '\\"'))
    ok(isinstance(r1, dict) and r1.get('n') == 0, '未锁定时板块标题后方无 🔒 标识')

    print('【② API：板块元信息未下发锁定者（未锁定）】', flush=True)
    s, d = api_call('GET', '/api/cards?board_ids=' + BID + '&size=1', t_admin)
    col = next((x for x in d.get('columns', []) if x['col_key'] == COLKEY), {})
    ok(s == 200 and col.get('locked_by') in ('', None), '未锁定：columns meta locked_by 为空')

    print('【③ fixture 用户认领板块编辑锁 → 标识实时出现】', flush=True)
    s, d = api_call('POST', '/api/locks/acquire', t_ed, {'key': LOCK_KEY})
    ok(s == 200, '认锁接口 200')
    await asyncio.sleep(2.0)
    r3 = await ev("""(function(){
      const tag=document.querySelector('.col-lock-tag');
      if(!tag)return {n:0};
      const title=document.querySelector('.week-title[data-colkey]');
      return {n:document.querySelectorAll('.col-lock-tag').length,
        txt:tag.textContent.trim(),cls:tag.className,
        afterTitle:title?title.nextElementSibling===tag:null};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('n') == 1, '锁定后标识实时出现（WS edit_lock → 原位更新）')
    ok(isinstance(r3, dict) and '已锁定' in str(r3.get('txt')) and '钱编辑' in str(r3.get('txt')),
       '标识文案 =「🔒 <姓名> 已锁定」（截图同款）')
    ok(isinstance(r3, dict) and 'lock-tag' in str(r3.get('cls')) and 'col-lock-tag' in str(r3.get('cls')),
       '样式复用事项行 .lock-tag')
    ok(isinstance(r3, dict) and r3.get('afterTitle') is True, '标识位于板块标题正后方')
    s, d = api_call('GET', '/api/cards?board_ids=' + BID + '&size=1', t_admin)
    col = next((x for x in d.get('columns', []) if x['col_key'] == COLKEY), {})
    ok(s == 200 and col.get('locked_by') == P + 'u_ed'
       and col.get('locked_by_name') == P + '钱编辑',
       'columns meta 下发 locked_by/locked_by_name')

    print('【④ 释放 → 标识实时消失】', flush=True)
    s, d = api_call('POST', '/api/locks/release', t_ed, {'key': LOCK_KEY})
    ok(s == 200, '释放接口 200')
    await asyncio.sleep(2.0)
    r4 = await ev("(document.querySelectorAll('.col-lock-tag').length)")
    ok(r4 == 0, '释放后标识实时消失（实际 %s）' % r4)
    s, d = api_call('GET', '/api/cards?board_ids=' + BID + '&size=1', t_admin)
    col = next((x for x in d.get('columns', []) if x['col_key'] == COLKEY), {})
    ok(col.get('locked_by') in ('', None), '释放后 columns meta locked_by 清空')

    print('== ⑤ 回归：板块编辑弹窗自身仍正常（认锁/持锁人提示逻辑未动）==', flush=True)
    r5 = await ev("""(function(){
      return {holderFn:typeof api==='function',syncFn:typeof syncColLockTag==='function'};})()""")
    ok(isinstance(r5, dict) and r5.get('holderFn') and r5.get('syncFn'), '前端函数接线完整')

    await send('Browser.close')


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    setup()
    asyncio.run(main())
finally:
    left = cleanup()
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
    for m in fails:
        print('  FAIL:', m)
    if fails or left:
        sys.exit(1)
