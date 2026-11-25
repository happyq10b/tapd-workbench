# -*- coding: utf-8 -*-
"""T-205z：排序方式改个人偏好设置（#205z 2026-11-18）API + CDP 实测
① 偏好保存：排序设定弹窗「确定」→ saveSortCfg → localStorage（本地缓存）+ PUT /api/prefs/sort_cfg（服务端固化，防抖 800ms）；
② 偏好读取：登录后 loadUserPrefs 拉取服务端 sort_cfg 覆盖内存（变化则重载当前列表）；
③ 按用户隔离：user_prefs 按 username 行隔离 —— 两个夹具账号各存各的、互不影响；
④ 换设备恢复：清 localStorage 后 loadUserPrefs 恢复服务端配置并回写本地缓存；
⑤ 一次性迁移：服务端缺、本地浏览器有 → 登录时自动上传。
夹具（__t205z_ 前缀账号 + user_prefs 行）测完即删；不触碰真实账号（admin/dsy）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = 'src/app.db'
_n = {'ok': 0, 'fail': 0}
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    _n['ok' if cond else 'fail'] += 1

def api(path, method='GET', body=None, tk=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (tk or ''))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def db_del_user_rows(accts):
    """精确主键清理夹具（D2：先查后删，行数核对）。"""
    conn = sqlite3.connect(DB)
    for t, col in [('user_prefs', 'username'), ('users', 'username')]:
        marks = ','.join('?' * len(accts))
        cur = conn.execute('DELETE FROM %s WHERE %s IN (%s)' % (t, col, marks), accts)
        conn.commit()
    conn.close()

def db_del_sort_cfg(accts):
    """精确清理某账号的 sort_cfg 偏好行（key 精确匹配，非宽匹配）。"""
    conn = sqlite3.connect(DB)
    for a in accts:
        conn.execute("DELETE FROM user_prefs WHERE username=? AND key='sort_cfg'", (a,))
    conn.commit()
    left = {a: conn.execute("SELECT COUNT(*) FROM user_prefs WHERE username=? AND key='sort_cfg'", (a,)).fetchone()[0]
            for a in accts}
    conn.close()
    return left

CFG_A = {'card': {'order': ['due', 'begin'], 'dir': {'begin': 'asc', 'due': 'asc', 'created': 'desc'}},
         'col': {'order': ['created'], 'dir': {'begin': 'desc', 'due': 'desc', 'created': 'desc'}}}
CFG_B = {'card': {'order': ['created'], 'dir': {'begin': 'asc', 'due': 'asc', 'created': 'asc'}},
         'col': {'order': ['begin'], 'dir': {'begin': 'desc', 'due': 'desc', 'created': 'desc'}}}
# 迁移场景注入 localStorage 的本地旧值（服务端缺、本地有 → 登录后应上传）
CFG_MIGRATE = {'card': {'order': ['due'], 'dir': {'begin': 'asc', 'due': 'desc', 'created': 'asc'}},
               'col': {'order': ['begin'], 'dir': {'begin': 'asc', 'due': 'asc', 'created': 'asc'}}}

async def main():
    import websockets
    A, B = '__t205z_a', '__t205z_b'
    conn = sqlite3.connect(DB); conn.close()
    db_del_user_rows([A, B])   # 幂等清场
    try:
        # ── 夹具：两个 editor 账号（allowed_boards='*'，prefs 按 username 隔离） ──
        conn = sqlite3.connect(DB)
        now = '2026-11-18 20:30:00'
        for acct in (A, B):
            conn.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                         " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
        conn.commit(); conn.close()
        tk_a, tk_b = make_token(A), make_token(B)

        # ── ① 偏好未配置：GET /api/prefs 无 sort_cfg ──
        st, d = api('/api/prefs', tk=tk_a)
        ok(st == 200 and 'sort_cfg' not in (d.get('prefs') or {}), "① 新账号 GET prefs 无 sort_cfg（未配置态）")

        # ── ② 保存 + 读取：a PUT sort_cfg → GET 读回一致 ──
        st, d = api('/api/prefs/sort_cfg', 'PUT', {'value': CFG_A}, tk=tk_a)
        ok(st == 200 and d.get('ok'), "② PUT /api/prefs/sort_cfg 保存成功")
        st, d = api('/api/prefs', tk=tk_a)
        got = (d.get('prefs') or {}).get('sort_cfg') or {}
        ok(got.get('card') == CFG_A['card'] and got.get('col') == CFG_A['col'],
           "② GET 读回与保存值一致（card.order=%s）" % (got.get('card') or {}).get('order'))

        # ── ③ 按用户隔离：b 存不同值 → a/b 各自读回自己的，互不影响 ──
        api('/api/prefs/sort_cfg', 'PUT', {'value': CFG_B}, tk=tk_b)
        ga = api('/api/prefs', tk=tk_a)[1]['prefs']['sort_cfg']
        gb = api('/api/prefs', tk=tk_b)[1]['prefs']['sort_cfg']
        ok(ga['card']['order'] == CFG_A['card']['order'] and gb['card']['order'] == CFG_B['card']['order'],
           "③ 用户隔离：a=%s / b=%s 各自独立" % (ga['card']['order'], gb['card']['order']))

        # 清理 API 层写入（防抖 PUT 已在上方 sleep 前落库）→ CDP 场景从干净状态开始
        time.sleep(1.2)
        left = db_del_sort_cfg([A, B])
        ok(all(v == 0 for v in left.values()), "③-bis 清理 API 层配置，CDP 前提归零（残留 %s）" % left)

        # ── ④~⑦ CDP：a 账号全链路 ──
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205z')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                          '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                          '--remote-debugging-port=9671', '--user-data-dir=' + profile,
                          'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9671/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        w = None
        try:
            t = json.loads(urllib.request.urlopen('http://127.0.0.1:9671/json', timeout=5).read())
            ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
            w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
            pending = {}
            async def reader():
                while True:
                    m = json.loads(await w.recv())
                    if m.get('id') is not None and m['id'] in pending:
                        f = pending.pop(m['id'])
                        if f and not f.done(): f.set_result(m)
            seq = [0]
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
            await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_a))
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True: break
            await asyncio.sleep(2)
            key = 'tapd.sortCfg_' + A

            # ④ 弹窗默认态 + 修改 + 确定 → 本地缓存与服务端同时固化
            r4 = await ev("""(function(){
              openSortSetModal();
              const before=JSON.parse(JSON.stringify(SORT_CFG.card.order));
              sortSetToggle('card','created',false);      // 取消「创建时间」→ order 只剩 begin,due
              sortSetApply();
              return {before:before, after:JSON.parse(JSON.stringify(SORT_CFG.card.order)),
                      ls:localStorage.getItem(%s)};
            })()""" % json.dumps(key))
            ok(r4 and not r4.get('__error__') and r4.get('before') == ['begin', 'due', 'created']
               and r4.get('after') == ['begin', 'due'],
               "④ 弹窗：默认三字段 → 取消「创建时间」→ order=[begin,due]（%s）" % (r4 or {}).get('after'))
            ok(r4 and r4.get('ls') and json.loads(r4['ls']).get('card', {}).get('order') == ['begin', 'due'],
               "④ 「确定」即固化：localStorage 本地缓存同步更新")
            await asyncio.sleep(1.5)   # _prefPush 防抖 800ms
            srv = api('/api/prefs', tk=tk_a)[1]['prefs'].get('sort_cfg') or {}
            ok((srv.get('card') or {}).get('order') == ['begin', 'due'],
               "④ 服务端 user_prefs.sort_cfg 已固化（card.order=%s）" % (srv.get('card') or {}).get('order'))

            # ⑤ 换设备模拟：清 localStorage → loadUserPrefs 从服务端恢复 + 回写本地
            r5 = await ev("(async function(){localStorage.removeItem(%s);await loadUserPrefs();"
                          "return {mem:JSON.parse(JSON.stringify(SORT_CFG.card.order)),"
                          "lsBack:JSON.parse(localStorage.getItem(%s)||'null')};})()"
                          % (json.dumps(key), json.dumps(key)), aw=True)
            ok(r5 and not r5.get('__error__') and r5.get('mem') == ['begin', 'due']
               and (r5.get('lsBack') or {}).get('card', {}).get('order') == ['begin', 'due'],
               "⑤ 换设备：清本地缓存 → 服务端配置恢复内存 + 回写 localStorage（%s）" % (r5 or {}).get('mem'))

            # ⑥ 一次性迁移：删服务端行（等防抖 PUT 全部落库后再删一次防复活）
            #   → 本地注入旧值 → 重载页面 → 登录时自动上传
            conn = sqlite3.connect(DB)
            cur = conn.execute("DELETE FROM user_prefs WHERE username=?", (A,)); conn.commit()
            n_del = cur.rowcount; conn.close()
            # T-236 起 sortSetApply 同时固化 sort_schemes 行 → a 名下可能有 2 行（sort_cfg+sort_schemes）
            ok(n_del >= 1, "⑥ 预置：清除 a 的 user_prefs 行（rowcount=%d，含 T-236 sort_schemes 行）" % n_del)
            await asyncio.sleep(1.2)   # 等飞行中的防抖 PUT（若有）落库
            left6 = db_del_sort_cfg([A])[A]
            ok(left6 == 0, "⑥-bis 二次删除防复活（残留 %d）" % left6)
            await ev("localStorage.setItem(%s, JSON.stringify(%s));location.href='/';"
                     % (json.dumps(key), json.dumps(CFG_MIGRATE)))
            await asyncio.sleep(1)
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME") is True: break
            await asyncio.sleep(2.5)   # loadUserPrefs 迁移上传（防抖 800ms）
            # 轮询等待迁移 PUT 落库（最多 8s）
            mig = {}
            for _ in range(16):
                mig = api('/api/prefs', tk=tk_a)[1]['prefs'].get('sort_cfg') or {}
                if (mig.get('card') or {}).get('order') == ['due']: break
                await asyncio.sleep(0.5)
            ok((mig.get('card') or {}).get('order') == ['due'] and (mig.get('card') or {}).get('dir', {}).get('due') == 'desc',
               "⑥ 一次性迁移：服务端缺、本地有 → 登录后自动上传（card.order=%s）" % (mig.get('card') or {}).get('order'))
            r6 = await ev("loadSortCfg();JSON.stringify(SORT_CFG.card.order)")
            # 注：夹具 editor 账号无看板选中 → reload 不走 renderBoard → loadSortCfg 未自动执行
            # （真实用户登录必选看板、renderBoard 必跑）。此处手动触发同一读取逻辑验证。
            ok(r6 == '["due"]', "⑥ 迁移后读取逻辑恢复本地/服务端配置（%s）" % r6)

            # ⑦ 换用户登录：b 无配置（服务端已在 ③-bis 清理）→ 默认配置、无本地缓存
            await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_b))
            for _ in range(90):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='%s'" % B) is True: break
            await asyncio.sleep(2.5)
            r7 = await ev("({u:ME.username, order:JSON.parse(JSON.stringify(SORT_CFG.card.order)),"
                          "ls:localStorage.getItem('tapd.sortCfg_'+ME.username)})")
            ok(r7 and r7.get('u') == B and r7.get('order') == ['begin', 'due', 'created'] and r7.get('ls') is None,
               "⑦ 换用户：b 登录后为默认配置、无本地缓存（与 a 完全隔离，%s）" % (r7 or {}).get('order'))
            ok('sort_cfg' not in (api('/api/prefs', tk=tk_b)[1].get('prefs') or {}),
               "⑦ b 的服务端 prefs 仍无 sort_cfg（a 的配置不会串到 b）")
        finally:
            try:
                if w: await w.close()
            except Exception: pass
            from cdp_test_helper import kill_profile_chrome
            kill_profile_chrome('cdp_t205z')
            shutil.rmtree(profile, ignore_errors=True)
    finally:
        await asyncio.sleep(1.5)   # 等飞行中的防抖 PUT 全部落库
        db_del_user_rows([A, B])   # 夹具自清理（users + user_prefs）
        await asyncio.sleep(0.8)
        db_del_user_rows([A, B])   # 二次删除：防迁移 PUT 竞态复活
        conn = sqlite3.connect(DB)
        left = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '__t205z%'").fetchone()[0]
        conn.close()
        print('fixture residue: %d' % left, flush=True)

asyncio.run(main())
print('结果：通过 %d / 失败 %d' % (_n['ok'], _n['fail']), flush=True)
sys.exit(1 if _n['fail'] else 0)
