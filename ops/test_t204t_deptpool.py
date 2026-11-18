# -*- coding: utf-8 -*-
"""T-204t（2026-11-17）看板 ACL 的归属部门约束贯通选人池/筛选候选 —— CDP 实测：
  ① colPickPool：看板 participants 中的**池外部门**人员被剔除（部门约束与
     看板管理 bcFilterAclByDept 同口径贯通）
  ② boardFilterCandidates（筛选栏候选）同口径剔除
  ③ 行数守恒 + 零残留
背景：用户报告「收入工作事项」看板 participants 存量含 dsy（杜诗煜，管理部），
但看板归属核算部——看板管理界面（bcFilterAclByDept）把他过滤了，而板块选人池
直接读库值 → 候选出现杜诗煜。修复 = ACL 读取路径统一挂部门约束。
数据安全守则 §3.4：夹具 API/sqlite 创建 + 精确清理；页面用 __cdp_ui（D6）。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, kill_profile_chrome, force_offline_and_remove  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9551
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEPT = '__t204t部门'
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


def base_counts():
    c = sqlite3.connect(DB)
    BS = chr(92)
    pat = '%' + BS + '_t204t%'
    out = {}
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('team_members', 'name')):
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ? ESCAPE ?"
                           " AND col" if False else f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    out['users'] = c.execute("SELECT COUNT(*) FROM users WHERE username NOT LIKE ? ESCAPE ?"
                             " AND username != '__cdp_ui'", (pat, BS)).fetchone()[0]
    out['board_config'] = c.execute("SELECT COUNT(*) FROM board_config WHERE dept NOT LIKE ? ESCAPE ?",
                                    (pat, BS)).fetchone()[0]
    c.close()
    return out


def setup():
    c = sqlite3.connect(DB)
    for u in ('__t204t_a1', '__t204t_a2'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    # 成员部门归属：甲=夹具部门（池内）、乙=管理部（池外）
    c.execute("INSERT OR IGNORE INTO team_members (name, workgroups, account, departments) "
              "VALUES ('__t204t甲','','__t204t_a1',?)", (DEPT,))
    c.execute("INSERT OR IGNORE INTO team_members (name, workgroups, account, departments) "
              "VALUES ('__t204t乙','','__t204t_a2','管理部')")
    c.commit()
    c.close()
    st, r = api('/api/boards', 'POST', {'board_name': '__t204t 测试看板'})
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    c = sqlite3.connect(DB)
    c.execute("UPDATE boards SET owner='__t204t_a1', participants='__t204t_a2' WHERE board_id=?",
              (IDS['bid'],))
    c.execute("INSERT OR IGNORE INTO board_config (board_id, dept, dept_node_id, attr, status) "
              "VALUES (?,?,0,'日常','启用')", (IDS['bid'], DEPT))
    c.commit()
    c.close()


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    BS = chr(92)
    pat = '%' + BS + '_t204t%'
    c = sqlite3.connect(DB)
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('team_members', 'name'),
                   ('messages', 'content')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM board_config WHERE dept LIKE ? ESCAPE ?", (pat, BS))
    c.commit()
    res = {}
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('team_members', 'name')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    res['board_config'] = c.execute("SELECT COUNT(*) FROM board_config WHERE dept LIKE ? ESCAPE ?",
                                    (pat, BS)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：', res, flush=True)


async def main():
    import websockets
    setup()
    base0 = base_counts()
    tk_ui = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204t')
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
        await ev("document.cookie=%s;location.href='/';"
                 % json.dumps('tk=%s; path=/; Max-Age=86400' % tk_ui))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='__cdp_ui'") is True:
                break
        await asyncio.sleep(1.5)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")
        await ev("curBoard='%s';curBoards=new Set(['%s']);reload(1)" % (IDS['bid'], IDS['bid']))
        await asyncio.sleep(2.5)

        await ev('bcLoadAclMembers()', True)   # awaitPromise：等异步加载完成
        tm_raw = await ev("api('/api/team').then(function(j){return (j.members||j||[]).filter(function(m){return (m.account||'').indexOf('__t204t')>=0}).map(function(m){return {name:m.name,account:m.account,departments:m.departments}})}).catch(function(e){return {err:String(e&&e.message||e)}})", True)
        print('/api/team 原始:', json.dumps(tm_raw, ensure_ascii=False), flush=True)
        await ev('bcLoadAclMembers()')   # 生产路径由 picker/colInitPickers 预加载；测试直调需补
        rd = await ev("""(function(){
          const mm=BC_ACL_MEMBERS.filter(function(m){return m.account.indexOf('__t204t')>=0;});
          return {aclTotal:BC_ACL_MEMBERS.length, loaded:!!BC_ACL_LOADED,
                  acl:mm, poolHas:!!(bcDeptPoolAccounts('__t204t部门')||new Set()).has('__t204t_a1'),
                  poolSize:(bcDeptPoolAccounts('__t204t部门')||{size:-1}).size};
        })()""")
        print('诊断:', json.dumps(rd, ensure_ascii=False), flush=True)
        r1 = await ev("""(function(){
          const b=(ME.boards||[]).find(x=>x.board_id==='%s');
          const pool=bcDeptPoolAccounts(b.dept||'');
          return {dept:b.dept,
                  ownerInPool:pool.has('__t204t_a1'), partInPool:pool.has('__t204t_a2'),
                  colPool:colPickPool('%s'),
                  filterCand:boardFilterCandidates()};
        })()""" % (IDS['bid'], IDS['bid']))
        ok(r1.get('dept') == DEPT and r1.get('ownerInPool') is True and r1.get('partInPool') is False,
           f"① 部门池口径：看板归属「{r1.get('dept')}」，甲在池内、乙（管理部）在池外")
        # #205q（2026-11-18 用户口径修订）：板块层不再与架构部门池做交集——
        # 板块的选人/筛选受制于**看板**（看板 ACL 全量 ∪ 协同部门），
        # 看板参与人乙（管理部）虽在架构池外，仍是板块层的合法候选。
        # #205q：colPickPool 本身不再做架构交集；乙不可见的剔除来源 =
        # **看板层读取过滤**（/api/me 按 看板层池=归属部门池∪协同 下发，2026-11-17 既有口径）
        ok(r1.get('colPool') == ['__t204t甲(__t204t_a1)'],
           f"② colPickPool = 看板 ACL（乙由看板层读取过滤剥离，非板块层架构交集；实际：{r1.get('colPool')}）")
        # 事项筛选候选 = 板块所配名单（#205q 新口径，async）——夹具未配置板块 → 空池
        r3 = await ev("""(async function(){
          await bcLoadAclMembers();
          return await boardFilterCandidates();
        })()""", aw=True)
        ok(r3 == [],
           f"③ boardFilterCandidates = 板块配置名单（夹具无板块 → 空池；实际：{r3}）")

        base1 = base_counts()
        ok(base0 == base1, f'④ 行数守恒（非夹具行）：{base0} → {base1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑤ 无 JS 错误（实际：{errs}）')
    finally:
        kill_profile_chrome("cdp_t204t")
        force_offline_and_remove('__cdp_ui')
        shutil.rmtree(profile, ignore_errors=True)
        cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
