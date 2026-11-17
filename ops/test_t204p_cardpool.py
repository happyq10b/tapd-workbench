# -*- coding: utf-8 -*-
"""T-204p（2026-11-17）事项/子事项选人池层级收窄 —— CDP 实测：
  ① 主事项新建：池 = 所属板块的负责人+参与人（COLS_META 独立复算比对）
  ② 子事项新建：池 = 父事项的负责人+参与人（parentCardPool，非板块池）
  ③ 子事项编辑：池 = 父事项名单
  ④ poolViolation 守卫单测（新增必须⊆池、存量放行）
  ⑤ 端到端拒绝：子事项提交池外人员 → toast 拒绝 + 零创建
  ⑥ 行数守恒（夹具外零写库）
数据安全守则 §3.4：夹具经 API 创建（admin token，不建 WS）、API 清理 + 残留自查；
页面登录用一次性测试账号 __cdp_ui（D6）。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, cleanup as cdp_cleanup  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9547
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CNAME = '__t204p板块'
BID = ''        # setup 时由服务端生成
COL_KEY = ''
PARENT_NAME = '__t204p 父事项'
SUB_NAME = '__t204p 子事项'
PASSED = []
IDS = {}          # 夹具 id 登记（parent/sub card_id）
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
    global BID, COL_KEY
    st, r = api('/api/boards', 'POST', {'board_name': '__t204p 测试看板'})
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    BID = r.get('board_id') or (r.get('board') or {}).get('board_id') or ''
    assert BID, f'看板 ID 未返回：{r}'
    COL_KEY = BID + '::' + CNAME
    # 板块负责人/参与人必须是真实账号（后端校验 users 表）→ 夹具建三个账号
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    for u in ('__t204p_u1', '__t204p_u2', '__t204p_u3'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    st, r = api('/api/columns', 'POST', {
        'board_id': BID, 'column_name': CNAME, 'created_at': '2026-11-17',
        'nature': '日常', 'year': '2026',
        'owner': '__t204p_u1',
        'participants': '__t204p_u2,__t204p_u3'})
    assert st == 200, f'夹具板块创建失败 {st} {r}'
    st, r = api('/api/cards', 'POST', {'board_id': BID, 'card_name': PARENT_NAME,
                'fields': {'owner': '__t204p甲;__t204p乙', 'cc': '__t204p丙'}}, )
    assert st == 200, f'夹具父事项创建失败 {st} {r}'
    IDS['parent'] = r['card_id']
    st, r = api('/api/cards', 'POST', {'parent_id': IDS['parent'], 'board_id': '',
                'card_name': SUB_NAME, 'fields': {'owner': '__t204p甲'}}, )
    assert st == 200, f'夹具子事项创建失败 {st} {r}'
    IDS['sub'] = r['card_id']


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    for cid in ('sub', 'parent'):
        if IDS.get(cid):
            api('/api/cards/' + IDS[cid], 'DELETE')
    api('/api/columns/' + urllib.parse.quote(COL_KEY, safe=''), 'DELETE')
    # LIKE 通配纪律：`__t204p%` 前两个 _ 是通配符 → 必须用 chr(92) 构造转义（#122 教训）
    BS = chr(92)                       # 反斜杠
    pat_card = '_{}_t204p%'.format(BS)          # \_\_t204p%
    pat_user = '_{}_t204p_%'.format(BS)         # \_\_t204p\_%（尾 _ 也转义）
    esc = BS
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE card_id LIKE ? ESCAPE ? OR card_name LIKE ? ESCAPE ?",
              (pat_card, esc, pat_card, esc))
    c.execute("DELETE FROM board_columns WHERE col_key=?", (COL_KEY,))
    c.execute("DELETE FROM boards WHERE board_id=?", (BID,))
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE ?", (pat_user, esc))
    c.execute("DELETE FROM messages WHERE content LIKE ? ESCAPE ?", (pat_card, esc))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM cards WHERE card_id LIKE ? ESCAPE ?", (pat_card, esc)).fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ? ESCAPE ?", (pat_user, esc)).fetchone()[0]
    n3 = c.execute("SELECT COUNT(*) FROM boards WHERE board_id LIKE ? ESCAPE ?", (pat_card, esc)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：cards=%d users=%d boards=%d' % (n, n2, n3), flush=True)


def table_counts():
    c = sqlite3.connect(DB)
    out = [c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
           for t in ('boards', 'board_columns', 'cards', 'org_appointments', 'team_members')]
    c.close()
    return out


async def main():
    import websockets
    setup()
    c0 = table_counts()
    tk = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204p')
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
        cookie = 'tk=%s; path=/; Max-Age=86400' % tk
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'") is True:
                break
        await asyncio.sleep(1.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        # ① 主事项新建：切到夹具看板（COLS_META 随渲染更新）→ 池 = 板块负责人+参与人
        r1 = await ev("""(async function(){
          curBoard='%s';curBoards=new Set(['%s']);reload(1);
          return true;
        })()""" % (BID, BID), aw=True)
        await asyncio.sleep(2.5)
        await ev("openNewModal('%s','%s')" % (BID, COL_KEY))
        await asyncio.sleep(1.5)
        r1b = await ev("""(function(){
          const meta=(window.COLS_META||[]).find(x=>x.col_key==='%s');
          const accs=[];
          if(meta&&meta.owner)accs.push(meta.owner);
          ((meta&&meta.participants)||'').split(',').forEach(a=>{if(a)accs.push(a);});
          const dep=new Set(BC_ACL_MEMBERS.filter(x=>x.status==='departed').map(x=>x.name));
          const expected=accs.filter(Boolean).map(a=>{
            const m=BC_ACL_MEMBERS.filter(x=>x.account===a)[0];
            return m?m.label:a;}).filter(Boolean).filter(n=>!dep.has(n));
          return {expected:[...new Set(expected)], ownerPool:PP['n_owner'].ALL.slice(),
                  ccPool:PP['n_cc'].ALL.slice()};
        })()""" % COL_KEY)
        ok(r1b.get('ownerPool') == r1b.get('expected') and (r1b.get('expected') or []),
           f"① 主事项池 = 板块负责人+参与人（{r1b.get('expected')}）")
        ok(r1b.get('ccPool') == r1b.get('expected'), '① 参与人池同源一致')
        await ev("closeModal('newModal')")

        # ② 子事项新建：池 = 父事项的负责人+参与人
        await ev("openNewSubModal('%s')" % IDS['parent'])
        await asyncio.sleep(1.5)
        r2 = await ev("""(function(){
          return {ownerPool:PP['n_owner'].ALL.slice(), ccPool:PP['n_cc'].ALL.slice()};
        })()""")
        ok(r2.get('ownerPool') == ['__t204p甲', '__t204p乙', '__t204p丙'],
           f"② 子事项新建池 = 父事项名单（{r2.get('ownerPool')}）")
        ok(r2.get('ccPool') == ['__t204p甲', '__t204p乙', '__t204p丙'], '② 参与人池同源一致')
        await ev("closeModal('newModal')")

        # ③ 子事项编辑：池 = 父事项名单
        r3 = await ev("""(async function(){
          try{
            // 真实流程：子事项编辑从详情弹窗进入，携带 preloaded 卡片
            //（/api/cards 列表只含主事项，子事项必须用 card_id 精确取）
            const d=await api('/api/cards?card_id=%s');
            const sub=d.cards&&d.cards[0];
            if(!sub)return {err:'子事项取不到'};
            await openEdit('%s',sub);
            return {title:(document.getElementById('editTitle')||{}).textContent||'',
                    ownerPool:PP['e_owner']?PP['e_owner'].ALL.slice():null,
                    ccPool:PP['e_cc']?PP['e_cc'].ALL.slice():null};
          }catch(e){return {err:String(e&&e.message||e),
                    toast:(document.getElementById('toast')||{}).textContent||''}}
        })()""" % (IDS['sub'], IDS['sub']), aw=True)
        await asyncio.sleep(1)
        print('r3 诊断:', json.dumps(r3, ensure_ascii=False), flush=True)
        ok(r3.get('ownerPool') == ['__t204p甲', '__t204p乙', '__t204p丙'],
           f"③ 子事项编辑池 = 父事项名单（{r3.get('ownerPool')}）")
        ok(r3.get('ccPool') == ['__t204p甲', '__t204p乙', '__t204p丙'], '③ 参与人池同源一致')
        # 关编辑弹窗（解锁）
        await ev("closeEdit()")
        await asyncio.sleep(0.8)

        # ④ poolViolation 守卫单测
        r4 = await ev("""(function(){
          return {a:poolViolation(['池内'],['甲','池内'],[]),
                  b:poolViolation(['池外'],['甲'],[]),
                  c:poolViolation(['存量','新增'],['甲'],[/*存量*/'存量'])};
        })()""")
        ok(r4.get('a') == [] and r4.get('b') == ['池外'] and r4.get('c') == ['新增'],
           f'④ 守卫单测：池内放行/池外拒绝/存量放行（{r4}）')

        # ⑤ 端到端拒绝：子事项提交池外负责人 → toast 拒绝 + 零创建
        await ev("openNewSubModal('%s')" % IDS['parent'])
        await asyncio.sleep(1.5)
        await ev("document.getElementById('n_name').value='__t204p_拒绝测试';"
                 "NEW_CARD_OWNER=['__t204p局外人'];NEW_CARD_CC=[];")
        await ev("createCard()")
        await asyncio.sleep(1)
        t5 = await ev("document.getElementById('toast').textContent")
        c = sqlite3.connect(DB)
        created = c.execute("SELECT COUNT(*) FROM cards WHERE card_name='__t204p_拒绝测试'").fetchone()[0]
        c.close()
        ok('提交被拒绝' in (t5 or '') and '不在父事项' in (t5 or ''),
           f'⑤ 池外提交被拒绝且文案明确（实际：{t5}）')
        ok(created == 0, f'⑤ 零创建（拒绝路径无写库，cards 中拒绝测试卡={created}）')
        await ev("closeModal('newModal')")

        # ⑥ 行数守恒 + 无 JS 错误
        c1 = table_counts()
        ok(c0 == c1, f'⑥ 行数守恒：{c0} → {c1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑦ 无 JS 错误（实际：{errs}）')
    finally:
        cdp_cleanup("cdp_t204p")
        shutil.rmtree(profile, ignore_errors=True)
        cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
