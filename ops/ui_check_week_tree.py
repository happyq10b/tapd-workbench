# -*- coding: utf-8 -*-
"""#46 UI 实测：① 周数下拉只含有事项的周（年份下推）；② 人员树弹窗删说明/搜索并排；
③ 默认展开「财务中心」。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9409
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__wk_'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    """造夹具：一个 2027 年的板块 + 挂一张 2027 年周的事项。
    若周数候选没按年份过滤，2026 视图下下拉里就会出现这个 2027 的周。"""
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 09:00:00'
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM cards WHERE board_id LIKE ?", (PREFIX + '%',))
    bid = PREFIX + 'B1'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,'周数验证看板','',?,0,?)", (bid, 'admin', now))
    # 板块：year=2027
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned) VALUES (?,?,?,?,?,'admin','日常','2027',0)",
              (bid + '::C1', PREFIX + 'C1', bid, 'C1', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,'财务中心',0,'日常','启用','',?)", (bid, now))
    # 事项：2027 年第 10 周（⚠️ week_no 必须显式写入，否则周数候选里根本不会出现）
    c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,creator,owner,created,modified,description,parent_id,deleted,week_no)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)""",
              (PREFIX + 'K1', bid, '周数验证看板', PREFIX + 'C1', 'C1', PREFIX + '事项', 'open', 'admin', '张三', now, now, '', '', '2027年第10周'))
    c.commit(); c.close()
    return bid

def cleanup(bid):
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id=?" % t, (bid,))
    c.commit(); c.close()

async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_wk%d' % PORT)
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
                    if msg.get('id') == mid: return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')
            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"): break
            await asyncio.sleep(2)

            # ── 需求①：周数下拉只含有事项的周 ──
            print('\n【需求1】周数候选按年份过滤')
            # 选中夹具看板（它只有 2027 年板块）→ 默认 2026 视图下，2027·第10周 不应出现
            await ev("(function(){var el=document.querySelector('.tb-board [data-bid], #tbBoards [data-bid]');"
                     "if(el)el.click();})()")
            await asyncio.sleep(1)
            # 直接调接口验证（更可控）：带 years=2026 → weeks 不含 2027 周；不带 → 含
            r1 = await ev("""(async function(){
              var tk=localStorage.getItem('tk')||'';
              var bid=%s;
              var q1=await fetch('/api/cards?board_id='+bid,{headers:{'Authorization':'Bearer '+tk}});
              var d1=await q1.json();
              var q2=await fetch('/api/cards?board_id='+bid+'&years=2026',{headers:{'Authorization':'Bearer '+tk}});
              var d2=await q2.json();
              var q3=await fetch('/api/cards?board_id='+bid+'&years=2027',{headers:{'Authorization':'Bearer '+tk}});
              var d3=await q3.json();
              return {noFilter:(d1.weeks||[]), y2026:(d2.weeks||[]), y2027:(d3.weeks||[]),
                      y2026total:d2.total, y2027total:d3.total};
            })()""" % json.dumps(fx), aw=True)
            ok('2027年第10周' in (r1.get('noFilter') or []), '不带 years：2027 年的周在候选里（基线）：%s' % r1.get('noFilter'))
            ok('2027年第10周' not in (r1.get('y2026') or []) and not (r1.get('y2026') or []),
               'years=2026：2027 年的周**不出现**（当前视图没有事项的周）：%s' % r1.get('y2026'))
            ok('2027年第10周' in (r1.get('y2027') or []), 'years=2027：该周出现（有事项的周保留）')
            ok(r1.get('y2026total') == 0 and r1.get('y2027total') == 1, 'total 同步过滤（2026→0，2027→1）')

            # ── 需求②③：人员树弹窗 ──
            print('\n【需求2/3】人员树弹窗：说明删除 / 搜索并排 / 财务中心默认展开')
            await ev("openPersonFilterPicker(document.getElementById('personFilterBox')||document.body);")
            await asyncio.sleep(1.5)
            r2 = await ev("""(function(){
              var panel=document.querySelector('.tree-pick');if(!panel)return {found:false};
              var tb=panel.querySelector('.tp-toolbar');
              var title=panel.querySelector('.tp-title');
              var search=panel.querySelector('#tp_search');
              var btns=[].slice.call(panel.querySelectorAll('.tp-tool-btn')).map(function(b){return b.textContent});
              var inToolbar=!!(tb&&tb.contains(search));
              // 同排判定：搜索框与按钮的垂直区间有重叠
              var sameRow=false;
              if(inToolbar){var sr=search.getBoundingClientRect(),br=tb.getBoundingClientRect();
                sameRow=sr.top>=br.top-2&&sr.bottom<=br.bottom+2;}
              // 财务中心是否展开：其节点行下存在可见的人员行（余河）
              var rows=[].slice.call(panel.querySelectorAll('.tp-node'));
              var fcVisible=rows.some(function(x){
                var lb=x.querySelector('.tp-label');
                return lb&&lb.textContent.trim()==='财务中心'&&x.offsetParent;});
              var memberVisible=rows.some(function(x){return x.textContent.indexOf('余河')>=0&&x.offsetParent});
              return {found:true,title:title?title.textContent:'',searchInToolbar:inToolbar,
                      sameRow:sameRow,btns:btns,fcVisible:fcVisible,memberVisible:memberVisible,
                      expandedIds:(typeof TREE_PICK!=='undefined')?[...TREE_PICK.expanded]:[]};
            })()""")
            ok(r2.get('found') is True, '树弹窗已打开')
            ok(r2.get('title', 'x') == '', '说明标题已删除（无 tp-title）：%r' % r2.get('title'))
            ok(r2.get('searchInToolbar') is True, '搜索框已进入工具栏（与展开/折叠并排）')
            ok(r2.get('sameRow') is True, '搜索框与展开/折叠按钮同排')
            ok((r2.get('btns') or []) == ['展开全部', '折叠全部'], '展开全部/折叠全部保留：%s' % r2.get('btns'))
            ok(r2.get('fcVisible') is True, '顶层「财务中心」节点可见')
            ok(r2.get('memberVisible') is True, '「财务中心」默认展开（其成员行可见，如 余河）')
            # 搜索框仍可用（IME 保护逻辑不因位置变化失效）
            await ev("var si=document.getElementById('tp_search');si.value='余';si.dispatchEvent(new Event('input',{bubbles:true}));")
            await asyncio.sleep(0.8)
            r3 = await ev("(function(){var b=document.getElementById('tp_body');return b?b.textContent.indexOf('余河')>=0:false})()")
            ok(r3 is True, '搜索框在工具栏位置仍能正常过滤')
            await ev("closeTreePick();")
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
