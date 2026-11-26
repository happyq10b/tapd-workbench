# -*- coding: utf-8 -*-
"""T-237 综合看板/排序设定三处调整验证：
【API】① 自建方案入列：配置人 GET syn-my-schemes 含自己名下方案（self=True，
        显示方案默认 active）② 自建方案选择生效：勾选空白名单方案 → 视图全放开
③ 按钮显隐：U 接受邀请 → /api/me syn_depts 含架构；退出全部 → 不含（按钮隐藏）；
   重新勾选 → 恢复；pending 未确认者不含；配置人恒含
【CDP】④ 排序设定弹窗：无说明文字、无方案空态提示、内容完整无滚动条
收尾恢复 nid=4 快照 + 夹具零残留。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
NID = 4
BOARD = 'BCP1793717004248'
TK = make_token('admin')
U = '__t237_u1'    # 接收方案的成员
U2 = '__t237_u2'   # pending 未确认成员

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

def db_rows(q, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows

def snap():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    s = {
        'scheme': [dict(r) for r in conn.execute('SELECT * FROM syn_scheme WHERE dept_node_id=?', (NID,))],
        'bcfg': [dict(r) for r in conn.execute('SELECT * FROM syn_board_config WHERE dept_node_id=?', (NID,))],
        'member': [dict(r) for r in conn.execute('SELECT * FROM syn_config_member WHERE dept_node_id=?', (NID,))],
        'smem': [dict(r) for r in conn.execute('SELECT * FROM syn_scheme_member WHERE dept_node_id=?', (NID,))],
        # T-238：邀请行也纳入忠实快照（测试保存流会删除成员的 pending 邀请，恢复必须带回）
        'invite': [dict(r) for r in conn.execute('SELECT * FROM syn_config_invite WHERE dept_node_id=?', (NID,))],
    }
    conn.close()
    return s

def restore(s):
    conn = sqlite3.connect(DB)
    conn.execute('DELETE FROM syn_scheme_member WHERE dept_node_id=?', (NID,))
    conn.execute('DELETE FROM syn_scheme WHERE dept_node_id=?', (NID,))
    for r in s['scheme']:
        conn.execute('INSERT INTO syn_scheme (id,dept_node_id,owner,name,columns,extra_members,is_display,updated_at) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['owner'], r['name'], r['columns'],
                      r['extra_members'], r['is_display'], r['updated_at']))
    conn.execute('DELETE FROM syn_config_member WHERE dept_node_id=?', (NID,))
    for r in s['member']:
        conn.execute('INSERT INTO syn_config_member (id,dept_node_id,member,owner) VALUES (?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['member'], r['owner']))
    for r in s['smem']:
        conn.execute('INSERT INTO syn_scheme_member (dept_node_id,username,scheme_id,status,updated_at) '
                     'VALUES (?,?,?,?,?)', (r['dept_node_id'], r['username'], r['scheme_id'],
                                            r['status'], r['updated_at']))
    conn.execute('DELETE FROM syn_config_invite WHERE dept_node_id=?', (NID,))
    for r in s['invite']:
        conn.execute('INSERT INTO syn_config_invite (id,dept_node_id,member,owner,status,created_at,decided_at,scheme_id) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (r['id'], r['dept_node_id'], r['member'], r['owner'], r['status'],
                      r['created_at'], r['decided_at'], r.get('scheme_id')))
    conn.commit(); conn.close()

def cleanup():
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM syn_scheme_member WHERE username LIKE '%t237%'")
    conn.execute("DELETE FROM syn_config_invite WHERE member LIKE '%t237%' OR owner LIKE '%t237%'")
    conn.execute("DELETE FROM syn_config_member WHERE member LIKE '%t237%' OR owner LIKE '%t237%'")
    conn.execute("DELETE FROM syn_scheme WHERE owner LIKE '%t237%'")
    conn.execute("DELETE FROM messages WHERE receiver LIKE '%t237%' OR sender LIKE '%t237%'"
                 " OR (kind='system' AND content LIKE '%追加邀请%')")
    conn.execute("DELETE FROM users WHERE username LIKE '%t237%'")
    conn.commit(); conn.close()

async def cdp_checks():
    """④ 排序设定弹窗：无说明文字 / 无空态提示 / 无滚动条"""
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t237')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                             '--disable-gpu', '--no-first-run', '--window-size=1440,900',
                             '--remote-debugging-port=9699', '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9699/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9699/json', timeout=5).read())
        ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
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
        await asyncio.sleep(2)
        await ev("openSortSetModal()")
        await asyncio.sleep(0.5)
        r4 = await ev("""(function(){
          const m=document.getElementById('sortSetModal');
          const card=m.querySelector('.modal');
          const banner=m.querySelector('.due-info-banner');
          const bar=document.getElementById('ss_scheme_bar');
          const rows=document.querySelectorAll('#sortSetBody .ss-row').length;
          return {bannerGone:!banner, emptyTextGone:bar.textContent.indexOf('暂无方案')<0,
                  rows:rows, scroll:card.scrollHeight-card.clientHeight,
                  h:card.clientHeight};
        })()""")
        ok(r4 and not r4.get('__error__') and r4.get('bannerGone') and r4.get('emptyTextGone'),
           '④ 说明文字与方案空态提示已删除')
        ok(r4 and r4.get('rows') == 12 and r4.get('scroll', 999) <= 1,
           '④ 弹窗 12 行内容完整、无滚动条（scroll=%s h=%s）' % ((r4 or {}).get('scroll'), (r4 or {}).get('h')))
        await ev("sortSetCancel()")
    finally:
        try:
            if w: await w.close()
        except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t237')
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)

def main():
    S = snap()
    try:
        # 夹具：成员 U / U2
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U, hash_pw('Xx123456')))
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U2, hash_pw('Xx123456')))
        conn.commit(); conn.close()
        tk_u = make_token(U)      # ⚠️ token 绑定 active_seq —— 用户落库后签发
        tk_u2 = make_token(U2)

        st, dc = api('/api/cards?board_id=%s&size=1' % BOARD)
        ck = (dc.get('columns') or [{}])[0].get('col_key', '')

        # admin 两个自建方案：甲 [ck]（显示）+ 乙 ['']（空白名单），U 被两方案追加、U2 仅乙
        st, d1 = api('/api/syn-config/%d' % NID, 'PUT', {'schemes': [
            {'name': '甲', 'columns': ck, 'extra_members': U},
            {'name': '乙', 'columns': '', 'extra_members': U2},
        ], 'display_index': 0})
        ok(st == 200 and d1.get('invited') == 2, '① admin 两方案保存 + 邀请发出（invited=2）')

        # ── ① 自建方案入列 ──
        st, dmy = api('/api/syn-my-schemes?dept_node_id=%d' % NID)
        schs = dmy.get('schemes') or []
        selfs = [s for s in schs if s.get('self')]
        ok(len(selfs) == 2 and [s['name'] for s in selfs] == ['甲', '乙'],
           '① 配置人选择清单含自己提交的两个方案（self=True）')
        stmap = {s['name']: s['status'] for s in selfs}
        ok(stmap.get('甲') == 'active' and stmap.get('乙') == 'exited',
           '① 自建方案默认态：显示方案「甲」=适用、「乙」=已退出（无接收行时）')

        # ── ② 自建方案选择生效（勾选空白名单的乙 → 视图全放开）──
        st, dsel = api('/api/syn-my-schemes?dept_node_id=%d' % NID)
        ids = {s['name']: s['id'] for s in (dsel.get('schemes') or [])}
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': [ids['乙']]})
        st, dv = api('/api/syn-boards?dept_node_ids=%d&syn_depts=%d' % (NID, NID))
        ok(st == 200 and (dv.get('col_whitelist') or []) == [] and (dv.get('free_boards') or []),
           '② 勾选空白名单方案「乙」→ 综合视图全板块放开（free_boards）')
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': [ids['甲']]})
        st, dv2 = api('/api/syn-boards?dept_node_ids=%d&syn_depts=%d' % (NID, NID))
        ok(st == 200 and ck in (dv2.get('col_whitelist') or []),
           '② 切回「甲」→ 视图按其白名单')

        # ── ③ 按钮显隐（syn_depts）──
        st, _ = api('/api/syn-invites/%d/decide' % _accept_first(U), 'POST', {'accept': True}, tk=tk_u)
        st, dme = api('/api/me', tk=tk_u)
        ok(str(NID) in [str(x) for x in (dme.get('syn_depts') or [])],
           '③ U 接受方案后 syn_depts 含架构（按钮显示）')
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': []}, tk=tk_u)
        st, dme = api('/api/me', tk=tk_u)
        ok(str(NID) not in [str(x) for x in (dme.get('syn_depts') or [])],
           '③ U 退出全部方案 → syn_depts 不含架构（按钮自动隐藏）')
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': [ids['甲']]}, tk=tk_u)
        st, dme = api('/api/me', tk=tk_u)
        ok(str(NID) in [str(x) for x in (dme.get('syn_depts') or [])],
           '③ U 重新勾选 → 按钮恢复')
        st, dme2 = api('/api/me', tk=tk_u2)
        ok(str(NID) not in [str(x) for x in (dme2.get('syn_depts') or [])],
           '③ U2 邀请 pending 未确认 → 按钮不显示')
        st, dmea = api('/api/me')
        ok(str(NID) in [str(x) for x in (dmea.get('syn_depts') or [])],
           '③ 配置人 admin 恒显示（不受退出影响）')

        # ── ④ CDP 排序弹窗 ──
        asyncio.run(cdp_checks())
    finally:
        cleanup()
        restore(S)
        conn = sqlite3.connect(DB)
        left = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t237%'").fetchone()[0]
        left2 = conn.execute("SELECT COUNT(*) FROM syn_scheme_member WHERE username LIKE '%t237%'").fetchone()[0]
        conn.close()
        ok(left == 0 and left2 == 0, '清理 夹具零残留（users=%s smem=%s）' % (left, left2))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

def _accept_first(member):
    rows = db_rows("SELECT id FROM syn_config_invite WHERE member=? AND status='pending' ORDER BY id DESC LIMIT 1",
                   (member,))
    return rows[0]['id'] if rows else 0

main()
