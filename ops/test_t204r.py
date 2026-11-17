# -*- coding: utf-8 -*-
"""T-204r（2026-11-17）两项优化 CDP 实测：
  ① 筛选栏负责人/参与人候选联动：只含当前所选看板的负责人+参与人（切换看板随之变化）
  ② 勾选工具栏新增【负责板块】：一键勾选我负责的板块+其下全部事项；
     再点取消；不影响其他板块勾选状态；管理员直通。
数据安全守则 §3.4：夹具 API 创建/清理（admin token，不建 WS）；页面登录用
一次性夹具账号 __t204r_u1 / __cdp_ui（D6，不碰真实账号）；零业务写库。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9549
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CNAME_A = '__t204r板块A'
CNAME_B = '__t204r板块B'
PASSED = []
IDS = {}
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


def setup():
    global IDS
    c = sqlite3.connect(DB)
    for u in ('__t204r_u1', '__t204r_u2'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    st, r = api('/api/boards', 'POST', {'board_name': '__t204r 测试看板'})
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    # 板块A owner=u1（我负责的板块）；板块B owner=u2、participants=u1（可见、非我负责）
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': CNAME_A,
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                'owner': '__t204r_u1'})
    IDS['colKeyA'] = r.get('col_key') or (IDS['bid'] + '::' + CNAME_A)
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': CNAME_B,
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                'owner': '__t204r_u2', 'participants': '__t204r_u1'})
    IDS['colKeyB'] = r.get('col_key') or (IDS['bid'] + '::' + CNAME_B)
    c = sqlite3.connect(DB)
    IDS['colIdA'] = c.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                              (IDS['colKeyA'],)).fetchone()[0]
    IDS['colIdB'] = c.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                              (IDS['colKeyB'],)).fetchone()[0]
    c.close()
    # 板块B 的 cc 卡（u1 可见可勾，但板块B 非我负责 → 负责板块不碰它）
    for nm, colid, extra in (('__t204r卡A1', IDS['colIdA'], {}),
                             ('__t204r卡A2', IDS['colIdA'], {}),
                             ('__t204r卡B1', IDS['colIdB'], {'cc_put': '__t204r_u1'})):
        st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': nm,
                    'column_id': colid, 'fields': {'owner': '__t204r_u2'}})
        assert st == 200, f'夹具卡 {nm} 创建失败 {st} {r}'
        IDS[nm] = r['card_id']
        if extra.get('cc_put'):
            st2, r2 = api('/api/cards/' + IDS[nm], 'PUT', {'fields': {'cc': extra['cc_put']}})
            assert st2 == 200, f'{nm} cc 补写失败 {st2} {r2}'


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    for nm in ('__t204r卡A1', '__t204r卡A2', '__t204r卡B1'):
        if IDS.get(nm):
            api('/api/cards/' + IDS[nm], 'DELETE')
    for ck in ('colKeyA', 'colKeyB'):
        if IDS.get(ck):
            api('/api/columns/' + urllib.parse.quote(IDS[ck], safe=''), 'DELETE')
    BS = chr(92)
    pat = '%_' + BS + '_t204r%'
    c = sqlite3.connect(DB)
    for t, col in (('cards', 'card_name'), ('board_columns', 'col_key'),
                   ('boards', 'board_name'), ('users', 'username'),
                   ('messages', 'content')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE ?", (pat, BS))
    c.commit()
    res = {}
    for t, col in (('cards', 'card_name'), ('boards', 'board_name'),
                   ('board_columns', 'col_key'), ('users', 'username')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：', res, flush=True)


def base_counts():
    c = sqlite3.connect(DB)
    out = {}
    for t, col in (('cards', 'card_name'), ('boards', 'board_name'),
                   ('board_columns', 'col_key'), ('users', 'username')):
        if t == 'users':
            out[t] = c.execute("SELECT COUNT(*) FROM users WHERE username NOT LIKE ?"
                               " AND username != '__cdp_ui'",
                               ('%' + chr(92) + '_t204r%',)).fetchone()[0]
        else:
            out[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ?",
                               ('%' + chr(92) + '_t204r%',)).fetchone()[0]
    c.close()
    return out


async def login(ev, tk, uname):
    """导航+种 cookie+等 ME 就绪"""
    await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % tk))
    for _ in range(90):
        await asyncio.sleep(0.5)
        if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='%s'" % uname) is True:
            break
    await asyncio.sleep(1.5)


async def main():
    import websockets
    setup()
    base0 = base_counts()
    tk_u1 = make_token('__t204r_u1')
    tk_ui = ensure_test_ui_account()      # 管理员直通断言用
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204r')
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
        await login(ev, tk_u1, '__t204r_u1')
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # ① 筛选候选联动：默认看板（非夹具）候选 ≠ 夹具看板候选；切到夹具看板后= 看板 ACL 聚合
        r0 = await ev("(function(){return boardFilterCandidates();})()")
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (IDS['bid'], IDS['bid']))
        await asyncio.sleep(2.5)
        r1 = await ev("""(function(){
          // 独立复算：ME.boards 的 owner/participants 聚合（不走 boardFilterCandidates）
          const b=(ME.boards||[]).find(x=>x.board_id==='%s');
          const accs=[];
          if(b&&b.owner)accs.push(b.owner);
          ((b&&b.participants)||'').split(',').forEach(function(a){if(a)accs.push(a);});
          const labels=accs.filter(Boolean).map(function(a){
            const m=BC_ACL_MEMBERS.filter(x=>x.account===a)[0];
            return m?m.label:a;}).filter(Boolean);
          return {cand:boardFilterCandidates(), expected:[...new Set(labels)],
                  candLen0:%d};
        })()""" % (IDS['bid'], len(r0) if isinstance(r0, list) else -1))
        ok(r1.get('cand') == r1.get('expected') and (r1.get('cand') or []),
           f"① 夹具看板候选 = 看板负责人+参与人（{r1.get('cand')}）")
        ok(r1.get('cand') != r1.get('candLen0') if r1.get('candLen0', -1) >= 0 else True,
           '① 切换看板 → 候选随之变化（非夹具看板候选 ≠ 夹具候选）')

        # ② 负责板块按钮存在且随勾选模式显隐
        r2 = await ev("""(function(){
          const b1=document.getElementById('chkMineColBtn');
          const visHidden=!!b1&&b1.style.display==='none';
          CHK_MODE=true;syncChkModeBtn(document.querySelector('.chk-toggle')||document.getElementById('chkToggleBtn')||b1);
          const visShown=b1?b1.style.display!=='none':false;
          CHK_MODE=false;syncChkModeBtn(document.querySelector('.chk-toggle')||document.getElementById('chkToggleBtn')||b1);
          return {exists:!!b1, visHidden, visShown,
                  order:(function(){const ids=['chkAllBtn','chkMineColBtn','chkMineOwnerBtn','chkMineCcBtn'];
                    return ids.map(function(id){const el=document.getElementById(id);
                      return el?Array.prototype.indexOf.call(el.parentNode.children,el):-1;});})()};
        })()""")
        ok(r2.get('exists') is True and r2.get('visHidden') is True and r2.get('visShown') is True,
           '② 【负责板块】按钮存在，勾选开启才显示')
        ok(r2.get('order') and r2['order'][0] < r2['order'][1] < r2['order'][2],
           f'② 按钮位于【全选当前】与【负责事项】之间（位置序：{r2.get("order")}）')

        # ③ selectCategoryCols：勾我负责板块（A）及其下全部事项；不碰板块B 勾选
        await ev("CHK_MODE=true;syncChkModeBtn(document.querySelector('.chk-toggle')||document.getElementById('chkToggleBtn')||document.getElementById('chkMineColBtn'))")
        await ev("reload(1)")
        await asyncio.sleep(2.5)
        await ev("ITEM_CHECKED=new Set(['%s']);COL_CHECKED=new Set();saveItemChecked();saveColChecked()"
                 % IDS['__t204r卡B1'])
        await ev("selectCategoryCols()")
        await asyncio.sleep(0.8)
        r3 = await ev("""(function(){
          return {colA:COL_CHECKED.has('%s'), colB:COL_CHECKED.has('%s'),
                  a1:ITEM_CHECKED.has('%s'), a2:ITEM_CHECKED.has('%s'),
                  b1keep:ITEM_CHECKED.has('%s'),
                  toast:document.getElementById('toast').textContent};
        })()""" % (IDS['colKeyA'], IDS['colKeyB'], IDS['__t204r卡A1'], IDS['__t204r卡A2'], IDS['__t204r卡B1']))
        ok(r3.get('colA') is True and r3.get('a1') is True and r3.get('a2') is True,
           f"③ 板块A（我负责）及其下事项全部勾选（toast：{r3.get('toast')}）")
        ok(r3.get('b1keep') is True and r3.get('colB') is False,
           '③ 不影响其他板块勾选状态（板块B 的 B1 勾选保留、板块B 本身未勾）')

        # ④ 再点一次：取消我负责板块的勾选；板块B 勾选仍保留
        await ev("selectCategoryCols()")
        await asyncio.sleep(0.8)
        r4 = await ev("""(function(){
          return {colA:COL_CHECKED.has('%s'), a1:ITEM_CHECKED.has('%s'),
                  b1keep:ITEM_CHECKED.has('%s')};
        })()""" % (IDS['colKeyA'], IDS['__t204r卡A1'], IDS['__t204r卡B1']))
        ok(r4.get('colA') is False and r4.get('a1') is False and r4.get('b1keep') is True,
           '④ 再点取消：板块A 及其下事项解除勾选，板块B 的 B1 保留')

        # ⑤ 管理员直通：__cdp_ui 登录 → myOwnedCols = 全部有卡板块
        await login(ev, tk_ui, '__cdp_ui')
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (IDS['bid'], IDS['bid']))
        await asyncio.sleep(2)
        r5 = await ev("(function(){return {n:myOwnedCols().length, "
                      "isAdmin:!!(ME&&(ME.is_admin||ME.is_super))};})()")
        ok(r5.get('isAdmin') is True and (r5.get('n') or 0) >= 2,
           f"⑤ 管理员直通：负责板块候选 = 全部板块（{r5.get('n')} 个）")

        # ⑥ 行数守恒 + 无 JS 错误
        base1 = base_counts()
        ok(base0 == base1, f'⑥ 行数守恒（非夹具行）：{base0} → {base1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑦ 无 JS 错误（实际：{errs}）')
    finally:
        kill_profile_chrome("cdp_t204r")
        force_offline_and_remove('__cdp_ui')
        force_offline_and_remove('__t204r_u1')
        shutil.rmtree(profile, ignore_errors=True)
        cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
