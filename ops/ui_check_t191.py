# -*- coding: utf-8 -*-
"""T-191 UI CDP 测试（人员管理 + 到期筛选的前端行为验证）：
【人员管理】
 ① 「更多」菜单含【人员管理】入口（admin 可见）；
 ② 人员信息全字段表格渲染（表头 16 列、行数与搜索过滤）；
 ③ 头像小图直出、照片缩略图点击弹出大图预览（imgPreviewModal）；
 ④ 头像/照片管理页签：网格卡片 + 替换/清除按钮 + 快照/历史入口。
【到期筛选】
 ⑤ 板块筛选按钮行含【到期筛选】（位于「清空筛选」之后）；
 ⑥ 日历弹窗：月视图、本月天数、点击多选、切月保留已选、全选本月双态、清空、取消还原；
 ⑦ 热力图：到期事项多的日期底色更深（rgba alpha 递增）、带数量角标；
 ⑧ 确定后仅显示截止日期为所选日期的事项（真实落库夹具），筛选明细含「到期：」，按钮带计数徽标。
"""
import asyncio, datetime, json, os, shutil, sqlite3, subprocess, sys, time, urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9532
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
P = '__t191u_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'
U1 = P + 'u1'
TODAY = datetime.date.today()
TOMORROW = (TODAY + datetime.timedelta(days=2)).isoformat()
TOMORROW2 = (TODAY + datetime.timedelta(days=3)).isoformat()
PNG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
       'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)


