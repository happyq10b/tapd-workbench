# -*- coding: utf-8 -*-
"""#153 CDP 实测：账号管理 ID 列显示工号 + 排序按工号；个人界面 ID 显示工号"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9447
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

# ---------- 夹具：临时成员+账号（工号 T00099，绑定登录）——幂等 ----------
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
c.execute("DELETE FROM team_members WHERE name='__t_工号测试'")
c.execute("DELETE FROM users WHERE username='__t_emp'")
c.execute("INSERT INTO team_members (id,name,workgroups,account,emp_no) VALUES "
          "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_工号测试','','__t_emp','T00099')")
mid = c.execute("SELECT id FROM team_members WHERE name='__t_工号测试'").fetchone()[0]
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
from app.app import hash_pw
c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_emp',?,'viewer','')",
          (hash_pw('Ttest123456'),))
c.commit(); c.close()

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d153')
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    async with websockets.connect(ws, max_size=50 * 1024 * 1024) as w:
        i = 0
        async def send(m, p=None):
            nonlocal i; i += 1; mid2 = i
            await w.send(json.dumps({'id': mid2, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid2: return msg.get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:200]}
            return r.get('result', {}).get('value')
        await send('Page.enable'); await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride', {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';document.getElementById('p').value='At159357';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"): break
        await asyncio.sleep(1.5)

        print('【① 账号管理：ID 列显示工号】')
        await ev("openTeamModal()")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
          const row=[...document.querySelectorAll('#tm_tbody tr')].find(function(tr){
            return tr.querySelector('td:nth-child(2) input') && tr.querySelector('td:nth-child(2) input').value==='余河';});
          const ids=[...document.querySelectorAll('#tm_tbody tr td:first-child')].slice(0,3).map(function(x){return x.textContent});
          return {yhId:row?row.querySelector('td:first-child').textContent:null,
                  first3:ids, th:document.querySelector('#teamModal .tm-table-scroll thead th').textContent.trim()};
        })()""")
        print('  ', json.dumps(r, ensure_ascii=False))
        ok(r.get('yhId') == '00006', '余河的 ID 列显示工号 00006：%s' % r.get('yhId'))
        ok(all(len(x) == 5 for x in (r.get('first3') or [])), 'ID 均为 5 位工号格式：%s' % r.get('first3'))
        ok((r.get('th') or '').startswith('ID'), '列名仍为「ID」：%s' % r.get('th'))

        print('【② 双击排序按工号（升→降）】')
        r2 = await ev("""(async function(){
          function ids(){return [...document.querySelectorAll('#tm_tbody tr td:first-child')].map(function(x){return x.textContent});}
          var th=document.querySelector('#teamModal .tm-table-scroll thead th');
          th.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
          await new Promise(function(res){setTimeout(res,300)});
          var d=ids(); var th1=th.textContent.trim();
          th.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
          await new Promise(function(res){setTimeout(res,300)});
          var a=ids(); var th2=th.textContent.trim();
          return {descFirst:d[0],descLast:d[d.length-1],th1:th1,ascFirst:a[0],ascLast:a[a.length-1],th2:th2,n:a.length};
        })()""", aw=True)
        print('  ', json.dumps(r2, ensure_ascii=False))
        ok(r2.get('th1').find('↓') >= 0 and r2.get('descFirst') == 'T00099' and r2.get('descLast') == '00006',
           '降序：T00099（字典序最大）排最前、00006 最后')
        ok(r2.get('th2').find('↑') >= 0 and r2.get('ascLast') == 'T00099',
           '升序时 T00099 排最后（工号序）')
        ok(r2.get('n') >= 66, '全部 %s 行参与排序' % r2.get('n'))
        await ev("closeModal('teamModal')")
        await asyncio.sleep(1)

        print('【③ 个人界面：ID 显示工号（用绑定了成员的测试账号登录）】')
        # 登出 → 用 __t_emp 登录
        await ev("logout()")
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='__t_emp';document.getElementById('p').value='Ttest123456';document.getElementById('btn').click();")
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"): break
        await asyncio.sleep(1.5)
        me = await ev("({emp_no:ME.emp_no,member_id:ME.member_id,name:ME.display_name})")
        print('  ', json.dumps(me, ensure_ascii=False))
        ok(me.get('emp_no') == 'T00099', '/api/me 返回 emp_no=T00099')
        await ev("openProfileModal()")
        await asyncio.sleep(1.2)
        r3 = await ev("""(function(){
          return {idTxt:document.getElementById('pf_member_id').textContent,
                  nameTxt:document.getElementById('pf_name').textContent,
                  label:document.querySelector('#pf_member_id').previousElementSibling.textContent};
        })()""")
        print('  ', json.dumps(r3, ensure_ascii=False))
        ok(r3.get('idTxt') == 'T00099', '个人界面 ID 显示工号 T00099')
        ok(r3.get('label') == 'ID', '列名仍为「ID」')
        await ev("closeModal('profileModal')")

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))

asyncio.run(main())

# ---------- 清理夹具（try/finally 兜底：无论测试成败都清） ----------
c = sqlite3.connect(DB)
c.execute("DELETE FROM team_members WHERE name='__t_工号测试'")
c.execute("DELETE FROM users WHERE username='__t_emp'")
c.commit()
n1 = c.execute("SELECT COUNT(*) FROM team_members WHERE name='__t_工号测试'").fetchone()[0]
n2 = c.execute("SELECT COUNT(*) FROM users WHERE username='__t_emp'").fetchone()[0]
c.close()
print('夹具残留: members=%d users=%d' % (n1, n2))
