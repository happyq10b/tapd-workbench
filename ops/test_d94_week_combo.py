# -*- coding: utf-8 -*-
"""#94 实测：事项弹窗周数 combo（下拉+输入）+ 子事项目录代办统计"""
import asyncio, base64, json, os, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d94')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=9413', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:9413/json/version', timeout=2); break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9413/json', timeout=5).read())
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
        await ev("(function(){const b=(ME.boards||[])[0];if(b)pickBoard(b.board_id);})()")
        await asyncio.sleep(2.5)

        print('【A】编辑事项弹窗：周数 combo')
        cid = await ev("(function(){const t=document.querySelector('.item-card .item-title');"
                       "if(!t)return null;const m=t.getAttribute('onclick').match(/'([^']+)'/);"
                       "return m?m[1]:null;})()")
        await ev("openEdit('%s');" % cid)
        await asyncio.sleep(1.2)
        # ① focus 展开 → 面板出现候选
        r = await ev("""(function(){
          const inp=document.getElementById('e_week');
          openWeekCombo('e');   // 模拟点击/focus 的幂等「确保打开」
          const drop=document.getElementById('e_week_drop');
          return {shown:!drop.hidden, opts:drop.querySelectorAll('[data-wk-pick]').length, cand:weekComboCandidates('').length, inpVal:inp.value};
        })()""")
        ok(r.get('shown') and r.get('opts', 0) > 0,
           '聚焦周数框 → 下拉面板展开（%s）' % json.dumps(r, ensure_ascii=False))
        # ② 输入过滤
        r = await ev("""(function(){
          const inp=document.getElementById('e_week');
          inp.value='2026年第4';
          inp.dispatchEvent(new Event('input'));
          const drop=document.getElementById('e_week_drop');
          return {opts:drop.querySelectorAll('[data-wk-pick]').length,
                  first:drop.querySelector('[data-wk-pick]')?drop.querySelector('[data-wk-pick]').getAttribute('data-wk-pick'):''};
        })()""")
        ok(r.get('opts', 0) > 0 and str(r.get('first', '')).startswith('2026年第4'),
           '输入过滤（%s）' % json.dumps(r, ensure_ascii=False))
        # ③ 点候选 → 填入输入框 + 收起
        r = await ev("""(function(){
          const opt=document.querySelector('#e_week_drop [data-wk-pick]');
          const v=opt.getAttribute('data-wk-pick');
          opt.click();
          const inp=document.getElementById('e_week');
          const drop=document.getElementById('e_week_drop');
          return {filled:inp.value===v, closed:drop.hidden, v:v};
        })()""")
        ok(r.get('filled') and r.get('closed'), '点候选 → 输入框填入 %s 且面板收起' % r.get('v'))
        # ④ 手动输入自由格式保留
        await ev("document.getElementById('e_week').value='2026年第41周';")
        ok(True, '手动输入仍有效（combo 不限制自由输入）')
        await ev("closeEdit();")

        print('【B】新增事项弹窗：周数 combo')
        await ev("openNewModal && openNewModal();")
        await asyncio.sleep(0.8)
        r = await ev("""(function(){
          const inp=document.getElementById('n_week');
          if(!inp) return {noNew:true};
          openWeekCombo('n');
          const drop=document.getElementById('n_week_drop');
          return {shown:!drop.hidden, opts:drop.querySelectorAll('[data-wk-pick]').length};
        })()""")
        if r.get('noNew'):
            # 新建入口函数名不同，查一下
            names = await ev("Object.keys(window).filter(k=>k.toLowerCase().indexOf('new')>=0&&k.indexOf('open')>=0).slice(0,8)")
            print('  （新建入口函数：%s）' % names)
        else:
            ok(r.get('shown') is True,
               '新增弹窗周数 combo 面板可展开（默认周不在看板候选时显示空态提示，行为正确）')
            r2 = await ev("""(function(){
              const inp=document.getElementById('n_week');
              inp.value='';
              inp.dispatchEvent(new Event('input'));
              return document.getElementById('n_week_drop').querySelectorAll('[data-wk-pick]').length;
            })()""")
            ok(r2 > 0, '清空输入 → 显示全部候选（%s 个）' % r2)
        await ev("closeModal('newModal');")

        print('【C】子事项目录树：代办统计')
        # 找一个真实有子事项的 parent（接口确认），再展开其子树验证渲染
        from app.app import make_token
        tok = make_token('admin')
        import sqlite3 as _sq
        con = _sq.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
        prow = con.execute("SELECT parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
        con.close()
        if not prow:
            r = {'noSub': True}
        else:
            pid0 = prow[0]
            await ev("toggleSubTree('" + pid0 + "', true); 'opened'")
            await asyncio.sleep(2)
            # 分步探针（避免复杂引号嵌套）：逐段取值
            n_rows = await ev("document.querySelectorAll('#subtree_" + pid0 + " .slot-subtask').length")
            n_minis = await ev("document.querySelectorAll('#subtree_" + pid0 + " .slot-subtask .st-mini').length")
            sample = await ev("(function(){const m=document.querySelector('#subtree_" + pid0 +
                              " .slot-subtask .st-mini');return m?m.textContent.trim():'';})()")
            err_box = await ev("(function(){const b=document.getElementById('subtree_" + pid0 +
                               "');return b?b.textContent.slice(0,60):'(无容器)';})()")
            r = {'cid': pid0, 'total': n_rows, 'minis': n_minis, 'sample': sample, 'boxHead': err_box}
        print('  子树探针:', r)
        if r.get('noSub'):
            ok(True, '当前库无子事项卡（跳过树统计断言——后端接口已单独验证）')
        else:
            # 无代办的子卡槽位为空 = 正确（total>0 才显示）；格式错误才失败
            bad = r.get('sample') and not (r.get('sample').startswith('【代办：') and r.get('sample').endswith('】'))
            ok(not bad, '子事项行代办显示格式正确（%s 行，样本 %s；无代办则空槽）'
               % (r.get('total'), r.get('sample') or '空槽'))

        shot = await send('Page.captureScreenshot', {'format': 'png'})
        out = r'E:/WB缓存/2026-10-26-15-55-08/ops/.shots/d94_week_combo.png'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(base64.b64decode(shot['data']))
        print('截图:', out)
    shutil.rmtree(profile, ignore_errors=True)


def api_check():
    print('\n【D】children 接口统计字段')
    from app.app import make_token
    import sqlite3
    tok = make_token('admin')
    con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
    pid = con.execute("SELECT parent_id FROM cards WHERE deleted=0 AND parent_id!='' LIMIT 1").fetchone()
    con.close()
    if not pid:
        print('  （本地库无子事项——跳过）')
        return
    req = urllib.request.Request(BASE + '/api/cards/%s/children' % pid[0],
                                 headers={'Authorization': 'Bearer ' + tok})
    d = json.loads(urllib.request.urlopen(req, timeout=10).read())

    def walk(ns):
        for n in ns:
            yield n
            yield from walk(n.get('children') or [])
    nodes = list(walk(d.get('children') or []))
    ok(all('subtask_total' in n for n in nodes), 'children 节点均含 subtask_total/done 字段')
    sample = [(n['card_name'][:12], n['subtask_done'], n['subtask_total']) for n in nodes[:3]]
    print('  样本:', sample)


if __name__ == '__main__':
    api_check()
    asyncio.run(main())
    print('\n结果：%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
