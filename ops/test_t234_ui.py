# -*- coding: utf-8 -*-
"""T-234 UI 验证（CDP）：
① 看板选择带两行完整展示（几何断言）
② 置顶最新优先：置顶组内按置顶时间从新到旧（stub eval + localStorage 时间戳落盘）
③ 板块置顶组内同规则
④ 排序新增【状态】维度枚举权重（未开始0<进行中1<已完成2<未完成3）
⑤ 【性质】【类别】枚举权重
⑥ 【不排序】三态交互（退出排序/升序自动加入）
⑦ 说明文本精简为一句话
收尾恢复 localStorage 快照（sortCfg/pins）。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token
TOK = make_token('admin')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9661
BOARD = 'BCP1793717004248'

async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t234_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                             '--window-size=1440,900', '--remote-debugging-port=%d' % PORT,
                             '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w = None
    OK = []
    def ok(cond, label):
        OK.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
            except Exception: time.sleep(0.5)
        import websockets
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}; seq = [0]
        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        async def send(mm, p=None):
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:300]}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TOK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(2.5)

        # 快照待收尾恢复
        snap = await ev("""({sc:localStorage.getItem('tapd.sortCfg_'+ME.username),
                            pins:localStorage.getItem('my_pins_v1:'+ME.username)})""")

        # ── ① 看板选择带：两行完整展示 ──
        r1 = await ev("""(function(){
          const grid=document.getElementById('tbBoards');
          if(!grid||!grid.offsetParent)return {err:'grid 不可见'};
          const items=[].slice.call(grid.children).filter(function(x){return x.offsetParent!==null;});
          if(items.length<4)return {err:'选项不足两行',n:items.length};
          const gr=grid.getBoundingClientRect();
          const last=items[3].getBoundingClientRect();
          return {maxH:grid.style.maxHeight, clientH:Math.round(gr.height),
                  lastBottomInGrid:Math.round(last.bottom-gr.top),
                  clip: last.bottom>gr.bottom+1,
                  n:items.length};
        })()""")
        ok(r1 and not r1.get('err') and not r1.get('clip'),
           '① 看板带两行选项完整展示、无截断（maxH=%s clientH=%s lastBottom=%s）'
           % (r1.get('maxH'), r1.get('clientH'), r1.get('lastBottomInGrid')) if r1 else '① grid 不可见')

        # ── ② 置顶最新优先（stub eval，确定性断言）──
        r2 = await ev("""(function(){
          const now=Date.now();
          MY_PINS.card={};
          MY_PINS.card['A']=now-5000;   // 旧置顶
          MY_PINS.card['B']=now-1000;   // 较新置顶（D 出现前排最上）
          MY_PINS.card['C']=1;          // 存量旧值 1（视为最旧）
          const card=function(id){return {card_id:id,created:'2026-11-01 10:00:00'};};
          const out=[card('A'),card('B'),card('C'),card('Z')].sort(cmpCard).map(function(x){return x.card_id;});
          // 真实路径：再置顶 D（setPinned 记时间戳）→ D 应浮到最上
          setPinned('card','D',true);
          const out2=[card('A'),card('B'),card('C'),card('D'),card('Z')].sort(cmpCard).map(function(x){return x.card_id;});
          const ls=localStorage.getItem('my_pins_v1:'+ME.username);
          const saved=JSON.parse(ls||'{}');
          const tsOk=typeof saved.card['D']==='number'&&saved.card['D']>now-60000;
          setPinned('card','D',false);delete MY_PINS.card['A'];delete MY_PINS.card['B'];delete MY_PINS.card['C'];
          return {out:out, out2:out2, tsOk:tsOk};
        })()""")
        ok(r2 and not r2.get('__error__') and r2.get('out')==['B','A','C','Z'],
           '② 置顶组内按时间从新到旧（B新 > A旧 > C存量1 > 未置顶Z，实际 %s）' % (r2 or {}).get('out'))
        ok(r2 and r2.get('out2') and r2.get('out2')[0]=='D',
           '② 新增置顶 D 立即浮到置顶列表最上部（%s）' % (r2 or {}).get('out2'))
        ok(r2 and r2.get('tsOk'), '② setPinned 落盘为时间戳（localStorage）')

        # ── ③ 板块置顶组内同规则 ──
        r3 = await ev("""(function(){
          const now=Date.now();
          MY_PINS.column={'b::甲':now-3000,'b::乙':now};
          const cmeta={'甲':{col_key:'b::甲',created_at:'2026-01-01'},
                       '乙':{col_key:'b::乙',created_at:'2026-01-01'}};
          const out=['甲','乙','丙'].sort(function(x,y){return cmpColumn(x,y,cmeta,null);});
          MY_PINS.column={};
          return out;
        })()""")
        ok(isinstance(r3, list) and r3 == ['乙', '甲', '丙'],
           '③ 板块置顶组内最新在前（乙 > 甲 > 未置顶丙，实际 %s）' % r3)

        # ── ④【状态】枚举权重 ──
        r4 = await ev("""(function(){
          window.COLS_META=[{col_key:'b::c1',column_name:'c1',nature:'日常',category:'年度重点工作'}];
          const mk=function(id,st){return {card_id:id,status:st,board_id:'b',column_name:'c1',created:'2026-11-01'};};
          const cfg={order:['status'],dir:{status:'asc'}};
          const cards=[mk('S1','open'),mk('S2','notstarted'),mk('S3','progressing'),mk('S4','done'),mk('S5','')];
          const out=cards.slice().sort(function(x,y){return cmpCard(x,y);}).map(function(x){return x.card_id;});
          // 临时替换 SORT_CFG 供 cmpCard 使用
          const bak=SORT_CFG.card;SORT_CFG.card=cfg;
          const out2=cards.slice().sort(function(x,y){return cmpCard(x,y);}).map(function(x){return x.card_id;});
          SORT_CFG.card=bak;
          return {out:out,out2:out2};
        })()""")
        ok(r4 and not r4.get('__error__') and r4.get('out2')==['S2','S3','S4','S1','S5'],
           '④ 状态权重排序：未开始<进行中<已完成<未完成，空值最后（%s）' % (r4 or {}).get('out2'))

        # ── ⑤【性质】【类别】枚举权重 ──
        r5 = await ev("""(function(){
          window.COLS_META=[
            {col_key:'b::cA',column_name:'cA',nature:'日常',category:'年度重点工作'},
            {col_key:'b::cB',column_name:'cB',nature:'专项',category:'文化及团队建设'}];
          const mk=function(id,col){return {card_id:id,board_id:'b',column_name:col,created:'2026-11-01'};};
          const bak=SORT_CFG.card;
          SORT_CFG.card={order:['nature'],dir:{nature:'asc'}};
          const o1=[mk('R','cB'),mk('D','cA')].sort(cmpCard).map(function(x){return x.card_id;});
          SORT_CFG.card={order:['category'],dir:{category:'asc'}};
          const o2=[mk('W','cB'),mk('Y','cA')].sort(cmpCard).map(function(x){return x.card_id;});
          // 未知类别排枚举之后
          SORT_CFG.card={order:['category'],dir:{category:'asc'}};
          const o3=[mk('U','不存在类别'),mk('Y','cA')].sort(cmpCard).map(function(x){return x.card_id;});
          SORT_CFG.card=bak;
          return {o1:o1,o2:o2,o3:o3};
        })()""")
        ok(r5 and not r5.get('__error__') and r5.get('o1')==['D','R'],
           '⑤ 性质权重：日常(0) < 专项(1)（%s）' % (r5 or {}).get('o1'))
        ok(r5 and r5.get('o2')==['Y','W'],
           '⑤ 类别权重：年度重点工作(0) < 文化及团队建设(4)（%s）' % (r5 or {}).get('o2'))
        ok(r5 and r5.get('o3')==['Y','U'],
           '⑤ 未知类别排枚举之后（%s）' % (r5 or {}).get('o3'))

        # ── ⑥【不排序】三态交互 ──
        r6 = await ev("""(function(){
          const bak=JSON.parse(JSON.stringify(SORT_CFG));
          openSortSetModal();
          const nBtns=document.querySelectorAll('#sortSetBody .ss-dir-btn').length;
          const nRows=document.querySelectorAll('#sortSetBody .ss-row').length;
          // 升序点击：未参与的 status → 自动加入 + asc
          sortSetDir('card','status','desc');
          const added=SORT_CFG.card.order.indexOf('status')>=0;
          // 不排序：退出
          sortSetNone('card','status');
          const removed=SORT_CFG.card.order.indexOf('status')<0;
          // checkbox 形态同步：status 行勾选框未选中
          const rows=[].slice.call(document.querySelectorAll('#sortSetBody .ss-row'));
          const stRow=rows.find(function(x){return x.textContent.indexOf('状态')>=0;});
          const cb=stRow?stRow.querySelector('input[type=checkbox]'):null;
          const cbUnchecked=cb&&!cb.checked;
          const offBtnOn=stRow?[].slice.call(stRow.querySelectorAll('.ss-dir-btn')).pop().classList.contains('on'):false;
          closeModal('sortSetModal');
          SORT_CFG=bak;
          return {nRows:nRows,nBtns:nBtns,added:added,removed:removed,cbUnchecked:cbUnchecked,offBtnOn:offBtnOn};
        })()""")
        ok(r6 and not r6.get('__error__') and r6.get('nRows')==12 and r6.get('nBtns')==36,
           '⑥ 弹窗 12 行（两分区×6维度）× 3 个方向按钮（rows=%s btns=%s）' % ((r6 or {}).get('nRows'), (r6 or {}).get('nBtns')))
        ok(r6 and r6.get('added') and r6.get('removed') and r6.get('cbUnchecked') and r6.get('offBtnOn'),
           '⑥ 升/降序自动加入排序；【不排序】退出且勾选框同步取消')

        # ── ⑦ 说明文字已整体删除（T-237b 用户需求3：弹窗精简）──
        r7 = await ev("""(function(){
          const b=document.querySelector('#sortSetModal .due-info-banner');
          return {gone:!b};
        })()""")
        ok(r7 and r7.get('gone') is True, '⑦ 说明文字已删除（弹窗精简，T-237b 口径）')

        # 收尾恢复快照
        await ev("localStorage.setItem('tapd.sortCfg_'+ME.username,%s);"
                 "localStorage.setItem('my_pins_v1:'+ME.username,%s);"
                 "loadSortCfg();loadPins();" % (json.dumps(snap.get('sc')), json.dumps(snap.get('pins'))))
    finally:
        try:
            if w: await w.close()
        except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t234_%d' % PORT)
        try: proc.kill()
        except Exception: pass
        shutil.rmtree(profile, ignore_errors=True)
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

asyncio.run(main())
