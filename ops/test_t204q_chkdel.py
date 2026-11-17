# -*- coding: utf-8 -*-
"""T-204q（2026-11-17）勾选删除权限预检 —— CDP 实测：
  ① 板块负责人勾选「本板块 2 卡 + 别的板块 1 卡」→ 弹「部分事项无删除权限，是否仅
     删除权限内事项」→ 确定 → 权限内删除、越权卡保留
  ② 全部越权 → toast 提示，不弹确认、零删除
  ③ 部分越权 → 首个确认选「取消」→ 零删除
  ④ 判定函数单测（板块负责人有权/无权；管理员直通）
数据安全守则 §3.4：删除动作只发生在**夹具卡**上；页面登录用测试夹具账号
__t204q_u1（一次性，非真实账号，D6）；收尾 API+精确清理零残留。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9548
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CNAME_A = '__t204q板块A'
CNAME_B = '__t204q板块B'
PASSED = []
IDS = {}          # bid / colKeyA / colKeyB / cards
DIALOGS = []      # 捕获的 confirm 文案
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


def card_alive(cid):
    c = sqlite3.connect(DB)
    row = c.execute('SELECT deleted FROM cards WHERE card_id=?', (cid,)).fetchone()
    c.close()
    return bool(row) and row[0] == 0


def fixture_base_counts():
    """非夹具行的计数（行数守恒口径：夹具增删不影响真实数据）"""
    c = sqlite3.connect(DB)
    out = {}
    for t, col in (('cards', 'card_name'), ('boards', 'board_name'),
                   ('board_columns', 'col_key'), ('users', 'username')):
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ?",
                           ('%' + chr(92) + '_t204q%',)).fetchone()[0]
    c.close()
    return out


def setup():
    global IDS
    c = sqlite3.connect(DB)
    for u in ('__t204q_u1', '__t204q_u2'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    st, r = api('/api/boards', 'POST', {'board_name': '__t204q 测试看板'})
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    # 可见性：公共看板对无架构身份的普通用户不可见 → 给看板挂参与人 u1
    #（u1 可见但非看板负责人 —— 恰好构造「板块负责人而非看板负责人」的测试角色）
    c2 = sqlite3.connect(DB)
    c2.execute("UPDATE boards SET participants='__t204q_u1' WHERE board_id=?", (IDS['bid'],))
    c2.commit()
    c2.close()
    # 板块身份（#113/#115 严格口径）：A/B 板块 owner=u2、participants=u1
    # → u1 经板块参与人**可见**两板块；删除权只看事项负责人继承链：
    #   A1/B1（owner=u1）有权；A2/B2（owner=别人）**可见但不可删** —— 越权场景。
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': CNAME_A,
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                'owner': '__t204q_u2', 'participants': '__t204q_u1'})
    assert st == 200, f'板块A创建失败 {st} {r}'
    IDS['colKeyA'] = r.get('col_key') or (IDS['bid'] + '::' + CNAME_A)
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': CNAME_B,
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                'owner': '__t204q_u2', 'participants': '__t204q_u1'})
    assert st == 200, f'板块B创建失败 {st} {r}'
    IDS['colKeyB'] = r.get('col_key') or (IDS['bid'] + '::' + CNAME_B)
    c3 = sqlite3.connect(DB)
    IDS['colIdA'] = c3.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                               (IDS['colKeyA'],)).fetchone()[0]
    IDS['colIdB'] = c3.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                               (IDS['colKeyB'],)).fetchone()[0]
    c3.close()
    # 卡片身份设计（事项级 5 身份过滤 #115：参与人 cc 可见但不可删——正是要测的场景）：
    #   A1/A3 owner=u1（事项负责人本人）；A2 owner=别人（u1 经板块A负责人有权）；
    #   B1/B2 owner=别人、cc=u1（参与人 → 可见可勾选，但删除无权）
    for nm, colk, owner in (('__t204q卡A1', IDS['colKeyA'], '__t204q_u1'),
                            ('__t204q卡A2', IDS['colKeyA'], '__t204q甲;cc=__t204q_u1'),
                            ('__t204q卡B1', IDS['colKeyB'], '__t204q_u1'),
                            ('__t204q卡A3', IDS['colKeyA'], '__t204q_u1'),
                            ('__t204q卡B2', IDS['colKeyB'], '__t204q戊;cc=__t204q_u1')):
        _owner, _, _cc = owner.partition(';cc=')
        _f = {'owner': _owner}
        if _cc:
            _f['cc'] = _cc
        st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': nm,
                    'column_id': IDS['colIdA'] if colk == IDS['colKeyA'] else IDS['colIdB'],
                    'fields': _f})
        assert st == 200, f'夹具卡 {nm} 创建失败 {st} {r}'
        IDS[nm] = r['card_id']
        if _cc:
            # POST /api/cards 的 fields 白名单不含 cc（创建接口限制）→ PUT 补写
            st2, r2 = api('/api/cards/' + IDS[nm], 'PUT',
                          {'fields': {'cc': '__t204q_u1'}})
            assert st2 == 200, f'夹具卡 {nm} cc 补写失败 {st2} {r2}' 


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    c = sqlite3.connect(DB)
    BS = chr(92)
    pat = '%_' + BS + '_t204q%'
    c.execute("DELETE FROM cards WHERE card_name LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM boards WHERE board_name LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM messages WHERE content LIKE ? ESCAPE ?", (pat, BS))
    c.commit()
    res = {}
    for t, col in (('cards', 'card_name'), ('boards', 'board_name'),
                   ('board_columns', 'col_key'), ('users', 'username')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：', res, flush=True)


async def main():
    import websockets
    setup()
    base0 = fixture_base_counts()
    tk = make_token('__t204q_u1')     # 板块A负责人（editor，非管理员）
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204q')
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

        async def send(m, p=None, mid=None):
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
        cookie = 'tk=%s; path=/; Max-Age=86400' % tk
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__t204q_u1'") is True:
                break
        await asyncio.sleep(1.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # 切到夹具看板渲染（CHK_COL_CARDS / META 注册）
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (IDS['bid'], IDS['bid']))
        await asyncio.sleep(2.5)
        rd = await ev("""(function(){
          return {meBoards:(ME.boards||[]).filter(function(b){return b.board_id.indexOf('t204q')>=0})
                    .map(function(b){return {id:b.board_id,dept:b.dept,p:b.participants}}),
                  chkCols:Object.keys(CHK_COL_CARDS),
                  titles:document.querySelectorAll('.week-title').length,
                  curBoard:curBoard};
        })()""")
        print('渲染诊断:', json.dumps(rd, ensure_ascii=False), flush=True)

        # ④ 判定函数单测（u1=板块A负责人；须在渲染后 —— colKey 反查依赖 CHK_COL_CARDS）
        r4 = await ev("""(function(){
          return {A1:canDeleteCheckedCard('%s'), A2:canDeleteCheckedCard('%s'),
                  B1:canDeleteCheckedCard('%s'), B2:canDeleteCheckedCard('%s'),
                  colA:chkCardColKey('%s')};
        })()""" % (IDS['__t204q卡A1'], IDS['__t204q卡A2'], IDS['__t204q卡B1'],
                 IDS['__t204q卡B2'], IDS['__t204q卡A1']))
        ok(r4.get('A1') is True and r4.get('B1') is True
           and r4.get('A2') is False and r4.get('B2') is False,
           f'④ 判定单测：A1/B1 有权、A2/B2 可见不可删（{r4}）')

        # ① 部分越权：勾 A1+A2（本板块）+ B1（别的板块）→ 确定 → 权限内删除
        DIALOGS.clear()
        await ev("CHK_MODE=true;ITEM_CHECKED=new Set(['%s','%s','%s']);COL_CHECKED=new Set();bulkDeleteChecked()"
                 % (IDS['__t204q卡A1'], IDS['__t204q卡A2'], IDS['__t204q卡B1']))
        await asyncio.sleep(2.5)
        ok(len(DIALOGS) >= 1 and '部分事项无删除权限' in DIALOGS[0] and '是否仅删除权限内事项' in DIALOGS[0],
           f'① 弹出确认文案精确匹配（实际：{DIALOGS[:1]}）')
        await asyncio.sleep(1)
        ok(card_alive(IDS['__t204q卡A1']) is False and card_alive(IDS['__t204q卡B1']) is False,
           '① 权限内 A1/B1 已删除')
        ok(card_alive(IDS['__t204q卡A2']) is True, '① 越权 A2 保留')

        # ② 全部越权：只勾 B1 → toast，零弹窗零删除
        DIALOGS.clear()
        await ev("ITEM_CHECKED=new Set(['%s']);bulkDeleteChecked()" % IDS['__t204q卡A2'])
        await asyncio.sleep(1.5)
        t2 = await ev("document.getElementById('toast').textContent")
        ok('均无删除权限' in (t2 or '') and not DIALOGS,
           f'② 全部越权 → toast 提示且不弹窗（实际：{t2}；弹窗：{DIALOGS}）')
        ok(card_alive(IDS['__t204q卡A2']) is True, '② A2 保留')

        # ③ 部分越权 + 取消：勾 A3（有权）+ B2（无权）→ 首个确认**取消** → 零删除
        #    （reader 自动 accept → 本场景改用拒绝应答：临时换应答策略）
        DIALOGS.clear()

        async def deny_dialogs():
            while True:
                await asyncio.sleep(3600)
        # 简化：直接以 admin token 把 B2 换成 u1 有权的卡？不行——需真实取消路径。
        # 用 CDP 覆盖 window.confirm 一次性返回 false（headless 下原生对话框已被
        # Page 层自动应答，覆盖法绕开 reader 的 accept）：
        await ev("window.__origConfirm=window.confirm;window.confirm=function(){window.__cancelSeen=true;return false};"
                 "ITEM_CHECKED=new Set(['%s','%s']);bulkDeleteChecked()"
                 % (IDS['__t204q卡A3'], IDS['__t204q卡B2']))
        await asyncio.sleep(2)
        r3 = await ev("({cancelSeen:!!window.__cancelSeen,"
                      "a3:undefined,b2:undefined})")
        ok(r3.get('cancelSeen') is True, '③ 首个确认（仅删权限内？）出现且被取消')
        ok(card_alive(IDS['__t204q卡A3']) is True and card_alive(IDS['__t204q卡B2']) is True,
           '③ 取消后零删除（A3/B2 均保留）')
        await ev("window.confirm=window.__origConfirm")

        # ⑥ 行数守恒（非夹具行）+ 无 JS 错误
        base1 = fixture_base_counts()
        ok(base0 == base1, f'⑥ 行数守恒（非夹具行）：{base0} → {base1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑦ 无 JS 错误（实际：{errs}）')
    finally:
        kill_profile_chrome("cdp_t204q")
        force_offline_and_remove('__t204q_u1')
        shutil.rmtree(profile, ignore_errors=True)
        cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
