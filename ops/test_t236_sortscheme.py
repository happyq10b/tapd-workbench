# -*- coding: utf-8 -*-
"""T-236 排序方案储存验证（CDP + API）：
① 存为方案（prompt 真实路径）→ localStorage + user_prefs.sort_schemes 落库
② chip 应用 → 弹窗配置还原 → 确定 → sort_cfg 固化生效
③ 重开弹窗方案持久 + 激活标记
④ 删除方案 → 清单与 server 同步
⑤ 用户隔离（他人无该方案）+ 换设备恢复（清 localStorage → 登录拉回）
收尾恢复 admin user_prefs 快照 + 夹具零残留。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
BOARD = 'BCP1793717004248'
TK = make_token('admin')
U2 = '__t236_u2'

OK = []
def ok(cond, label):
    OK.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + label)

def api(path, method='GET', body=None, tk=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (tk or TK))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def pref_row(user, key):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT value FROM user_prefs WHERE username=? AND key=?', (user, key)).fetchone()
    conn.close()
    return json.loads(r['value']) if r else None

def main():
    # 快照：admin 的 sort 相关 prefs + 夹具清理
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    SNAP = [dict(r) for r in conn.execute(
        "SELECT * FROM user_prefs WHERE username='admin' AND key IN ('sort_cfg','sort_schemes')")]
    conn.execute("DELETE FROM users WHERE username LIKE '%t236%'")
    conn.commit(); conn.close()

    async def run():
        import websockets
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t236')
        shutil.rmtree(profile, ignore_errors=True)
        proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                                 '--disable-gpu', '--no-first-run', '--window-size=1440,900',
                                 '--remote-debugging-port=9695', '--user-data-dir=' + profile, 'about:blank'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        w = None
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen('http://127.0.0.1:9695/json/version', timeout=2); break
                except Exception: time.sleep(0.5)
            targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9695/json', timeout=5).read())
            ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
            w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
            pending = {}; seq = [0]; dialogs = []
            async def reader():
                while True:
                    m = json.loads(await w.recv())
                    if m.get('id') is not None and m['id'] in pending:
                        f = pending.pop(m['id'])
                        if f and not f.done(): f.set_result(m)
                    elif m.get('method') == 'Page.javascriptDialogOpening':
                        dialogs.append(m['params'].get('message') or '')
                        # fire-and-forget：reader 内 await 会阻塞自身响应消费（死锁）
                        asyncio.get_event_loop().create_task(
                            send('Page.handleJavaScriptDialog', {'accept': True, 'promptText': '回归A'}))
            async def send(mm, p=None):
                seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
                await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
                return (await asyncio.wait_for(f, timeout=30)).get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:300]}
                return r.get('result', {}).get('value')
            asyncio.get_event_loop().create_task(reader())
            await send('Page.enable'); await send('Runtime.enable')
            await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
            await asyncio.sleep(1)
            await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TK))
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True: break
            await asyncio.sleep(2.5)
            await ev("pickBoard('%s')" % BOARD)
            await asyncio.sleep(2.5)

            # ── ① 真实路径存方案：打开弹窗 → ＋存为方案（prompt「回归A」）──
            await ev("openSortSetModal()")
            await asyncio.sleep(0.5)
            await ev("ssSchemeSave()")
            await asyncio.sleep(1.0)   # prompt 对话框处理 + 防抖
            ok(any('方案名称' in d for d in dialogs), '① 存为方案弹出命名对话框（prompt）')
            ls1 = await ev("localStorage.getItem('tapd.sortSchemes_'+ME.username)")
            names1 = [s.get('name') for s in (json.loads(ls1) if ls1 else [])]
            ok('回归A' in names1, '① 方案「回归A」落 localStorage（%s）' % names1)
            # 防抖 800ms 落库
            await asyncio.sleep(1.2)
            srv = pref_row('admin', 'sort_schemes')
            ok(srv and '回归A' in [s.get('name') for s in srv],
               '① 方案落 user_prefs.sort_schemes（服务端按账号隔离）')

            # ── ② 修改配置（加状态维度）→ chip 应用 → 配置还原 → 确定固化 ──
            await ev("sortSetDir('card','status','asc')")   # 未参与 → 自动加入 + 升序
            st_mod = await ev("SORT_CFG.card.order.indexOf('status')>=0")
            ok(st_mod is True, '② 修改配置：状态维度加入排序')
            await ev("ssSchemeApply(0)")                     # 点 chip 应用方案
            st_back = await ev("SORT_CFG.card.order.indexOf('status')<0")
            ok(st_back is True, '② chip 应用「回归A」→ 配置还原（状态维度退出）')
            await ev("sortSetApply()")                       # 确定固化
            await asyncio.sleep(2.5)
            cfg_srv = pref_row('admin', 'sort_cfg')
            ok(cfg_srv and 'status' not in (cfg_srv.get('card') or {}).get('order', []),
               '② 确定后 sort_cfg 固化为方案配置（服务端）')

            # ── ③ 重开弹窗：方案持久 + 激活标记 ──
            await ev("openSortSetModal()")
            await asyncio.sleep(0.4)
            r3 = await ev("({n:SYN_SCHEMES?undefined:SORT_SCHEMES.length,"
                          " names:SORT_SCHEMES.map(function(s){return s.name;}),"
                          " active:[].slice.call(document.querySelectorAll('#ss_scheme_bar .ss-chip')).filter(function(c){return c.className.indexOf('on')>=0;}).length})")
            ok(r3 and '回归A' in (r3.get('names') or []) and r3.get('active') == 1,
               '③ 重开弹窗方案持久且 chip 激活（当前配置匹配）')

            # ── ⑤ 用户隔离：他人账号无该方案 ──
            conn = sqlite3.connect(DB)
            conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U2, hash_pw('Xx123456')))
            conn.commit(); conn.close()
            st, dp = api('/api/prefs', tk=make_token(U2))
            ok(st == 200 and 'sort_schemes' not in (dp.get('prefs') or {}),
               '⑤ 用户隔离：他人账号无 sort_schemes（%s）' % st)

            # ── ⑥ 换设备恢复：清 localStorage → 重载 → 服务端拉回 ──
            await ev("localStorage.removeItem('tapd.sortSchemes_'+ME.username);location.href='/';")
            await asyncio.sleep(1)
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True: break
            await asyncio.sleep(2.5)
            r6 = await ev("SORT_SCHEMES.map(function(s){return s.name;})")
            ok('回归A' in (r6 or []), '⑥ 换设备（localStorage 已清）→ 登录拉回方案（%s）' % r6)
            # 顺手测 ls 回写
            ok(await ev("!!localStorage.getItem('tapd.sortSchemes_'+ME.username)") is True,
               '⑥ 服务端配置回写本地缓存')

            # ── ④ 删除方案（真实 confirm 对话框）──
            dialogs.clear()
            await ev("openSortSetModal()")
            await asyncio.sleep(0.4)
            await ev("ssSchemeDel(0)")
            await asyncio.sleep(1.0)
            ok(any('删除方案' in d for d in dialogs), '④ 删除弹出确认对话框')
            srv2 = pref_row('admin', 'sort_schemes')
            ok(srv2 is not None and len(srv2) == 0 or srv2 == [],
               '④ 删除后方案清单为空（服务端同步：%s）' % srv2)
            await ev("sortSetCancel()")
        finally:
            try:
                if w: await w.close()
            except Exception: pass
            from cdp_test_helper import kill_profile_chrome
            kill_profile_chrome('cdp_t236')
            try: proc.kill()
            except Exception: pass
            shutil.rmtree(profile, ignore_errors=True)

    asyncio.run(run())

    # 收尾：恢复 admin prefs 快照 + 夹具清理
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM user_prefs WHERE username='admin' AND key IN ('sort_cfg','sort_schemes')")
    for r in SNAP:
        conn.execute('INSERT INTO user_prefs (username, key, value, updated_at) VALUES (?,?,?,?)',
                     (r['username'], r['key'], r['value'], r['updated_at']))
    conn.execute("DELETE FROM users WHERE username LIKE '%t236%'")
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t236%'").fetchone()[0]
    # 恢复核对：admin 的 sort_cfg/sort_schemes 行与快照完全一致（快照干净=无测试痕迹）
    now_rows = [dict(r) for r in conn.execute(
        "SELECT username,key,value FROM user_prefs WHERE username='admin' AND key IN ('sort_cfg','sort_schemes') ORDER BY key")]
    exp_rows = sorted([{'username': r['username'], 'key': r['key'], 'value': r['value']} for r in SNAP],
                      key=lambda x: x['key'])
    conn.close()
    ok(left == 0 and now_rows == exp_rows,
       '清理 夹具零残留 + admin prefs 与快照一致（users=%s rows=%s/%s）' % (left, len(now_rows), len(exp_rows)))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

main()
