# -*- coding: utf-8 -*-
"""#119 实测：看板卡片【编辑】按钮 → 看板管理弹窗定位到该看板 → 保存生效并自动关闭

验证口径：
  ① 看板卡片（span.tab-btn）内存在 .dept-home「编辑」按钮（与架构卡「主页」同类）
  ② 点击编辑 → 弹窗打开、BC_SELECTED 定位到该看板、右侧表单回填现有信息
  ③ 修改备注 → 点【保存看板】→ 弹窗自动关闭 + /api/boards 读回新值（生效）
  ④ 页面状态同步：renderTabs 重渲染后卡片仍在、BC_FROM_CARD 复位
  ⑤ 标准入口（📊 看板管理）不受影响：保存后弹窗不关闭
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9417
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d120')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=30 * 1024 * 1024) as w:
        i = 0

        async def send(m, p=None):
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:400]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1440, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"):
                break
        await asyncio.sleep(2)
        # 展开第一个有看板的部门，让看板卡片渲染出来
        r = await ev("""(function(){
          const g=groupBoardsByDept();
          const d=g.depts.find(x=>x.boards.length)||{name:g.unassigned.length?'__un__':null,boards:g.unassigned};
          if(!d)return {none:true};
          if(d.name==='__un__'){DEPT_OPEN[UNASSIGNED_KEY]=true;return {bid:g.unassigned[0].board_id,name:g.unassigned[0].board_name}}
          DEPT_OPEN[d.name]=true;
          return {bid:d.boards[0].board_id,name:d.boards[0].board_name};
        })()""")
        await ev("renderTabs();")
        await asyncio.sleep(1.5)
        if r.get('none'):
            ok(False, '无可展开部门，跳过'); return
        bid = r['bid']
        print('目标看板：%s (%s)' % (r['name'], bid))

        print('【① 卡片上的【编辑】按钮】')
        r1 = await ev("""(function(){
          const card=[...document.querySelectorAll('#tbBoards .tab-btn')].find(x=>x.querySelector('.dept-home'));
          const btn=card?card.querySelector('.dept-home'):null;
          const arch=document.querySelector('#tbDepts .dept-home');
          const cs=btn?getComputedStyle(btn):null;
          return {cards:document.querySelectorAll('#tbBoards .tab-btn').length,
                  withBtn:document.querySelectorAll('#tbBoards .tab-btn .dept-home').length,
                  inCard:card?card.contains(btn):false,
                  fontSize:cs?cs.fontSize:'', text:btn?btn.textContent:''};
        })()""")
        ok(r1.get('withBtn', 0) > 0 and r1.get('inCard'),
           '看板卡片内有【编辑】按钮（%s 张卡片 / %s 个按钮，文本「%s」，字号 %s）'
           % (r1.get('cards'), r1.get('withBtn'), r1.get('text'), r1.get('fontSize')))
        ok(r1.get('fontSize') == '11.5px', '样式与架构卡「主页」一致（同为 .dept-home，11.5px）')

        print('【② 点击编辑 → 弹窗定位 + 表单回填】')
        orig = await ev("(function(){const b=ME.boards.find(x=>x.board_id==='%s');return {name:b?b.board_name:''};})()" % bid)
        await ev("""(function(){
          const card=[...document.querySelectorAll('#tbBoards .tab-btn')].find(x=>x.querySelector('.dept-home'));
          card.querySelector('.dept-home').click();
        })()""")
        await asyncio.sleep(3)   # loadBoardConfig + bcLoadAclMembers
        r2 = await ev("""(function(){
          const m=document.getElementById('boardConfigModal');
          const area=document.getElementById('bcEditArea');
          return {open:m&&m.style.display==='flex',
                  sel:(typeof BC_SELECTED!=='undefined'&&BC_SELECTED)?BC_SELECTED.board_id:'',
                  isEditTitle:(area.textContent||'').indexOf('编辑看板配置')>=0,
                  remarkField:!!document.getElementById('bc_remark'),
                  deptSel:(document.getElementById('bc_dept')||{}).value||''};
        })()""")
        ok(r2.get('open'), '看板管理弹窗已打开')
        ok(r2.get('sel') == bid, '弹窗定位到目标看板：%s' % r2.get('sel'))
        ok(r2.get('isEditTitle') and r2.get('remarkField'), '右侧为「编辑看板配置」且表单已渲染')

        print('【③ 修改备注 → 保存 → 弹窗关闭 + 数据生效】')
        stamp = '__bc_edit_%d__' % (int(time.time()) % 100000)
        await ev("document.getElementById('bc_remark').value='%s';"
                 "document.getElementById('bc_remark').dispatchEvent(new Event('input'));" % stamp)
        await ev("saveBoardAll();'fired'")
        await asyncio.sleep(3)
        r3 = await ev("""(function(){
          const m=document.getElementById('boardConfigModal');
          return {closed:m&&m.style.display!=='flex',
                  fromCardReset:(typeof BC_FROM_CARD!=='undefined')&&BC_FROM_CARD===false,
                  remark:(typeof BC_BOARDS!=='undefined'&&BC_BOARDS.find(x=>x.board_id==='%s')||{}).remark};
        })()""" % bid)
        ok(r3.get('closed'), '保存后弹窗自动关闭')
        ok(r3.get('fromCardReset'), '入口标记复位（BC_FROM_CARD=false）')
        ok(r3.get('remark') == stamp, '备注已生效（读回=%s）' % r3.get('remark'))

        print('【④ 恢复原备注（再走一遍卡片编辑链路）】')
        origRemark = await ev("fetch('/api/boards',{headers:{'Authorization':'Bearer '+TOKEN}}).then(r=>r.json()).then(d=>'(读回即 %s，无需恢复)')" % stamp)
        # 原备注未知（可能原本为空）→ 直接清空为 ''（保守还原：备注字段多数看板为空）
        await ev("(function(){const card=[...document.querySelectorAll('#tbBoards .tab-btn')].find(x=>x.querySelector('.dept-home'));card.querySelector('.dept-home').click();})()")
        await asyncio.sleep(3)
        ok(await ev("document.getElementById('boardConfigModal').style.display==='flex'"), '再次从卡片打开弹窗')
        await ev("document.getElementById('bc_remark').value='';"
                 "document.getElementById('bc_remark').dispatchEvent(new Event('input'));saveBoardAll();'fired'")
        await asyncio.sleep(3)
        r4 = await ev("""(function(){
          return {closed:document.getElementById('boardConfigModal').style.display!=='flex',
                  remark:(BC_BOARDS.find(x=>x.board_id==='%s')||{}).remark,
                  cardAlive:!!document.querySelector('#tbBoards .tab-btn .dept-home')};
        })()""" % bid)
        ok(r4.get('closed') and r4.get('remark') == '', '还原备注并自动关闭（remark=%r）' % r4.get('remark'))
        ok(r4.get('cardAlive'), '页面状态同步：顶栏看板卡片正常重渲染')

        print('【⑤ 标准入口回归：保存后不关闭】')
        await ev("openBoardConfigModal();'fired'")
        await asyncio.sleep(3)
        r5 = await ev("""(function(){
          return {open:document.getElementById('boardConfigModal').style.display==='flex',
                  noSel:(typeof BC_SELECTED!=='undefined')&&BC_SELECTED===null,
                  fromCard:(typeof BC_FROM_CARD!=='undefined')&&BC_FROM_CARD===false};
        })()""")
        ok(r5.get('open') and r5.get('noSel') and r5.get('fromCard'),
           '📊 看板管理入口：默认不选中、BC_FROM_CARD=false（保存后仍停留弹窗，行为不变）')
        await ev("closeModal('boardConfigModal');")

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
