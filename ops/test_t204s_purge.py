# -*- coding: utf-8 -*-
"""T-204s（2026-11-17）「清空无事项板块」权限校对 —— CDP 实测：
  ① 板块参与人视角：empty=[板块A(参与人,无权), 板块B(负责人,有权)] →
     弹「部分板块无删除权限，是否仅清空权限内板块？」→ 确定 → B 删、A 保留
  ② 全部无权（A+C 均非我负责）→ toast 拦截、不弹窗、零删除
  ③ colPurgeAllowed 单测（参与人 false / 板块负责人 true / 管理员直通 true）
数据安全守则 §3.4：删除只发生在夹具空板块上；页面登录用夹具账号 __t204s_u1
（D6，不碰真实账号）；收尾 API+精确清理零残留。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9550
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []
IDS = {}
DIALOGS = []
CLEANED = [False]
TK_ADMIN = make_token('admin')


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (token or TK_ADMIN))
    body = json.dumps(data).encode() if data is not None else None
    if body:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def col_alive(ck):
    c = sqlite3.connect(DB)
    row = c.execute('SELECT 1 FROM board_columns WHERE col_key=?', (ck,)).fetchone()
    c.close()
    return bool(row)


def setup():
    c = sqlite3.connect(DB)
    for u in ('__t204s_u1', '__t204s_u2'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    st, r = api('/api/boards', 'POST', {'board_name': '__t204s 测试看板'})
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    # A：u1 仅参与人（无权清空）；B：u1 负责人（有权）；C：u1 仅参与人（无权，②用）
    for nm, owner, parts, key in (('板块A', '__t204s_u2', '__t204s_u1', 'colKeyA'),
                                  ('板块B', '__t204s_u1', '', 'colKeyB'),
                                  ('板块C', '__t204s_u2', '__t204s_u1', 'colKeyC')):
        st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': '__t204s' + nm,
                    'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                    'owner': owner, 'participants': parts})
        assert st == 200, f'{nm} 创建失败 {st} {r}'
        IDS[key] = r.get('col_key') or (IDS['bid'] + '::__t204s' + nm)


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    for ck in ('colKeyA', 'colKeyB', 'colKeyC'):
        if IDS.get(ck):
            api('/api/columns/' + urllib.parse.quote(IDS[ck], safe=''), 'DELETE')
    BS = chr(92)
    pat = '%_' + BS + '_t204s%'
    c = sqlite3.connect(DB)
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('messages', 'content')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE ?", (pat, BS))
    c.commit()
    res = {}
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'), ('users', 'username')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：', res, flush=True)


def base_counts():
    c = sqlite3.connect(DB)
    out = {}
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'), ('users', 'username')):
        if t == 'users':
            out[t] = c.execute("SELECT COUNT(*) FROM users WHERE username NOT LIKE ? ESCAPE ?"
                               " AND username != '__cdp_ui'",
                               ('%' + chr(92) + '_t204s%', chr(92))).fetchone()[0]
        else:
            out[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ? ESCAPE ?",
                               ('%' + chr(92) + '_t204s%', chr(92))).fetchone()[0]
    c.close()
    return out


async def main():
    import websockets
    setup()
    base0 = base_counts()
    tk_u1 = make_token('__t204s_u1')
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204s')
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
    try:
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
                elif msg.get('method') == 'Page.javascriptDialogOpening':
                    DIALOGS.append(msg['params'].get('message', ''))
                    await w.send(json.dumps({'id': 0, 'method': 'Page.handleJavaScriptDialog',
                                             'params': {'accept': True}}))

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
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
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_u1))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__t204s_u1'") is True:
                break
        await asyncio.sleep(1.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (IDS['bid'], IDS['bid']))
        await asyncio.sleep(2.5)

        # ③ 判定单测（u1：A/C 仅参与人 false；B 负责人 true）
        r3 = await ev("""(function(){
          return {A:colPurgeAllowed('%s'), B:colPurgeAllowed('%s'), C:colPurgeAllowed('%s')};
        })()""" % (IDS['colKeyA'], IDS['colKeyB'], IDS['colKeyC']))
        ok(r3.get('A') is False and r3.get('B') is True and r3.get('C') is False,
           f'③ 判定单测：参与人 false / 板块负责人 true（{r3}）')

        # ① 部分越权：empty=[A,B]（C 还没造?——C 已造，三板块都空 → empty=[A,B,C]）
        #    预检 allowed=[B] denied=[A,C] → 弹部分越权 → 确定 → B 删、A/C 保留
        DIALOGS.clear()
        await ev("purgeEmptyColumns()")
        await asyncio.sleep(2)
        ok(len(DIALOGS) >= 1 and '部分板块无删除权限' in DIALOGS[0] and '是否仅清空权限内板块' in DIALOGS[0],
           f'① 弹出确认文案精确匹配（实际：{DIALOGS[:1]}）')
        ok(len(DIALOGS) >= 2 and '确认删除 1 个无事项板块' in DIALOGS[1],
           f'① 主确认仅列权限内 1 个板块（实际：{DIALOGS[1:2]}）')
        await asyncio.sleep(1)
        ok(col_alive(IDS['colKeyB']) is False, '① 权限内板块B 已删除')
        ok(col_alive(IDS['colKeyA']) is True and col_alive(IDS['colKeyC']) is True,
           '① 无权限板块A/C 保留')
        IDS['colKeyB'] = ''   # 已删，cleanup 不再重复 DELETE

        # ② 全部无权：empty=[A,C] → toast 拦截
        DIALOGS.clear()
        await ev("purgeEmptyColumns()")
        await asyncio.sleep(1.5)
        t2 = await ev("document.getElementById('toast').textContent")
        ok('无权限清空' in (t2 or '') and '板块参与人不可清空' in (t2 or '') and not DIALOGS,
           f'② 全部无权 → toast 拦截且不弹窗（实际：{t2}；弹窗：{DIALOGS}）')

        # ⑤ 管理员直通（__cdp_ui 登录断言 colPurgeAllowed）
        await ev("document.cookie=%s;location.href='/';"
                 % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_ui))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'") is True:
                break
        await asyncio.sleep(1)
        r5 = await ev("(function(){return {A:colPurgeAllowed('%s')};})()" % IDS['colKeyA'])
        ok(r5.get('A') is True, '⑤ 管理员直通：参与人板块也判定有权')

        # ⑥ 行数守恒（非夹具行）+ 无 JS 错误
        base1 = base_counts()
        ok(base0 == base1, f'⑥ 行数守恒（非夹具行）：{base0} → {base1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑦ 无 JS 错误（实际：{errs}）')
    finally:
        kill_profile_chrome("cdp_t204s")
        force_offline_and_remove('__cdp_ui')
        force_offline_and_remove('__t204s_u1')
        shutil.rmtree(profile, ignore_errors=True)
        cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
