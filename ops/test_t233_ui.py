# -*- coding: utf-8 -*-
"""T-233 UI 冒烟（CDP）：综合配置弹窗方案条渲染/切换/保存往返 + 改名断言。
用后恢复：保存的测试方案经真源 syn_board_config 重建回滚（复用 t233 逻辑）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

NID = 4
BOARD = 'BCP1793717004248'
ok_n = fail_n = 0
def ok(cond, msg):
    global ok_n, fail_n
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if cond: ok_n += 1
    else: fail_n += 1

def api(tk, path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + tk)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20,
                                    data=json.dumps(body).encode() if body is not None else None) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t233ui')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                             '--headless=new', '--disable-gpu', '--no-first-run',
                             '--window-size=1440,900', '--remote-debugging-port=9681',
                             '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9681/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9681/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}; seq = [0]
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        async def send(mm, p=None):
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:200]}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        # 改名断言：按钮文案 = 综合配置
        btn = await ev("(function(){var b=document.getElementById('bandSynEditBtn');return b?b.textContent.trim():null})()")
        ok(btn == '综合配置', '① 【综合编辑】已改名【综合配置】（实际 %r）' % btn)
        # 打开配置弹窗（经综合模式路径：先锚定架构再进入综合模式）
        await ev("ensureOrgTree(false).then(function(){ARCH_SEL=new Set(['核算部']);return toggleSynMode();})" )
        await asyncio.sleep(2.5)
        synm = await ev("SYN_MODE?SYN_MODE.name:null")
        ok(synm == '核算部', '② 前置：进入「核算部」综合模式（%r）' % synm)
        await ev("openSynConfigModal(%d)" % NID)
        await asyncio.sleep(1.5)
        chips = await ev("(function(){return [].slice.call(document.querySelectorAll('#syn_scheme_chips .syn-scheme-chip')).map(function(x){return x.textContent.trim();});})()")
        ok(chips and len(chips) >= 1 and '默认方案' in chips[0],
           '② 方案条渲染：存量「默认方案」chip 存在（%s）' % chips)
        disp = await ev("(function(){return SYN_SCHEMES.map(function(s){return s.name+(s.disp?'*':'');});})()")
        ok(disp and disp[0].endswith('*'), '② 存量方案默认标记为外部显示方案（%s）' % disp)
        # 新建方案 + 切换
        await ev("synSchemeAdd()")
        await asyncio.sleep(0.3)
        n = await ev("SYN_SCHEMES.length")
        idx = await ev("SYN_SCHEME_IDX")
        ok(n == 2 and idx == 1, '③ 新建方案 → 2 个方案且激活新方案')
        # 新方案勾一个板块（第一个可见 col_key）
        ck = await ev("(function(){var c=synCollectBoards();return c.length?c[0].col_key:null;})()")
        await ev("SYN_CHECKED=new Set([%s]);synFlushScheme();" % json.dumps(ck))
        # 设为外部显示方案
        await ev("synSchemeSetDisplay(1)")
        # 保存（新方案 1 板块、默认方案保持原样全选→空串）
        await ev("saveSynConfig()")
        await asyncio.sleep(2)
        st, d = api(tk, '/api/syn-config?dept_node_id=%d' % NID)
        scs = d.get('schemes') or []
        ok(len(scs) == 2 and scs[1]['name'].startswith('方案') and scs[1]['columns'] == [ck]
           and scs[1]['is_display'] is True and scs[0]['is_display'] is False,
           '④ 保存往返：2 方案、新方案白名单 1 项、外部显示方案=新方案')
        # 恢复真源
        conn = sqlite3.connect('src/app.db'); conn.row_factory = sqlite3.Row
        cfg = [dict(r) for r in conn.execute('SELECT * FROM syn_board_config WHERE dept_node_id=?', (NID,))]
        conn.execute('DELETE FROM syn_scheme WHERE dept_node_id=?', (NID,))
        for r in cfg:
            conn.execute('INSERT INTO syn_scheme (dept_node_id,owner,name,columns,extra_members,is_display,updated_at) '
                         'VALUES (?,?,?,?,?,1,?)', (r['dept_node_id'], r['owner'], '默认方案',
                                                    r['columns'], r['extra_members'], r['updated_at']))
        conn.commit(); conn.close()
        st, d = api(tk, '/api/syn-config?dept_node_id=%d' % NID)
        ok(len(d.get('schemes') or []) == 1 and (d['schemes'][0]['name'] == '默认方案'),
           '⑤ 真源恢复：回到存量「默认方案」单方案')
    finally:
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t233ui')
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
print('结果: %d PASS / %d FAIL' % (ok_n, fail_n))
sys.exit(1 if fail_n else 0)
