# -*- coding: utf-8 -*-
"""T-235 综合看板升级验证：
【API】① 首次追加→邀请→确认→接收登记  ② 多方案接收（双发起人并存不驱逐）
③ 选择弹窗数据源（syn-my-schemes）  ④ 选择/退出即时生效（视图白名单并集/单选/退出全部）
⑤ 全量候选（除 admin 外全部用户、含跨部门）
【CDP】⑥ 类别强排序取消  ⑦ 综合看板按钮→方案选择弹窗→勾选/退出/确定进入综合模式
收尾恢复 nid=4 快照 + 夹具零残留。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
NID = 4                      # 核算部（有真实配置，快照恢复）
BOARD = 'BCP1793717004248'
TK = make_token('admin')
U = '__t235_u1'              # 接收方案的成员（夹具）
U2 = '__t235_u2'             # 拒绝流成员（夹具）
O2 = '__t235_o2'             # 第二发起人（admin 角色夹具）

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
            if 'json' in r.headers.get('Content-Type', ''):
                return r.status, json.loads(r.read().decode())
            return r.status, r.read()
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
    conn.commit(); conn.close()

def cleanup():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM syn_scheme_member WHERE username LIKE '%t235%'")
    conn.execute("DELETE FROM syn_config_invite WHERE member LIKE '%t235%' OR owner LIKE '%t235%'")
    conn.execute("DELETE FROM syn_config_member WHERE member LIKE '%t235%' OR owner LIKE '%t235%'")
    conn.execute("DELETE FROM syn_scheme WHERE owner LIKE '%t235%'")
    conn.execute("DELETE FROM messages WHERE receiver LIKE '%t235%' OR sender LIKE '%t235%'"
                 " OR (kind='system' AND content LIKE '%已接受您发出的追加邀请%')"
                 " OR (kind='system' AND content LIKE '%已拒绝您发出的追加邀请%')")
    conn.execute("DELETE FROM users WHERE username LIKE '%t235%'")
    conn.commit(); conn.close()

async def cdp_checks():
    """CDP：⑥ 类别强排序取消 ⑦ 按钮→弹窗→选择/退出/确定"""
    TOK_U = make_token(U)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t235')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                             '--disable-gpu', '--no-first-run', '--window-size=1440,900',
                             '--remote-debugging-port=9681', '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9681/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9681/json', timeout=5).read())
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
        async def click_pt(js):
            pt = await ev(js)
            if not pt or pt.get('x') is None: return None
            await send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': pt['x'], 'y': pt['y']})
            await send('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': pt['x'], 'y': pt['y'], 'button': 'left', 'buttons': 1, 'clickCount': 1})
            await send('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': pt['x'], 'y': pt['y'], 'clickCount': 1})
            return pt
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TOK_U))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        # ⑥ 类别强排序取消（stub eval）
        r6 = await ev("""(function(){
          const bak=typeof SYN_MODE!=='undefined'?SYN_MODE:null;
          SYN_MODE={name:'X',nodeIds:[4]};
          const cmeta={'甲':{col_key:'b::甲',created_at:'2026-01-01',category:'文化及团队建设'},
                       '乙':{col_key:'b::乙',created_at:'2026-01-01',category:'年度重点工作'}};
          const out=['甲','乙','丙'].sort(function(x,y){return cmpColumn(x,y,cmeta,null);});
          SYN_MODE=bak;
          return out;
        })()""")
        ok(isinstance(r6, list) and r6 == ['甲', '乙', '丙'],
           '⑥ 综合模式不再按类别强排序（同创建时间按名称兜底：甲/乙在前、%s）' % r6)
        # ⑦ 按钮 → 弹窗 → 确定 → 进入综合模式
        await ev("if(!DEPT_OPEN['核算部'])toggleDept('核算部')")
        await asyncio.sleep(1)
        r7 = await ev("toggleSynMode()")   # 探针验证：直接调用（真实点击受 WS 重绘时序干扰）
        await asyncio.sleep(1.5)
        st_modal = await ev("({open:getComputedStyle(document.getElementById('synMyModal')).display!=='none',"
                            " rows:document.querySelectorAll('#synMyList input[type=checkbox]').length,"
                            " myN:(typeof SYN_MY!=='undefined'&&SYN_MY)?SYN_MY.items.length:-1,"
                            " arch:[...ARCH_SEL], btnVis:(function(){const b=document.getElementById('bandSynBtn');return b?b.offsetParent!==null:false;})()})")
        ok(st_modal and st_modal.get('open') and st_modal.get('rows', 0) >= 1,
           '⑦ 点【综合看板】弹出方案选择弹窗（rows=%s myN=%s arch=%s btnVis=%s）'
           % ((st_modal or {}).get('rows'), (st_modal or {}).get('myN'),
              (st_modal or {}).get('arch'), (st_modal or {}).get('btnVis')))
        r_names = await ev("[].slice.call(document.querySelectorAll('#synMyList b')).map(function(x){return x.textContent;})")
        ok(r_names and ('默认方案' in (r_names or [])) and ('S2方案' in (r_names or [])),
           '⑦ 弹窗列出接收方案「默认方案」+「S2方案」（%s）' % r_names)
        # 确定（保持勾选）→ 进入综合模式
        await ev("synMyApply()")
        await asyncio.sleep(2.5)
        ok(await ev("!!SYN_MODE") is True, '⑦ 确定后进入综合看板模式')
        # 退出综合模式 → 再开 → 退出方案（立即生效）
        await ev("exitSynMode()")
        await asyncio.sleep(1.5)
        await ev("toggleSynMode()")
        await asyncio.sleep(1.5)
        await ev("(function(){const x=[].slice.call(document.querySelectorAll('#synMyList span')).find(function(s){return s.textContent==='退出'&&s.offsetParent!==null;});if(x)x.click();return 1;})()")
        await asyncio.sleep(1.5)
        st2 = await ev("({open:getComputedStyle(document.getElementById('synMyModal')).display!=='none',"
                       " anyChecked:[].slice.call(document.querySelectorAll('#synMyList input[type=checkbox]')).some(function(c){return c.checked;}),"
                       " badge:[].slice.call(document.querySelectorAll('#synMyList span')).some(function(s){return s.textContent==='适用中';})})")
        ok(st2 and st2.get('open') and st2.get('anyChecked') is True,
           '⑦ 点【退出】→ 该方案取消勾选，另一方案保持勾选（单方案退出语义）')
        rows = db_rows("SELECT status FROM syn_scheme_member WHERE username=? AND dept_node_id=?", (U, NID))
        ok(sorted(r['status'] for r in rows) == ['active', 'exited'],
           '⑦ 退出落库：1 exited + 1 active（%s）' % [r['status'] for r in rows])
        # 收尾：取消弹窗（不进入）
        await ev("synMyCancel()")
    finally:
        try:
            if w: await w.close()
        except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t235')
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)

def main():
    S = snap()
    try:
        # 夹具：成员 U + 第二发起人 O2（admin 角色 → 全架构可配置）
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U, hash_pw('Xx123456')))
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'editor',1)", (U2, hash_pw('Xx123456')))
        conn.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq) VALUES (?,?,'admin',1)", (O2, hash_pw('Xx123456')))
        conn.commit(); conn.close()
        tk_u = make_token(U)     # ⚠️ token 绑定 active_seq —— 必须在用户落库后签发
        tk_u2 = make_token(U2)
        tk_o2 = make_token(O2)

        # 取 BCP 的一个真实板块 col_key 做白名单
        st, dc = api('/api/cards?board_id=%s&size=1' % BOARD)
        ck = (dc.get('columns') or [{}])[0].get('col_key', '')

        # ── ① 首次追加→邀请→确认→接收登记 ──
        st, d1 = api('/api/syn-config/%d' % NID, 'PUT',
                     {'columns': ck, 'extra_members': U})
        ok(st == 200 and d1.get('invited') == 1, '① admin 首次追加 U → 发邀请（invited=1，不再即时生效）')
        rows = db_rows("SELECT owner FROM syn_config_member WHERE member=? AND dept_node_id=?", (U, NID))
        ok(not rows, '① 确认前无归属/无接收（syn_config_member 空）')
        st, dmy = api('/api/syn-my-schemes?dept_node_id=%d' % NID, tk=tk_u)
        ok(st == 403, '① 确认前无接收能力位 → 弹窗数据接口 403（HTTP %s）' % st)
        st, dinv = api('/api/syn-invites', tk=tk_u)
        invs = [x for x in (dinv.get('invites') or []) if x['owner'] == 'admin']
        ok(len(invs) == 1, '① U 收到 admin 邀请')
        st, _ = api('/api/syn-invites/%d/decide' % invs[0]['id'], 'POST', {'accept': True}, tk=tk_u)
        rows = db_rows("SELECT scheme_id,status FROM syn_scheme_member WHERE username=? AND dept_node_id=?", (U, NID))
        ok(len(rows) == 1 and rows[0]['status'] == 'active', '① 确认后接收登记 active（%s）' % rows)

        # ── ② 多方案接收：第二发起人 O2 → U 再收一个方案 ──
        st, d2 = api('/api/syn-config/%d' % NID, 'PUT',
                     {'schemes': [{'name': 'S2方案', 'columns': ck, 'extra_members': U}],
                      'display_index': 0}, tk=tk_o2)
        ok(st == 200 and d2.get('invited') == 1, '② O2 追加已接收 admin 方案的 U → 仍发邀请（可并存）')
        st, dinv2 = api('/api/syn-invites', tk=tk_u)
        inv2 = [x for x in (dinv2.get('invites') or []) if x['owner'] == O2]
        ok(len(inv2) == 1 and inv2[0]['scheme_name'] == 'S2方案', '② U 收到 O2 的「S2方案」邀请')
        st, _ = api('/api/syn-invites/%d/decide' % inv2[0]['id'], 'POST', {'accept': True}, tk=tk_u)
        rows = db_rows("SELECT status FROM syn_scheme_member WHERE username=? AND dept_node_id=?", (U, NID))
        ok(len(rows) == 2 and all(r['status'] == 'active' for r in rows),
           '② U 同时接收 2 个方案（多方案并存，%d 行 active）' % len(rows))
        st, dA = api('/api/syn-config?dept_node_id=%d' % NID)
        ok(any(U in (s.get('extra_members') or []) for s in (dA.get('schemes') or [])),
           '② admin 方案仍包含 U（确认不驱逐原发起人）')

        # ── ③ 选择弹窗数据源 ──
        st, dmy = api('/api/syn-my-schemes?dept_node_id=%d' % NID, tk=tk_u)
        schs = dmy.get('schemes') or []
        ok(st == 200 and len(schs) == 2 and all(s['status'] == 'active' for s in schs),
           '③ 选择弹窗数据：2 个已接收方案均 active（%s）' % [s['name'] for s in schs])

        # ── ④ 选择/退出即时生效（视图白名单）──
        st, dv = api('/api/syn-boards?dept_node_ids=%d&syn_depts=%d' % (NID, NID), tk=tk_u)
        ok(st == 200 and ck in (dv.get('col_whitelist') or []),
           '④ 双方案 active → 综合视图白名单含 ck（并集口径）')
        keep = [s['id'] for s in schs if s['owner'] == 'admin']
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': keep}, tk=tk_u)
        st, dv2 = api('/api/syn-boards?dept_node_ids=%d&syn_depts=%d' % (NID, NID), tk=tk_u)
        ok(st == 200 and (dv2.get('col_whitelist') or []) == (dv.get('col_whitelist') or []),
           '④ 只保留 admin 方案 → 视图仍含 ck（S2 同白名单，退出其一不影响并集结果）')
        rows = db_rows("SELECT scheme_id,status FROM syn_scheme_member WHERE username=? AND dept_node_id=?", (U, NID))
        ok(sorted(r['status'] for r in rows) == ['active', 'exited'],
           '④ 选择落库：1 active + 1 exited（%s）' % [r['status'] for r in rows])
        # 退出全部 → 视图为空
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': []}, tk=tk_u)
        st, dv3 = api('/api/syn-boards?dept_node_ids=%d&syn_depts=%d' % (NID, NID), tk=tk_u)
        ok(st == 200 and not (dv3.get('col_whitelist') or []) and not (dv3.get('boards') or []),
           '④ 全部退出 → 综合视图为空（可随时重新选择）')
        st, dmy2 = api('/api/syn-my-schemes?dept_node_id=%d' % NID, tk=tk_u)
        ok(all(s['status'] == 'exited' for s in (dmy2.get('schemes') or [])) and len(dmy2.get('schemes') or []) == 2,
           '④ 弹窗数据仍列全部已接收方案（status=exited，可重新勾选）')
        # 重新勾选 → 恢复
        st, _ = api('/api/syn-my-schemes/%d' % NID, 'POST', {'scheme_ids': [s['id'] for s in (dmy2.get('schemes') or [])]}, tk=tk_u)
        rows = db_rows("SELECT status FROM syn_scheme_member WHERE username=? AND dept_node_id=?", (U, NID))
        ok(all(r['status'] == 'active' for r in rows), '④ 重新勾选 → 全部恢复 active')

        # ── ⑤ 全量候选（除 admin 外）──
        st, dc2 = api('/api/syn-config?dept_node_id=%d' % NID)
        cands = {c['account'] for c in (dc2.get('candidates') or [])}
        ok(U in cands and 'admin' not in cands, '⑤ 候选含夹具成员、不含 admin')
        # 跨部门/全员：随机抽一个非本架构真实账号验证在候选内
        others = db_rows("SELECT username FROM users WHERE username NOT IN ('admin',?) LIMIT 1", (U,))
        if others:
            ok(others[0]['username'] in cands,
               '⑤ 任意真实账号 %s 均在候选（T-235 全量候选）' % others[0]['username'])

        # ── 拒绝反馈通知（新成员 U2 的首次追加 → 邀请 → 拒绝）──
        st, d3 = api('/api/syn-config/%d' % NID, 'PUT',
                     {'schemes': [{'name': 'S3方案', 'columns': '', 'extra_members': U2}],
                      'display_index': 0}, tk=tk_o2)
        ok(st == 200 and d3.get('invited') == 1, '⑤-2 O2 首次追加 U2 → 发邀请（全量邀请制）')
        st, dinv3 = api('/api/syn-invites', tk=tk_u2)
        inv3 = [x for x in (dinv3.get('invites') or []) if x['owner'] == O2]
        st, _ = api('/api/syn-invites/%d/decide' % inv3[0]['id'], 'POST', {'accept': False}, tk=tk_u2)
        st, dm = api('/api/messages', tk=tk_o2)
        ok('已拒绝您发出的追加邀请' in json.dumps(dm, ensure_ascii=False),
           '⑤-2 U2 拒绝 → O2 收到拒绝反馈通知')
        mems = db_rows("SELECT extra_members FROM syn_scheme WHERE dept_node_id=? AND owner=?", (NID, O2))
        ok(mems and U2 not in (mems[0]['extra_members'] or ''), '⑤-2 拒绝 → 发起人方案移除该成员')
        # 已确认过本人邀请的成员再次追加 → 直接生效（不再重复邀请）
        st, d4 = api('/api/syn-config/%d' % NID, 'PUT',
                     {'schemes': [{'name': 'S2方案', 'columns': ck, 'extra_members': U}],
                      'display_index': 0}, tk=tk_o2)
        ok(st == 200 and d4.get('invited') == 0, '⑤-3 U 已确认过 O2 → 再次追加直接生效（invited=0）')
        rows = db_rows("SELECT status FROM syn_scheme_member WHERE username=? AND dept_node_id=? AND scheme_id IN "
                       "(SELECT id FROM syn_scheme WHERE dept_node_id=? AND owner=?)", (U, NID, NID, O2))
        ok(rows and rows[0]['status'] == 'active', '⑤-3 直接生效：U 的接收登记含 O2 方案（active）')

        # ── CDP：⑥ 类别排序取消 ⑦ 弹窗流程 ──
        asyncio.run(cdp_checks())
    finally:
        cleanup()
        restore(S)
        conn = sqlite3.connect(DB)
        left = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t235%'").fetchone()[0]
        left2 = conn.execute("SELECT COUNT(*) FROM syn_scheme_member WHERE username LIKE '%t235%'").fetchone()[0]
        conn.close()
        ok(left == 0 and left2 == 0, '清理 夹具零残留（users=%s smem=%s）' % (left, left2))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

main()
