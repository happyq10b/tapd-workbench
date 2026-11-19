# -*- coding: utf-8 -*-
"""T-0188 CDP 测试：倒计时列 + 板块浏览界面（待办/评论模块）。
① 目录【倒计时】列：事项行/板块行按 due 自动计算（未来/今天/逾期红色）；
② 板块浏览弹窗：无「板块事项」、元信息含截止/倒计时、待办增删勾、评论发表。
"""
import asyncio, base64, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8100'
PORT = 9521
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = ROOT + '/src/app.db'
P = '__cdv_'
BID, COLKEY = P + 'bid', P + 'bid::' + P + '板块'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


def today(offset):
    t = time.localtime(time.time() + offset * 86400)
    return '%04d-%02d-%02d' % (t.tm_year, t.tm_mon, t.tm_mday)


def make_fixtures():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT OR IGNORE INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', ''))
    c.execute("INSERT OR IGNORE INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,year,completion,description,due_date)"
              " VALUES(?,?,?,?,?,?,?,?,'open','板块描述文本',?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026', today(10)))
    # 事项：未来 3 天 / 逾期 1 天 / 无截止
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,week_no,created,deleted,parent_id,due)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (P + 'c1', BID, P + '看板', P + 'cid', P + '板块', P + '事项甲', 'open', '张三', '', '', '2026-11-12 10:00:00', 0, '', today(3)))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,week_no,created,deleted,parent_id,due)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (P + 'c2', BID, P + '看板', P + 'cid', P + '板块', P + '事项乙', 'open', '李四', '', '', '2026-11-12 10:00:00', 0, '', today(-1)))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,owner,cc,week_no,created,deleted,parent_id,due)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (P + 'c3', BID, P + '看板', P + 'cid', P + '板块', P + '事项丙', 'open', '王五', '', '', '2026-11-12 10:00:00', 0, '', ''))
    c.commit()
    c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("DELETE FROM column_comments WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM column_todos WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM cards WHERE card_id LIKE ? OR board_id LIKE ?", (P + '%', P + '%'))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ?", (P + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (P + '%',))
    c.commit()
    c.close()


