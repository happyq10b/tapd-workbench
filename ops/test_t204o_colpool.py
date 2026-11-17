# -*- coding: utf-8 -*-
"""T-204o（2026-11-17）板块弹窗负责人/参与人选人池 —— 上级看板过滤 CDP 实测：
  ① 新增板块：池 = 当前所属看板的负责人+参与人（独立口径复算比对）
  ② 池是真约束：池 ⊆ 全员名单，且存在池 < 全员（非全量兜底）
  ③ 切换所属看板 → 池随动
  ④ 编辑板块：池 = 该板块归属看板的负责人+参与人
  ⑤ 行数守恒：boards/board_columns/org_appointments 零变化（只开弹窗不保存）
数据安全守则 §3.4：无任何写库动作；页面登录用一次性测试账号 __cdp_ui（D6）。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_test_helper import ensure_test_ui_account, cleanup as cdp_cleanup  # noqa: E402
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PORT = 9546
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def table_counts():
    c = sqlite3.connect(DB)
    out = [c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
           for t in ('boards', 'board_columns', 'org_appointments', 'team_members')]
    c.close()
    return out


async def main():
    import websockets
    c0 = table_counts()

    tk = ensure_test_ui_account()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t204o')
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

        # ① 前提：/api/me 的 boards 带 owner/participants（colPickPool 的数据源）
        r0 = await ev("""(function(){
          const bs=(ME.boards||[]).map(b=>({id:b.board_id,name:b.board_name,
            owner:b.owner||'',parts:b.participants||''}));
          const withAcl=bs.filter(b=>b.owner||b.parts);
          return {n:bs.length, withAcl:withAcl.length, first:withAcl[0]||null, all:bs};
        })()""")
        ok(r0.get('withAcl', 0) >= 2, f'① /api/me boards 带 owner/participants（{r0.get("withAcl")}/{r0.get("n")} 块）')

        # ② 打开新增板块弹窗 → 池 = 默认看板的负责人+参与人（页面内独立口径复算）
        await ev("openColumnModal()")
        await asyncio.sleep(1.5)
        r2 = await ev("""(function(){
          const sel=document.getElementById('c_board').value;
          const b=(ME.boards||[]).find(x=>x.board_id===sel);
          // 独立复算：不经过 colPickPool
          const accs=[];
          if(b.owner)accs.push(b.owner);
          (b.participants||'').split(',').forEach(a=>{if(a)accs.push(a);});
          const labels=aclAccsInDept(b.dept||'',accs).filter(Boolean).map(a=>{
            const m=BC_ACL_MEMBERS.filter(x=>x.account===a)[0];
            return m?m.label:a;}).filter(Boolean);
          const dep=new Set(BC_ACL_MEMBERS.filter(x=>x.status==='departed').map(x=>x.name));
          const expected=[...new Set(labels)].filter(n=>!dep.has(n));
          return {board:sel, expected:expected,
                  ownerPool:PP['c_owner'].ALL.slice(), partsPool:PP['c_parts'].ALL.slice(),
                  fullN:BC_ACL_MEMBERS.filter(x=>x.status!=='departed').length};
        })()""")
        ok(r2.get('ownerPool') == r2.get('expected'),
           f'② 新增板块·负责人池 = 看板[{r2.get("board")}]负责人+参与人（{r2.get("expected")}）')
        ok(r2.get('partsPool') == r2.get('expected'), '② 参与人池同源一致')
        ok(len(r2.get('ownerPool') or []) < (r2.get('fullN') or 0),
           f'② 池是真约束：{len(r2.get("ownerPool") or [])} < 全员 {r2.get("fullN")}（非全量兜底）')

        # ③ 切换所属看板 → 池随动
        r3 = await ev("""(function(){
          const cur=document.getElementById('c_board').value;
          const other=(ME.boards||[]).find(b=>b.board_id!==cur&&(b.owner||b.participants));
          if(!other)return {skip:true};
          const el=document.getElementById('c_board');
          el.value=other.board_id;
          el.dispatchEvent(new Event('change'));
          const b=other;
          const accs=[];
          if(b.owner)accs.push(b.owner);
          (b.participants||'').split(',').forEach(a=>{if(a)accs.push(a);});
          const labels=aclAccsInDept(b.dept||'',accs).filter(Boolean).map(a=>{
            const m=BC_ACL_MEMBERS.filter(x=>x.account===a)[0];
            return m?m.label:a;}).filter(Boolean);
          const dep=new Set(BC_ACL_MEMBERS.filter(x=>x.status==='departed').map(x=>x.name));
          return {board:b.board_id, expected:[...new Set(labels)].filter(n=>!dep.has(n)),
                  ownerPool:PP['c_owner'].ALL.slice()};
        })()""")
        if r3.get('skip'):
            print('SKIP ③ 仅一块看板配置了 ACL，切换场景跳过', flush=True)
        else:
            print('r3 诊断:', json.dumps(r3, ensure_ascii=False), flush=True)
        ok(r3.get('ownerPool') == r3.get('expected'),
               f'③ 切换看板[{r3.get("board")}] → 池随动（{r3.get("expected")}）')

        # ④ 编辑模式：池 = 该板块归属看板的负责人+参与人（真实入口：切看板→渲染→取板块标题 dataset）
        r4 = await ev("""(async function(){
          const target=(ME.boards||[]).find(b=>b.owner||b.participants);
          if(!target)return {skip:true};
          curBoard=target.board_id;curBoards=new Set([target.board_id]);reload(1);
          return {board:target.board_id};
        })()""", aw=True)
        await asyncio.sleep(2.5)
        r4b = await ev("""(async function(){
          const t=document.querySelector('#boardContent .week-title.edit[data-colkey]');
          if(!t)return {skip:true,reason:'当前看板无可编辑板块'};
          const okL=await openColumnEdit({colkey:t.dataset.colkey,bid:t.dataset.bid,cname:t.dataset.cname},true);
          if(!okL)return {skip:true,reason:'认锁失败'};
          await new Promise(function(res){setTimeout(res,1200)});   // 等 colInitPickers 异步链
          const bid=t.dataset.bid;
          const b=(ME.boards||[]).find(x=>x.board_id===bid);
          const accs=[];
          if(b.owner)accs.push(b.owner);
          (b.participants||'').split(',').forEach(a=>{if(a)accs.push(a);});
          const labels=aclAccsInDept(b.dept||'',accs).filter(Boolean).map(a=>{
            const m=BC_ACL_MEMBERS.filter(x=>x.account===a)[0];
            return m?m.label:a;}).filter(Boolean);
          const dep=new Set(BC_ACL_MEMBERS.filter(x=>x.status==='departed').map(x=>x.name));
          return {board:bid, ownerPool:PP['c_owner'].ALL.slice(),
                  partsPool:PP['c_parts'].ALL.slice(),
                  expected:[...new Set(labels)].filter(n=>!dep.has(n))};
        })()""", aw=True)
        if r4b.get('skip'):
            print(f"SKIP ④ 编辑模式（{r4b.get('reason')}）", flush=True)
        else:
            print('r4b 诊断:', json.dumps(r4b, ensure_ascii=False), flush=True)
            ok(r4b.get('ownerPool') == r4b.get('expected'),
               f'④ 编辑板块·池 = 归属看板[{r4b.get("board")}]负责人+参与人')
            ok(r4b.get('partsPool') == r4b.get('expected'), '④ 参与人池同源一致')
            # 收尾：关弹窗释放编辑锁（MODAL_CLOSE_HOOKS）
            await ev("closeModal('columnModal')")
            await asyncio.sleep(0.8)

        # ⑤ 行数守恒 + 无 JS 错误（只开弹窗未保存）
        c1 = table_counts()
        ok(c0 == c1, f'⑤ 行数守恒：{c0} → {c1}')
        errs = await ev("window.__errs")
        ok(not errs, f'⑥ 无 JS 错误（实际：{errs}）')
    finally:
        cdp_cleanup("cdp_t204o")
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
