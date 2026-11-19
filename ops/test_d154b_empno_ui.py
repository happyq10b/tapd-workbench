# -*- coding: utf-8 -*-
"""#154b CDP：超管在账号管理界面改 ID —— 输入框、撞号 toast 带姓名、唯一修改生效"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9448
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM team_members WHERE name='__t_idui'")
    c.execute("INSERT INTO team_members (id,name,workgroups,account,emp_no) VALUES "
              "((SELECT COALESCE(MAX(id),0)+1 FROM team_members),'__t_idui','','','T99001')")
    mid = c.execute("SELECT id FROM team_members WHERE name='__t_idui'").fetchone()[0]
    c.commit(); c.close()
    return mid

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM team_members WHERE name='__t_idui'")
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM team_members WHERE name='__t_idui'").fetchone()[0]
    c.close()
    print('夹具残留: %d' % n)

MID = setup()
try:
    async def main():
        import websockets
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d154')
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

            print('【① ID 列为可编辑输入框（超管）】')
            await ev("openTeamModal()")
            await asyncio.sleep(2.5)
            r = await ev("""(function(){
              const row=[...document.querySelectorAll('#tm_tbody tr')].find(function(tr){
                const n=tr.querySelector('td:nth-child(2) input');
                return n && n.value==='__t_idui';});
              if(!row)return {noRow:true};
              const inp=row.querySelector('#tm_empno_'+%d);
              const inputCount=[...document.querySelectorAll('#tm_tbody tr td:first-child input')].length;
              return {hasInput:!!inp, val:inp?inp.value:null, inputCount:inputCount};
            })()""" % MID, aw=True)
            print('  ', json.dumps(r, ensure_ascii=False))
            ok(r.get('hasInput') and r.get('val') == 'T99001', '夹具行 ID 为输入框，当前值 T99001')
            ok((r.get('inputCount') or 0) >= 70, '超管视图全部 %s 行 ID 均可编辑' % r.get('inputCount'))

            print('【② 改成他人工号 00006 → toast 带占用者姓名】')
            await ev("""(function(){
              const inp=document.getElementById('tm_empno_'+%d);
              inp.value='00006';
              saveAllTeamMembers();
            })()""" % MID, aw=True)
            await asyncio.sleep(1.5)
            r2 = await ev("""(function(){
              var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
              return {toast:toasts, val:document.getElementById('tm_empno_'+%d).value};
            })()""" % MID, aw=True)
            print('  ', json.dumps(r2, ensure_ascii=False))
            ok('00006' in (r2.get('toast') or '') and '余河' in (r2.get('toast') or ''),
               'toast 带占用者姓名：%s' % r2.get('toast'))

            print('【③ 改成唯一 ID → 保存生效并读回】')
            await ev("""(function(){
              const inp=document.getElementById('tm_empno_'+%d);
              inp.value='T99099';
              saveAllTeamMembers();
            })()""" % MID, aw=True)
            await asyncio.sleep(2.5)
            r3 = await ev("""(async function(){
              await openTeamModal();
              await new Promise(function(res){setTimeout(res,2000)});
              const row=[...document.querySelectorAll('#tm_tbody tr')].find(function(tr){
                const n=tr.querySelector('td:nth-child(2) input');
                return n && n.value==='__t_idui';});
              return {val:row?row.querySelector('#tm_empno_'+%d).value:null};
            })()""" % MID, aw=True)
            print('  ', json.dumps(r3, ensure_ascii=False))
            ok(r3.get('val') == 'T99099', '重开弹窗读回新 ID T99099')
            await ev("closeModal('teamModal')")
    asyncio.run(main())
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
finally:
    cleanup()