async def main():
    import websockets
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0188')
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
    tgts = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [x['webSocketDebuggerUrl'] for x in tgts if x.get('type') == 'page'][0]
    w = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
    pending = {}
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=90)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.get_event_loop().create_task(reader())

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev('document.cookie=%s;location.href="/";' % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)
    # 选定夹具看板并刷新
    await ev('curBoards=new Set([%s]);curBoard=%s;reload(1)' % (json.dumps(BID), json.dumps(BID)))
    await asyncio.sleep(3.0)

    print('【① 目录【倒计时】列：事项行自动计算】', flush=True)
    r1 = await ev("""(function(){
      const rows=[...document.querySelectorAll('.item-card')];
      const out=[];
      rows.forEach(function(r){
        const t=r.querySelector('.item-title');
        const cd=r.querySelector('.fcol-cd');
        if(t&&cd)out.push({name:t.textContent.trim().slice(0,12),cd:cd.textContent.trim(),
          over:cd.className.indexOf('fcol-cd-over')>=0});
      });
      return out;})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    m = {x['name']: x for x in (r1 or [])} if isinstance(r1, list) else {}
    ok(m.get((P + '事项甲'), {}).get('cd', '').find('3') >= 0 and m.get((P + '事项甲'), {}).get('cd', '').find('天') < 0,
       '未来截止（+3 天）→ 倒计时「3」（T-0190：只显示数字）')
    ok(m.get((P + '事项乙'), {}).get('cd', '').find('-1') >= 0 and m.get((P + '事项乙'), {}).get('over') is True,
       '逾期截止（-1 天）→「-1」（负数）且红色高亮')
    ok(m.get((P + '事项丙'), {}).get('cd', '').find('—') >= 0, '无截止 → 空占位「—」')

    print('【② 板块行截止/倒计时】', flush=True)
    r2 = await ev("""(function(){
      const wh=document.querySelector('.week-header');
      const due=wh?wh.querySelector('.fcol-due'):null;
      const cd=wh?wh.querySelector('.fcol-cd'):null;
      return {due:due?due.textContent.trim():null,cd:cd?cd.textContent.trim():null};})()""")
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and r2.get('due') == '截止 ' + today(10), '板块行显示截止日期（due_date）')
    ok(isinstance(r2, dict) and r2.get('cd') == '倒计时 10', '板块行倒计时自动计算（T-191h 回滚：恢复「倒计时」前缀）')

    print('【③ 板块浏览界面：待办 + 评论模块】', flush=True)
    title_sel = json.dumps('.week-title.edit[data-colkey="%s"]' % COLKEY)
    await ev('openColumnDetail(document.querySelector(%s))' % title_sel)
    r3 = {}
    for _ in range(20):
        await asyncio.sleep(0.5)
        r3 = await ev("""({cd:document.getElementById('columnDetailModal').style.display,
            meta:document.getElementById('cd_meta').textContent,
            hasCards:!!document.getElementById('cd_cards'),
            todoBox:!!document.getElementById('cd_todos'),
            cmtBox:!!document.getElementById('cd_comments'),
            addRow:!!document.getElementById('cd_todo_add_row'),
            todos:document.getElementById('cd_todos').textContent.trim().slice(0,30)})""")
        if isinstance(r3, dict) and r3.get('todoBox') and '加载中' not in str(r3.get('todos', '')):
            break
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('cd') == 'flex', '点标题 → 浏览弹窗打开')
    ok(isinstance(r3, dict) and not r3.get('hasCards'), '「板块事项」区块已移除')
    ok(isinstance(r3, dict) and r3.get('todoBox') and r3.get('cmtBox'), '待办与评论模块已就位')
    ok(isinstance(r3, dict) and r3.get('meta', '').find('截止日期') >= 0 and
       r3.get('meta', '').find(today(10)) >= 0 and r3.get('meta', '').find('倒计时') >= 0,
       '浏览元信息含截止日期与倒计时')
    ok(isinstance(r3, dict) and r3.get('addRow') is False, '浏览界面无待办添加行（T-0190：设置入口只在编辑弹窗）')

    print('【④ 待办增删勾（T-0190：设置入口在编辑弹窗，真实落库）】', flush=True)
    await ev("window.confirm=function(){return true}")   # headless 下放行删除确认
    await ev("openColumnEdit(document.querySelector(%s).dataset,true)" % title_sel)
    await asyncio.sleep(1.0)
    await ev("document.getElementById('c_todo_new').value='发布年报初稿'")
    await ev('colAddTodo()')
    rt = {}
    for _ in range(15):
        await asyncio.sleep(0.4)
        rt = await ev("({n:COL_TODOS.length,name:COL_TODOS.length?COL_TODOS[0].name:'',done:COL_TODOS.length?COL_TODOS[0].done:-1})")
        if isinstance(rt, dict) and rt.get('n') == 1:
            break
    print('  ', json.dumps(rt, ensure_ascii=True), flush=True)
    ok(isinstance(rt, dict) and rt.get('n') == 1 and rt.get('name') == '发布年报初稿', '编辑弹窗添加待办 → 列表 1 条')
    ok(isinstance(rt, dict) and rt.get('done') == 0, '初始未勾选')
    await ev("colToggleTodo(COL_TODOS[0].id,true)")
    rtk = {}
    for _ in range(15):
        await asyncio.sleep(0.4)
        rtk = await ev("({done:COL_TODOS.length?COL_TODOS[0].done:-1})")
        if isinstance(rtk, dict) and rtk.get('done') == 1:
            break
    ok(isinstance(rtk, dict) and rtk.get('done') == 1, '勾选待办 → 状态更新并落库')
    await ev("colDeleteTodo(COL_TODOS[0].id)")
    await asyncio.sleep(0.8)
    ok(await ev("COL_TODOS.length") == 0, '删除待办 → 清空')
    # 关闭编辑弹窗（不回浏览：直接复位标记后关闭）
    await ev("COLUMN_EDIT_FROM_DETAIL=false;closeModal('columnModal')")
    await asyncio.sleep(0.6)

    print('【⑤ 评论发表与展示】', flush=True)
    await ev("document.getElementById('cd_new_comment').value='这条板块需要本周内收尾'")
    await ev('cdAddComment()')
    rc = {}
    for _ in range(15):
        await asyncio.sleep(0.4)
        rc = await ev("({n:document.getElementById('cd_comments').querySelectorAll('.comment-item').length,"
                      "txt:document.getElementById('cd_comments').textContent})")
        if isinstance(rc, dict) and rc.get('n') == 1:
            break
    print('  ', json.dumps(rc, ensure_ascii=True), flush=True)
    ok(isinstance(rc, dict) and rc.get('n') == 1 and rc.get('txt', '').find('本周内收尾') >= 0,
       '发表评论 → 列表展示（含作者与时间）')
    # 服务端真值复核
    c = sqlite3.connect(DB)
    nc = c.execute("SELECT COUNT(*) FROM column_comments WHERE col_key=?", (COLKEY,)).fetchone()[0]
    nt = c.execute("SELECT COUNT(*) FROM column_todos WHERE col_key=?", (COLKEY,)).fetchone()[0]
    c.close()
    ok(nc == 1 and nt == 0, f'服务端落库复核（评论 {nc}/待办 {nt}）')
    await send('Browser.close')


make_fixtures()
try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    cleanup()
    print('⑤ 夹具残留自查（清理后）')
    c = sqlite3.connect(DB)
    n_res = 0
    for t, col in (('boards', 'board_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('column_comments', 'col_key'), ('column_todos', 'col_key')):
        n_res += c.execute("SELECT COUNT(*) FROM " + t + " WHERE " + col + " LIKE ? ESCAPE '\\'",
                           ('%' + P.replace('_', '\\_') + '%',)).fetchone()[0]
    c.close()
    ok(n_res == 0, f'夹具零残留（实际 {n_res}）')
fails = [m for c, m in N if not c]
print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