def make_fixtures():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT OR IGNORE INTO users(username,password_hash,role,active_seq,avatar,photo) "
              "VALUES(?,?,?,1,?,?)", (U1, hash_pw('x'), 'editor', PNG, PNG))
    c.execute("INSERT OR IGNORE INTO team_members(name,account) VALUES(?,?)", (P + '姓名甲', U1))
    c.execute("INSERT INTO boards(board_id,board_name,owner,participants) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', ''))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,year,completion,pinned,owner) VALUES(?,?,?,?,?,?,?,?,'open',0,'')",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-12', 'admin', '日常', '2026'))
    for cid, name, due in ((P + 'c1', P + '事项甲', TOMORROW),
                           (P + 'c2', P + '事项乙', TOMORROW2),
                           (P + 'c3', P + '事项丙', TOMORROW)):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,"
                  "status,owner,cc,due,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,'')",
                  (cid, BID, P + '看板', P + 'cid', P + '板块', name, 'open', '', '', due,
                   '2026-11-12 10:00:00'))
    c.commit(); c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('users', 'username'), ('team_members', 'name'),
                   ('user_media_history', 'username')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit(); n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('team_members', 'name'), ('user_media_history', 'username')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0191')
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
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending = {}
    seq = [0]

    async def send(m, p=None):
        seq[0] += 1
        mid = seq[0]
        fut = asyncio.get_event_loop().create_future()
        pending[mid] = fut
        await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

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

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')

    bid_js = json.dumps(BID)
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % t0
    await ev('document.cookie=%s;location.href="/";' % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    # ---------- 人员管理 ----------
    print('【① 更多菜单含【人员管理】入口（admin 可见）】', flush=True)
    r1 = await ev("""(function(){
      const b=document.getElementById('staffBtn');
      if(!b)return {has:false};
      const menu=b.closest('.header-more-menu');
      return {has:true,disp:getComputedStyle(b).display!=='none',inMenu:!!menu,
        afterTeam:!!(b.previousElementSibling&&b.previousElementSibling.id==='teamBtn')};})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('has') and r1.get('disp') and r1.get('inMenu'),
       '「更多」菜单含【人员管理】且 admin 可见')

    print('【② 人员信息全字段表格】', flush=True)
    await ev("openStaffModal()")
    for _ in range(20):
        await asyncio.sleep(0.4)
        if await ev("document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length>0") is True:
            break
    r2 = await ev("""(function(){
      const ths=[...document.querySelectorAll('#staffTableWrap thead th')].map(x=>x.textContent.trim());
      const n=document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length;
      const si=document.getElementById('staffSearch');
      si.value=%s;renderStaffTable();
      const n2=document.querySelectorAll('#staffTableWrap .staff-table tbody tr').length;
      const row=document.querySelector('#staffTableWrap .staff-table tbody tr');
      const av=row.querySelector('img.staff-av');
      return {ths:ths,n:n,n2:n2,
        avOk:!!(av&&av.src.indexOf('/api/staff/img/')>=0),
        photoThumb:!!row.querySelector('img.staff-photo-thumb')};})()""" % json.dumps(P + '姓名甲'))
    print('  ', json.dumps(r2, ensure_ascii=True), flush=True)
    ok(isinstance(r2, dict) and len(r2.get('ths', [])) >= 15 and '头像' in r2['ths'][0]
       and '照片' in r2['ths'][1] and '政治面貌' in ''.join(r2['ths']),
       '表头覆盖全字段（头像/照片/姓名/…/政治面貌/手机…）')
    ok(isinstance(r2, dict) and r2.get('n', 0) >= 70, '表格渲染全部人员（%s 行）' % (r2 or {}).get('n'))
    ok(isinstance(r2, dict) and r2.get('n2') == 1, '按姓名搜索过滤 → 1 行（夹具人员）')
    ok(isinstance(r2, dict) and r2.get('avOk'), '头像列小图直出（/api/staff/img/…）')
    ok(isinstance(r2, dict) and r2.get('photoThumb'), '照片列缩略图可点')

    print('【③ 照片点击弹出大图预览】', flush=True)
    r3 = await ev("""(function(){
      const th=document.querySelector('#staffTableWrap img.staff-photo-thumb');
      th.click();
      const m=document.getElementById('imgPreviewModal');
      const img=document.getElementById('imgPreviewSrc');
      return {open:m.style.display==='flex',
        src:img.src.indexOf('/api/staff/img/')>=0,
        cap:document.getElementById('imgPreviewCap').textContent.indexOf('照片')>=0};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('open') and r3.get('src') and r3.get('cap'),
       '点击照片 → 大图预览弹窗打开且指向照片直出地址')
    await ev("closeModal('imgPreviewModal')")

    print('【④ 头像/照片管理页签】', flush=True)
    r4 = await ev("""(function(){
      staffShowTab('media');
      const g=document.getElementById('staffMediaGrid');
      const cards=[...g.querySelectorAll('.staff-media-card')];
      const mine=cards.find(c=>c.textContent.indexOf(%s)>=0);
      return {cards:cards.length,mine:!!mine,
        thumbs:mine?mine.querySelectorAll('.staff-media-thumb').length:0,
        upBtns:mine?[...mine.querySelectorAll('button')].map(b=>b.textContent.trim()).join('|'):'',
        snapBtn:!!document.querySelector('#staffViewMedia button[onclick*=staffMediaSnapshot]'),
        histBtn:!!document.querySelector('#staffViewMedia button[onclick*=staffMediaHist]')};})()"""
             % json.dumps(P + '姓名甲'))
    print('  ', json.dumps(r4, ensure_ascii=True), flush=True)
    ok(isinstance(r4, dict) and r4.get('cards', 0) >= 70, '管理页签按账号出卡片（%s 张）' % (r4 or {}).get('cards'))
    ok(isinstance(r4, dict) and r4.get('thumbs') == 2, '每人卡片含头像+照片两个缩略位')
    ok(isinstance(r4, dict) and '替换头像' in (r4.get('upBtns') or '') and '清除照片' in (r4.get('upBtns') or ''),
       '替换/清除按钮齐备（上传/替换 + 清除）')
    ok(isinstance(r4, dict) and not r4.get('snapBtn') and r4.get('histBtn'),
       '变更历史入口在列；快照入口已按 T-191b 移除（断言更新到现行口径）')
    await ev("closeModal('staffModal')")

    # ---------- 到期筛选 ----------
    print('【⑤ 板块筛选按钮行含【到期筛选】】', flush=True)
    r5 = await ev("""(function(){
      const btn=document.getElementById('dueFilterBtn');
      if(!btn)return {has:false};
      const btns=[...btn.parentElement.querySelectorAll('button')].map(x=>x.id||x.textContent.trim());
      return {has:true,idx:btns.indexOf('dueFilterBtn'),
        beforeClear:btns.indexOf('dueFilterBtn')>0&&btns.indexOf('dueFilterBtn')<btns.indexOf('clearFilterBtn')};})()""")
    print('  ', json.dumps(r5, ensure_ascii=True), flush=True)
    ok(isinstance(r5, dict) and r5.get('has') and r5.get('beforeClear'),
       '【到期筛选】位于【启用勾选】之后、【清空筛选】之前（清空筛选固定尾部）')

    print('【⑥ 日历弹窗：月视图 / 多选 / 切月保留 / 全选双态 / 取消还原】', flush=True)
    await ev("openDueCalModal()")
    await asyncio.sleep(0.8)
    r6 = await ev("""(function(){
      const t=document.getElementById('dueCalTitle').textContent;
      const cells=[...document.querySelectorAll('#dueCalGrid .due-cell:not(.empty)')];
      const d='%s',d2='%s';
      dueCalPick(d);dueCalPick(d2);
      const sel2=cells.length&&document.querySelector('#dueCalGrid .due-cell[data-due="'+d+'"]').classList.contains('sel');
      const n=DUE_SEL.size;
      dueCalShift(1);
      const t2=document.getElementById('dueCalTitle').textContent;
      const kept=DUE_SEL.size===n;
      dueCalShift(-1);
      const backSel=!!document.querySelector('#dueCalGrid .due-cell[data-due="'+d+'"]') &&
        document.querySelector('#dueCalGrid .due-cell[data-due="'+d+'"]').classList.contains('sel');
      // 全选本月双态
      dueCalToggleAll();
      const allLabel=document.getElementById('dueCalAllBtn').textContent.trim();
      const allN=DUE_SEL.size;
      dueCalToggleAll();
      const offN=DUE_SEL.size;
      // 清空 + 取消还原
      dueCalPick(d);dueCalPick(d2);
      dueCalClear();
      const cleared=DUE_SEL.size===0;
      dueCalPick(d);
      dueCalCancel();
      return {t:t,days:cells.length,sel2:sel2,n:n,t2:t2,kept:kept,backSel:backSel,
        allLabel:allLabel,allN:allN,offN:offN,cleared:cleared,
        restored:DUE_SEL.size===0};})()"""
             % (TOMORROW, TOMORROW2))
    print('  ', json.dumps(r6, ensure_ascii=True), flush=True)
    ok(isinstance(r6, dict) and str(r6.get('t', '')).startswith(str(TODAY.year) + '年'),
       '日历初始展示当前月（%s）' % (r6 or {}).get('t'))
    ok(isinstance(r6, dict) and r6.get('days') == 30, '本月 30 天格（实际 %s）' % (r6 or {}).get('days'))
    ok(isinstance(r6, dict) and r6.get('sel2') and r6.get('n') == 2, '点击两个日期 → 多选 2 天')
    ok(isinstance(r6, dict) and r6.get('kept') and r6.get('backSel'),
       '切换月份已选保留，切回仍高亮')
    ok(isinstance(r6, dict) and r6.get('allLabel') == '取消全选' and r6.get('allN') == 30,
       '全选本月 → 30 天、按钮变「取消全选」')
    ok(isinstance(r6, dict) and r6.get('offN') == 0,
       '再按取消全选 → 移除本月全部已选（夹具两日期均在本月 → 0，实际 %s）' % (r6 or {}).get('offN'))
    ok(isinstance(r6, dict) and r6.get('cleared'), '清空 → 全部已选清零')
    ok(isinstance(r6, dict) and r6.get('restored'), '取消 → 还原打开时快照（打开时为空 → 0）')
    await asyncio.sleep(0.5)   # 等 170ms 淡出完成
    r6c = await ev("document.getElementById('dueCalModal').style.display==='none'")
    ok(r6c is True, '取消 → 弹窗已关闭')

    print('【⑦ 热力图着色与数量角标】', flush=True)
    await ev("openDueCalModal()")
    await asyncio.sleep(1.0)
    r7 = await ev("""(function(){
      const hot=document.querySelector('#dueCalGrid .due-cell[data-due="%s"]');
      const warm=document.querySelector('#dueCalGrid .due-cell[data-due="%s"]');
      if(!hot||!warm)return {hot:!!hot,warm:!!warm};
      const hb=hot.style.background,wb=warm.style.background;
      const al=s=>{const m=/rgba\\(\\s*[\\d.]+,\\s*[\\d.]+,\\s*[\\d.]+,\\s*([\\d.]+)\\s*\\)/.exec(s);return m?parseFloat(m[1]):0};
      return {hb:hb,wb:wb,hotA:al(hb),warmA:al(wb),deeper:al(hb)>al(warm),
        badge:hot.querySelector('.dc-n')?hot.querySelector('.dc-n').textContent:null};})()"""
             % (TOMORROW, TOMORROW2))
    print('  ', json.dumps(r7, ensure_ascii=True), flush=True)
    ok(isinstance(r7, dict) and r7.get('hotA', 0) > 0, '有到期事项的日期有热力底色（alpha=%s）' % (r7 or {}).get('hotA'))
    ok(isinstance(r7, dict) and r7.get('deeper') is True,
       '到期 2 项的日期比 1 项的更红（alpha %s > %s）' % ((r7 or {}).get('hotA'), (r7 or {}).get('warmA')))
    ok(isinstance(r7, dict) and r7.get('badge') == '2', '热力角标显示数量 2')
    # 未选中的日期无热力时无色
    r7b = await ev("""(function(){
      const plain=[...document.querySelectorAll('#dueCalGrid .due-cell:not(.empty)')]
        .find(c=>!c.style.background);
      return {none:!!plain};})()""")
    ok(isinstance(r7b, dict) and r7b.get('none'), '数量为零的日期无色（透明底）')

    print('【⑧ 确定后仅显示所选截止日期的事项】', flush=True)
    # 先进入夹具看板（此前测试未选看板，boardContent 为空态）
    dbg = await ev("""(async function(){
      curBoards=new Set([%s]);curBoard=%s;
      const q=buildFilterParams({page:1,size:50}).toString();
      let direct=null;
      try{
        const r=await fetch('/api/cards?'+q,{headers:{Authorization:'Bearer '+TOKEN}});
        const dj=await r.json();
        direct={q:q,total:dj.total,n:dj.cards.length,cols:(dj.columns||[]).length};
      }catch(e){direct='ERR '+e.message}
      try{await reload(1);}catch(e){direct='RELOAD_ERR '+e.message}
      await new Promise(r=>setTimeout(r,800));
      return {q:q,direct:direct,
        html:document.getElementById('boardContent').textContent.slice(0,80)};})()"""
             % (bid_js, bid_js), True)
    print('  dbg:', json.dumps(dbg, ensure_ascii=True), flush=True)
    r8 = await ev("""(async function(){
      const bid=%s;
      const before=document.getElementById('boardContent').textContent.indexOf('%s')>=0;
      dueCalPick('%s');
      dueCalApply();
      await new Promise(r=>setTimeout(r,1200));
      const txt=document.getElementById('boardContent').textContent;
      const badge=document.getElementById('dueFilterBadge');
      let api=null;
      try{
        const resp=await fetch('/api/cards?board_ids='+encodeURIComponent(bid)+'&due_dates='+encodeURIComponent(window._dueFilter),
          {headers:{Authorization:'Bearer '+TOKEN}});
        const dj=await resp.json();
        api={total:dj.total,names:dj.cards.map(c=>c.card_name)};
      }catch(e){api='ERR '+e.message}
      return {before:before,n:DUE_SEL.size,filter:window._dueFilter,
        badge:badge.hidden?'':badge.textContent,
        hasA:txt.indexOf('%s')>=0,hasC:txt.indexOf('%s')>=0,hasB:txt.indexOf('%s')>=0,
        snippet:txt.slice(0,120),api:api,
        hint:document.getElementById('filterHint').textContent};})()"""
             % (bid_js, P + '事项甲', TOMORROW, P + '事项甲', P + '事项丙', P + '事项乙'), True)
    print('  ', json.dumps(r8, ensure_ascii=True), flush=True)
    ok(isinstance(r8, dict) and r8.get('n') == 1, '确定 → 应用 1 天到期筛选')
    ok(isinstance(r8, dict) and r8.get('badge') == '1', '按钮徽标显示已选天数 1')
    ok(isinstance(r8, dict) and r8.get('hasA') and r8.get('hasC') and not r8.get('hasB'),
       '列表仅显示截止日期命中的事项甲/丙，事项乙（次日）被滤除')
    ok(isinstance(r8, dict) and '到期：' in (r8.get('hint') or ''), '筛选明细含「到期：」')
    # 清空全部筛选后恢复
    await ev("clearAllRowFilters()")
    await asyncio.sleep(0.9)
    r9 = await ev("""(function(){
      return {n:DUE_SEL.size,badge:document.getElementById('dueFilterBadge').hidden,
        hasB:document.getElementById('boardContent').textContent.indexOf('%s')>=0};})()"""
             % (P + '事项乙'))
    ok(isinstance(r9, dict) and r9.get('n') == 0 and r9.get('badge') and r9.get('hasB'),
       '「清空筛选」清掉到期筛选，事项乙恢复显示')

    await send('Browser.close')


make_fixtures()
try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
finally:
    left = cleanup()
    fails = [m for c, m in PASS if not c]
    print('结果: PASS=%d FAIL=%d 残留=%d' % (len(PASS) - len(fails), len(fails), left), flush=True)
    if fails or left:
        sys.exit(1)
