# -*- coding: utf-8 -*-
"""T-240 验证（API + CDP）：
【API】① 消息清空：夹具用户种子消息 → POST /api/messages/clear-all → 清空、计数正确
② 用户隔离：他人消息不受影响  ③ 清空后再清 → cleared=0
【CDP】④ 架构/看板两带高度固定两行（单行内容也保留第二行空位）、overflow-y:auto
⑤ 消息面板：清空按钮存在、confirm 二次确认、确认后空状态展示
收尾夹具零残留（admin 真实消息数与运行前一致）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
BOARD = 'BCP1793717004248'
NID = 4
TK = make_token('admin')
U = '__t240_u1'     # 消息清空夹具
U2 = '__t240_u2'    # 隔离对照夹具

OK = []
def ok(cond, label):
    OK.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + label)

def api(path, method='GET', body=None, tk=None, syn=False):
    if syn and 'syn_depts=' not in path:
        path += ('&' if '?' in path else '?') + 'syn_depts=%d' % NID
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

def db_exec(q, args=()):
    conn = sqlite3.connect(DB)
    cur = conn.execute(q, args)
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n

def db_rows(q, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows

def seed_msgs(who, n, tag):
    for i in range(n):
        db_exec("INSERT INTO messages (receiver, sender, card_id, kind, content) VALUES (?,?,?,?,?)",
                (who, 'admin', '', 'system', '%s 种子消息 %d' % (tag, i + 1)))

async def cdp_checks():
    """④ 两带固定两行高  ⑤ 消息面板清空流（confirm 对话框处理）"""
    TOK_U = make_token(U)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t240')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                             '--disable-gpu', '--no-first-run', '--window-size=1440,900',
                             '--remote-debugging-port=9709', '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    dialogs = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9709/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9709/json', timeout=5).read())
        ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}; seq = [0]
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
                elif m.get('method') == 'Page.javascriptDialogOpening':
                    dialogs.append(m['params'].get('message') or '')
                    # fire-and-forget（await 会阻塞 reader 响应消费 → 死锁）
                    asyncio.get_event_loop().create_task(
                        send('Page.handleJavaScriptDialog', {'accept': True}))
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
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TOK_U))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        # ── ④ 两带固定两行高 ──
        r4 = await ev("""(function(){
          function probe(id){
            const g=document.getElementById(id);
            if(!g||g.offsetParent===null)return {err:id+' 不可见'};
            const cs=getComputedStyle(g);
            const items=[].slice.call(g.children).filter(function(x){return x.offsetParent!==null;});
            const gap=parseFloat(cs.rowGap)||6;
            const h1=items.length?items[0].getBoundingClientRect().height:0;
            const two=h1+gap+(items.length>1?items[1].getBoundingClientRect().height:h1)+6;
            return {id:id, h:Math.round(g.getBoundingClientRect().height),
                    fixed:!!g.style.height, overflowY:cs.overflowY,
                    twoRowOK:Math.abs(g.getBoundingClientRect().height-two)<=2,
                    n:items.length};
          }
          return [probe('tbDepts'), probe('tbBoards')];
        })()""")
        for r in (r4 or []):
            ok(r and not r.get('err') and r.get('fixed') and r.get('twoRowOK') and r.get('overflowY') == 'auto',
               '④ %s 高度固定两行 + 区域内滚动（h=%s n=%s overflowY=%s）'
               % (r.get('id'), r.get('h'), r.get('n'), r.get('overflowY')) if r else '④ 不可见')

        # ── ⑤ 消息面板清空流 ──
        await ev("openMsgPanel()")
        await asyncio.sleep(1)
        r5a = await ev("({btn:!!document.getElementById('msgClearBtn'),"
                       " items:document.querySelectorAll('#msgList .msg-item').length})")
        ok(r5a and r5a.get('btn') and (r5a.get('items') or 0) >= 1,
           '⑤ 消息面板打开：清空按钮存在、种子消息在列（items=%s）' % (r5a or {}).get('items'))
        dialogs.clear()
        await ev("clearAllMessages()")
        await asyncio.sleep(1.2)
        ok(any('确定清空全部消息' in d for d in dialogs), '⑤ 二次确认提示出现（confirm）')
        r5b = await ev("({empty:!!document.querySelector('#msgList .msg-empty'),"
                       " items:document.querySelectorAll('#msgList .msg-item').length,"
                       " badge:document.getElementById('msgBadge').hidden})")
        ok(r5b and r5b.get('empty') and (r5b.get('items') or 0) == 0,
           '⑤ 清空后消息列表为空状态')
        ok(r5b and r5b.get('badge') is True, '⑤ 铃铛未读徽标归零')
    finally:
        try:
            if w: await w.close()
        except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t240')
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)

def main():
    ADM_MSGS = db_rows("SELECT COUNT(*) n FROM messages WHERE receiver='admin'")[0]['n']
    try:
        # 夹具：两个用户 + 各自种子消息
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U, hash_pw('Xx123456')))
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U2, hash_pw('Xx123456')))
        conn.commit(); conn.close()
        tk_u = make_token(U)      # ⚠️ token 绑定 active_seq —— 用户落库后签发
        tk_u2 = make_token(U2)
        seed_msgs(U, 3, 'T-240')

        # ── ① 清空：计数与空态 ──
        st, d0 = api('/api/messages', tk=tk_u)
        ok(st == 200 and len(d0.get('messages') or []) == 3, '① 种子消息 3 条在列')
        st, d1 = api('/api/messages/clear-all', 'POST', tk=tk_u)
        ok(st == 200 and d1.get('cleared') == 3, '① 清空成功（cleared=%s）' % (d1 or {}).get('cleared'))
        st, d1b = api('/api/messages', tk=tk_u)
        ok(st == 200 and not (d1b.get('messages') or []) and not (d1b.get('unread') or 0),
           '① 清空后消息列表为空、未读归零')

        # ── ② 用户隔离 ──
        seed_msgs(U2, 2, 'T-240')
        st, d2 = api('/api/messages', tk=tk_u2)
        ok(st == 200 and len(d2.get('messages') or []) == 2,
           '② 他人消息不受影响（U2 仍有 2 条）')

        # ── ③ 再清一次 → cleared=0 ──
        st, d3 = api('/api/messages/clear-all', 'POST', tk=tk_u)
        ok(st == 200 and d3.get('cleared') == 0, '③ 空清单再清 → cleared=0')

        # ── ④⑤ CDP（重新播种 U 的消息供面板清空流使用）──
        seed_msgs(U, 2, 'T-240 面板流')
        st, dchk = api('/api/messages', tk=tk_u)
        print('⑤ 前置：重播种后 U 的 API 计数 =', len(dchk.get('messages') or []))
        asyncio.run(cdp_checks())
    finally:
        db_exec("DELETE FROM messages WHERE receiver LIKE '%t240%'")
        db_exec("DELETE FROM users WHERE username LIKE '%t240%'")
        adm = db_rows("SELECT COUNT(*) n FROM messages WHERE receiver='admin'")[0]['n']
        left = db_rows("SELECT COUNT(*) n FROM users WHERE username LIKE '%t240%'")[0]['n']
        left2 = db_rows("SELECT COUNT(*) n FROM messages WHERE receiver LIKE '%t240%'")[0]['n']
        ok(left == 0 and left2 == 0 and adm == ADM_MSGS,
           '清理 夹具零残留 + admin 消息数与运行前一致（adm=%s 快照=%s）' % (adm, ADM_MSGS))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)), '| ADM_MSGS =', ADM_MSGS)

main()
