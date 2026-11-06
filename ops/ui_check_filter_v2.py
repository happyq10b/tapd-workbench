# -*- coding: utf-8 -*-
"""#53 筛选器改进 UI 实测：人员树清空/确认bug / 周数格式+全选清空 / 按钮行调整"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9539
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__fs_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-04 12:00:00'
    # 清旧夹具
    c.execute("DELETE FROM users WHERE username LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM team_members WHERE account LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM board_columns WHERE board_id LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM board_config WHERE board_id LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM boards WHERE board_id LIKE '" + PREFIX + "%'")
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,?,?,?)",
              (PREFIX + '成员', '', PREFIX + 'u1', now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
              (PREFIX + 'u1', 'x', 'admin', '*', '*', now))
    bid = PREFIX + 'B1'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,'FS看板','',?,0,?)", (bid, PREFIX + 'u1', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,'日常','2026',0,'','')",
              (bid + '::C1', PREFIX + 'c1', bid, 'C1', now, 'x'))
    c.commit(); c.close()
    return bid

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM users WHERE username LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM team_members WHERE account LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM board_columns WHERE board_id LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM board_config WHERE board_id LIKE '" + PREFIX + "%'")
    c.execute("DELETE FROM boards WHERE board_id LIKE '" + PREFIX + "%'")
    c.commit(); c.close()

async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_fs%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0
            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value=%s;document.getElementById('btn').click();" % json.dumps(PWD))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            # 选中夹具看板（若在列表中）——直接调 pickBoard
            await ev("(function(){var b=(typeof BC_BOARDS!=='undefined'&&BC_BOARDS[0])?BC_BOARDS[0].board_id:(typeof BOARDS!=='undefined'&&BOARDS[0]?BOARDS[0].board_id:null);if(b){curBoards=new Set([b]);curBoard=b;}return curBoard})()")
            await asyncio.sleep(2)

            # ── 需求3：按钮行 ──
            print('\n【需求3】按钮行')
            r = await ev("""(function(){
              // 2026-11-06 #83：按钮行移到筛选明细行（filterHint 的父容器）右端
              var bar=document.getElementById('filterHint').parentElement;
              var btns=[].slice.call(bar.querySelectorAll(':scope > button, :scope > .slot-ops > button')).map(function(b){return b.textContent.trim()});
              return {order:btns};
            })()""")
            order = r.get('order') or []
            # ⚠️ 2026-11-04 #56：展开/折叠/导入导出/新建板块 → 「操作 ▾」
            #    2026-11-06 #83：按钮行移到筛选明细行右端（容器从 .toolbar-right 改为明细行）
            ok(order == ['清空筛选', '操作 ▾'],
               '按钮顺序 = 清空筛选 + 操作 ▾（#83 明细行右端）：%s' % order)

            # ── 需求3：清空筛选一键清空 ──
            print('\n【需求3】清空筛选')
            # 先造一堆筛选状态
            await ev("""(function(){
              PERSON_SEL=new Set(['张三']);
              WEEK_SEL=new Set(['2026年第41周']);
              document.getElementById('searchInput').value='测试词';
              document.getElementById('createdStart').value='2026-01-01';
              return true;
            })()""")
            await ev("clearAllRowFilters()")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              return {q:document.getElementById('searchInput').value,
                      ds:document.getElementById('createdStart').value,
                      de:document.getElementById('createdEnd').value,
                      person:PERSON_SEL.size, week:WEEK_SEL.size};
            })()""")
            ok(r.get('q') == '' and r.get('ds') == '' and r.get('de') == '' and r.get('person') == 0 and r.get('week') == 0,
               '清空筛选一键重置 搜索/人员/周数/日期：%s' % r)

            # ── 需求2：周数面板 ──
            print('\n【需求2】周数筛选')
            await ev("openFilterCombo('week')")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              var d=document.getElementById('weekFilterDrop');
              var tip=d.querySelector('.cf-tip');
              return {tip:tip?tip.textContent.trim():'',
                      allBtn:!!d.querySelector('[data-week-all]'),
                      clearBtn:!!d.querySelector('[data-week-clear]'),
                      oldClearAll:!!d.querySelector('[data-clear-week]'),
                      opts:d.querySelectorAll('[data-pick-week]').length};
            })()""")
            ok('「2026-41」' in (r.get('tip') or ''), '提示文字含「2026-41」：%s' % r.get('tip'))
            ok('「41」后回车' not in (r.get('tip') or ''), '旧提示（可直接输入「41」）已移除')
            ok(r.get('allBtn') is True and r.get('clearBtn') is True, '【全选】【清空】按钮都在')
            ok(r.get('oldClearAll') is False, '底部旧「清空全部」选项已被按钮取代')
            n = r.get('opts') or 0
            # 全选
            await ev("(function(){var b=document.querySelector('#weekFilterDrop [data-week-all]');b.click();return true})()")
            await asyncio.sleep(1.5)
            r = await ev("WEEK_SEL.size")
            ok(r == n, '【全选】勾选全部 %s 个候选（实际选中 %s）' % (n, r))
            # 清空
            await ev("(function(){var b=document.querySelector('#weekFilterDrop [data-week-clear]');b.click();return true})()")
            await asyncio.sleep(1.5)
            r = await ev("WEEK_SEL.size")
            ok(r == 0, '【清空】清空全部已选（剩 %s）' % r)

            # 输入格式：纯数字 41 应被拒绝，2026-41 应成功
            await ev("openFilterCombo('week')")
            await asyncio.sleep(1)
            await ev("(function(){var i=document.getElementById('weekFilterInput');i.value='41';onFilterComboKey('week',{key:'Enter',preventDefault:function(){}});return true})()")
            await asyncio.sleep(1)
            r = await ev("(function(){var t=[].slice.call(document.querySelectorAll('.toast')).map(function(x){return x.textContent}).join('|');return {week:WEEK_SEL.size,toast:t}})()")
            ok(r.get('week') == 0 and '2026-41' in (r.get('toast') or ''),
               '纯数字「41」被拒绝且提示新格式：%s' % r)
            await ev("(function(){var i=document.getElementById('weekFilterInput');i.value='2026-41';onFilterComboKey('week',{key:'Enter',preventDefault:function(){}});return true})()")
            await asyncio.sleep(1.5)
            r = await ev("WEEK_SEL.has('2026年第41周')")
            ok(r is True, '「2026-41」回车成功选中 2026年第41周')
            await ev("clearFilterSel('week')")

            # ── 需求1：人员树清空按钮 + 全取消可确认 ──
            print('\n【需求1】人员筛选树')
            await ev("openPersonFilterPicker(document.getElementById('personFilterBtn')||document.querySelector('.cf-person'))")
            await asyncio.sleep(2)
            r = await ev("""(function(){
              var p=document.querySelector('.tree-pick');
              if(!p)return {found:false};
              return {found:true,clearBtn:!!p.querySelector('[onclick*=tpClearSelected]'),
                      count:(document.getElementById('tp_count')||{}).textContent};
            })()""")
            ok(r.get('found') is True, '人员树弹窗打开')
            ok(r.get('clearBtn') is True, '底栏有【清空】按钮')
            # 选两个人（用内部 API 模拟勾选）
            await ev("(function(){TREE_PICK.selected=[ORG_PERSON_PREFIX+'张三',ORG_PERSON_PREFIX+'李四'];paintAll();return true})()")
            await asyncio.sleep(0.5)
            r = await ev("(document.getElementById('tp_count')||{}).textContent")
            ok(r == '2', '模拟勾选 2 人（计数 %s）' % r)
            # 点清空
            await ev("(function(){document.querySelector('.tree-pick [onclick*=tpClearSelected]').click();return true})()")
            await asyncio.sleep(0.5)
            r = await ev("(function(){return {cnt:(document.getElementById('tp_count')||{}).textContent,sel:TREE_PICK.selected.length}})()")
            ok(r.get('cnt') == '0' and r.get('sel') == 0, '【清空】一键清空临时已选：%s' % r)
            # 全取消后确认 = 清空筛选（不再被 toast 拦截）
            await ev("(function(){PERSON_SEL=new Set(['张三']);TREE_PICK.selected=[];treePickConfirm();return true})()")
            await asyncio.sleep(1.5)
            r = await ev("(function(){var t=[].slice.call(document.querySelectorAll('.toast')).map(function(x){return x.textContent}).join('|');return {person:PERSON_SEL.size,toast:t}})()")
            ok(r.get('person') == 0, '全取消后点确定 → 筛选被清空（PERSON_SEL=%s）' % r.get('person'))
            ok('未选择人员' not in (r.get('toast') or ''), '不再误提示「未选择人员」：%s' % r.get('toast'))
    finally:
        cleanup()
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
