# -*- coding: utf-8 -*-
"""T-205q 选人层级口径修订实测：
① 事项筛选树候选 = 板块配置名单（非看板 ACL 全量/架构池）
② colPickPool = 看板 ACL ∪ 协同部门成员（DOM 注入零写库）
③ 后端 _column_allowed_accounts = 看板 ACL ∪ 协同部门、_card_allowed_accounts = 板块名单（临时夹具+恢复）"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.error, urllib.parse

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

_okN = _failN = 0
def ok(cond, msg):
    global _okN, _failN
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if cond: _okN += 1
    else: _failN += 1

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + make_token('admin'))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=25, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

BOARD = '1162069797001000238'   # 财务中心/综合工作事项（中心级，看板 ACL=71 人）

async def main():
    import websockets
    tk = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205q')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                      '--headless=new', '--disable-gpu', '--no-first-run',
                      '--window-size=1400,900', '--remote-debugging-port=9631',
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9631/json/version', timeout=2); break
        except Exception: time.sleep(0.5)
    w = None
    col_key = None; col_id = None
    try:
        # ── API 夹具：238 上建一个只配「王伟娜」的板块（wwn ∈ 看板 ACL，写入放行）──
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t205q_单员板块',
                                            'nature': '日常', 'year': '2026', 'created_at': '2026-11-18'})
        assert st in (200, 201), d
        col_key = d.get('col_key'); col_id = d.get('column_id')
        st2, d2 = api('/api/columns/' + urllib.parse.quote(col_key, safe='') + '/participants',
                      'PUT', {'participants': 'wwn'})
        assert st2 in (200, 201), d2
        print('夹具板块已建（参与人=wwn 王伟娜）', flush=True)

        # ── ③ 后端口径（python 直调，临时夹具改 238 的 collab_depts 再恢复）──
        from app.app import _column_allowed_accounts, _card_allowed_accounts, _board_allowed_accounts, _collab_dept_accounts, _board_dept_pool_accounts
        db = sqlite3.connect('src/app.db')
        orig = db.execute("SELECT collab_depts FROM board_config WHERE board_id=?", (BOARD,)).fetchone()[0]
        try:
            # 夹具：中心级看板 238 临时协同部门=核算部 → 板块层池 = ACL ∪ 核算部成员
            nid = db.execute("SELECT id FROM org_nodes WHERE name='核算部' AND node_type='dept' LIMIT 1").fetchone()
            db.execute("UPDATE board_config SET collab_depts=? WHERE board_id=?", (str(nid[0]), BOARD))
            db.commit()
            collab = _collab_dept_accounts(BOARD)
            _collab_accs = set(collab)
            ok(len(collab) > 10, "③ 协同部门成员解析（核算部 %d 人）" % len(collab))
            col_pool = _column_allowed_accounts(BOARD, 'editor')
            ok('wwn' in col_pool and collab.issubset(col_pool),
               "③ 板块层池 = 看板 ACL ∪ 协同部门（%d 人，含 wwn+核算部成员）" % len(col_pool))
        finally:
            db.execute("UPDATE board_config SET collab_depts=? WHERE board_id=?", (orig, BOARD))
            db.commit()
        # 夹具 2：部门级看板 243（归属核算部）临时协同部门=资金部 → 看板层池 = 核算部池 ∪ 资金部成员
        BID2 = '1162069797001000243'
        orig2 = db.execute("SELECT collab_depts FROM board_config WHERE board_id=?", (BID2,)).fetchone()[0]
        try:
            nid2 = db.execute("SELECT id FROM org_nodes WHERE name='资金部' AND node_type='dept' LIMIT 1").fetchone()
            db.execute("UPDATE board_config SET collab_depts=? WHERE board_id=?", (str(nid2[0]), BID2))
            db.commit()
            dept_pool = _board_dept_pool_accounts(BID2)
            b_pool = _board_allowed_accounts(BID2)
            ok(b_pool is not None and 'zl' in b_pool and b_pool.issuperset(dept_pool) and (b_pool - dept_pool),
               "③ 看板层池 = 归属部门池 ∪ 协同部门（核算部 %d 人 ∪ 资金部成员，卓莉 zl 入池）" % len(dept_pool))
        finally:
            db.execute("UPDATE board_config SET collab_depts=? WHERE board_id=?", (orig2, BID2))
            db.commit(); db.close()
        # 事项层池 = 板块名单（移除架构交集）：夹具板块只配 wwn → 池={wwn}
        card_pool = _card_allowed_accounts(BOARD, col_id, 'editor', column_name='__t205q_单员板块')
        ok(card_pool == {'wwn'},
           "③ 事项层池 = 板块所配名单（%s = {wwn}，不再被看板 ACL/架构池放大）" % card_pool)

        # ── CDP：① 事项筛选候选 = 板块名单 ──
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9631/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50*1024*1024)
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
            return (await asyncio.wait_for(f, timeout=40)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
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
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)
        # ① 事项筛选候选池 = 各板块配置人员并集（此时含夹具板块 wwn + 既有 71 人板块）
        #    断言：候选 ⊆ 看板下板块配置名单（不出现板块未配置的人员）
        r1 = await ev("""(async function(){
          await bcLoadAclMembers();
          const pool=await boardFilterCandidates();
          // 页面侧重算板块配置名单（与实现同一数据源，交叉验证）
          const d=await api('/api/boards/1162069797001000238/columns');
          const cfg=new Set();
          ((d||{}).columns||[]).forEach(function(meta){
            if(meta.owner)cfg.add(meta.owner);
            (meta.participants||'').split(',').forEach(function(a){if(a)cfg.add(a);});
          });
          const acc2label={};
          const depAcc=new Set(BC_ACL_MEMBERS.filter(function(x){return x.status==='departed';}).map(function(x){return x.account;}));
          BC_ACL_MEMBERS.forEach(function(m){acc2label[m.account]=m.label;});
          const expect=[...cfg].filter(function(a){return !depAcc.has(a);}).map(function(a){return acc2label[a]||a;});
          const extra=pool.filter(function(x){return expect.indexOf(x)<0;});
          return {poolN:pool.length, cfgN:expect.length, extraN:extra.length,
                  extra:extra.slice(0,5), hasWwn:pool.some(function(x){return x.indexOf('王伟娜')>=0;})};
        })()""", aw=True)
        ok(r1 and r1.get('poolN') == r1.get('cfgN') and r1.get('extraN') == 0,
           "① 事项筛选候选 = 板块配置名单并集（池 %s 项 = 板块配置 %s 项，板块外 0 人）"
           % (r1.get('poolN'), r1.get('cfgN')))
        ok(r1 and r1.get('hasWwn'), "①-bis 夹具板块配置的「王伟娜」进入筛选候选")

        # ── ② colPickPool = 看板 ACL ∪ 协同部门（DOM 注入假看板条目，零写库）──
        r2 = await ev("""(function(){
          const fake={board_id:'__t205q_fake__',board_name:'__夹具__',owner:'glh',participants:'',
                      dept:'财务中心',collab_depts:['核算部']};
          ME.boards.push(fake);
          let pool=[];
          try{ pool=colPickPool('__t205q_fake__'); }catch(e){ return {err:String(e)}; }
          ME.boards.splice(ME.boards.indexOf(fake),1);   // 还原
          return {poolN:pool.length, pool:pool.slice(0,6)};
        })()""")
        _expect = ({'glh'} | _collab_accs) - {'tyl'}   # tyl 离岗（账号层剔除）
        ok(r2 and not r2.get('err') and (r2.get('poolN') or 0) == len(_expect),
           "② 板块选人池 = 看板 ACL ∪ 协同部门（池 %s 项 = glh+核算部 %d 人；看板 ACL 仅 glh）"
           % (r2.get('poolN'), len(_collab_accs)))
    finally:
        try:
            if col_key: api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception: pass
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205q')
        shutil.rmtree(profile, ignore_errors=True)

    print('---- 结果: %d PASS / %d FAIL ----' % (_okN, _failN), flush=True)

asyncio.run(main())
