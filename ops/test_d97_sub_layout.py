# -*- coding: utf-8 -*-
"""#96b 实测：子事项周数编辑生效 + 新增/编辑布局与父事项一致"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    from app.app import make_token
    tok = make_token('admin')
    import sqlite3
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'); con.row_factory = sqlite3.Row
    sub = con.execute("SELECT card_id,parent_id,week_no FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    pid, sid, old_week = sub['parent_id'], sub['card_id'], sub['week_no']
    con.close()
    new_week = '2026年第40周' if old_week != '2026年第40周' else '2026年第41周'
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d97')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu',
                      '--no-first-run', '--remote-debugging-port=9424', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9424/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9424/json', timeout=5).read())
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
                return {'__error__': str(r['exceptionDetails'])[:300]}
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
        con2 = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        pboard = con2.execute('SELECT board_id FROM cards WHERE card_id=?', (pid,)).fetchone()[0]
        con2.close()
        # ⚠️ pick 父卡**所在的看板**（此前误把 parent_id 当 board_id → 看板错误 → 探针全空）
        await ev("(function(){if(pickBoard)pickBoard('" + pboard + "');})()")
        await asyncio.sleep(2.5)

        print('【A】编辑子事项：周数可见、修改生效、目录同步')
        await ev("toggleSubTree('" + pid + "', true); 'x'")
        await asyncio.sleep(1.5)
        await ev("openSubModal('" + sid + "');")
        await asyncio.sleep(1.5)
        await ev("openDetailEdit();")
        await asyncio.sleep(1.2)
        is_sub = await ev('JSON.stringify(EDIT_IS_SUB)')
        g = await ev("(function(){const g=document.getElementById('e_week_group');return g?getComputedStyle(g).display:'gone';})()")
        week_val = await ev("JSON.stringify(document.getElementById('e_week').value)")
        owner_shown = await ev("document.getElementById('e_owner_row').style.display!=='none'")
        cc_shown = await ev("!!document.getElementById('e_cc_group').offsetParent")
        r = {'EDIT_IS_SUB': json.loads(is_sub), 'weekDisp': g, 'weekVal': json.loads(week_val),
             'ownerRowShown': owner_shown, 'ccShown': cc_shown}
        print('  探针:', r)
        ok(r.get('EDIT_IS_SUB') is True, '子事项模式识别（EDIT_IS_SUB=true）')
        ok(r.get('weekDisp') not in ('none','gone'), '周数框可见（#96b 修复：不再被 owner 搬移破坏，display=%s）' % r.get('weekDisp'))
        ok(bool(r.get('weekVal')), '周数回填（%s）' % r.get('weekVal'))
        ok(r.get('ownerRowShown') and r.get('ccShown'), '负责人/参与人与父事项同布局（一行两列）')
        # 修改周数保存
        await ev("document.getElementById('e_week').value='" + new_week + "';")
        await ev("saveEdit(); 'x'", aw=True)
        await asyncio.sleep(2)
        con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        now = con.execute("SELECT week_no FROM cards WHERE card_id=?", (sid,)).fetchone()[0]
        con.close()
        ok(now == new_week, '保存后库中周数 = %s' % now)
        # 目录同步：缓存已清 → 重新展开子树会重新拉数据 → 行周数 = 新值
        await ev("toggleSubTree('" + pid + "', false); 'x'")
        await asyncio.sleep(0.3)
        await ev("toggleSubTree('" + pid + "', true); 'x'", aw=True)
        await asyncio.sleep(1.5)
        tree_week = await ev("(function(){const row=document.querySelector('#subtree_" + pid +
                             " .sub-node');const fc=row?row.querySelector('.fcols'):null;return fc?fc.textContent:'';})()")
        print('  目录子树行字段:', (tree_week or '')[:60])
        ok(new_week in (tree_week or ''), '目录子树行周数已同步为新值（缓存清理生效）')

        print('【B】新增子事项：布局与父事项一致')
        await ev("openNewSubModal('" + pid + "');")
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
          return {title:document.getElementById('n_title').textContent,
                  boardHidden:document.getElementById('n_board_wrap').style.display==='none',
                  weekVisible:document.getElementById('n_week_group').offsetParent!==null,
                  weekFull:document.getElementById('n_week_group').style.flex.indexOf('100%')>=0,
                  parentShown:document.getElementById('n_parent_wrap').style.display!=='none',
                  parentTxt:(document.getElementById('n_parent_info').textContent||'').slice(0,40),
                  peopleRow:[...document.querySelectorAll('#n_people_row .form-group')].length};
        })()""")
        print('  探针:', r)
        ok(r.get('title') == '新建子事项', '标题=新建子事项')
        ok(r.get('boardHidden') and r.get('weekFull'), '看板隐藏（继承父）+ 周数占满整行')
        ok(r.get('parentShown') and '父事项' in r.get('parentTxt', ''), '父事项上下文行显示')
        ok(r.get('peopleRow') == 2, '负责人/参与人一行两列（与父事项一致）')
        # combo 可用
        r = await ev("""(function(){
          const inp=document.getElementById('n_week');
          inp.value='';
          openWeekCombo('n');
          return document.getElementById('n_week_drop').querySelectorAll('[data-wk-pick]').length;
        })()""")
        ok(r > 0, '周数 combo 可用（清空过滤词后候选 %s 个）' % r)
        await ev("closeModal('newModal');")

        # 主事项新增不受影响
        await ev("openNewModal();")
        await asyncio.sleep(1)
        r = await ev("""(function(){
          return {boardShown:document.getElementById('n_board_wrap').style.display!=='none',
                  parentHidden:document.getElementById('n_parent_wrap').style.display==='none',
                  weekFlex:document.getElementById('n_week_group').style.flex};
        })()""")
        ok(r.get('boardShown') and r.get('parentHidden') and r.get('weekFlex') == '',
           '主事项新增布局不受影响（看板显示/无父行/周数同行正常）')
        await ev("closeModal('newModal');")

        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d97_sub_layout.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图:', out)

        # 还原周数
        await ev("openDetailEdit();")
        await asyncio.sleep(1.2)
        await ev("document.getElementById('e_week').value='" + old_week + "';")
        await ev("saveEdit(); 'x'", aw=True)
        await asyncio.sleep(1.5)
        con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        back = con.execute("SELECT week_no FROM cards WHERE card_id=?", (sid,)).fetchone()[0]
        con.close()
        print('（周数已还原为 %s）' % back)
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    asyncio.run(main())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
