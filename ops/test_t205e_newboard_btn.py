# -*- coding: utf-8 -*-
"""T-205e：看板带「＋ 新建看板」按钮（用户需求①②）

① admin（超管）登录 → 看板带标题行右端按钮可见 → 点击 → 看板管理弹窗打开
   且「新建看板」弹窗自动叠加（boardModal 在上、boardConfigModal 在下）
② 无权限用户（__cdp_ui 普通管理员 role=admin 但 arch_scope 空 & 非 admin 账号）
   → 按钮不渲染（display:none）
   ⚠️ __cdp_ui role=admin 会走 ME.is_admin=true → 按钮可见。需造一个
   role=editor 且非架构负责人的夹具账号验证「不渲染」。改用 make_token
   直接给 editor 夹具账号签 token（CDP cookie 注入）。
③ 关闭新建看板弹窗 → 回到看板管理弹窗（叠加语义）
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
PORT = 9573
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = os.path.join(ROOT, 'src', 'app.db')
U1 = '__t205e_editor'      # editor、无 arch_scope → 按钮应不渲染
_results = []


def ok(cond, msg):
    _results.append((bool(cond), msg))
    print(('PASS ' if cond else 'FAIL ') + msg)


async def login_and_check(token, who):
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205e_' + who)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      f'--remote-debugging-port={PORT}', '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    w = None
    try:
        t = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}

        async def reader():
            while True:
                m = json.loads(await w.recv())
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done():
                        f.set_result(m)

        seq = [0]

        async def send(m, p=None):
            seq[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[seq[0]] = fut
            await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
            return (await asyncio.wait_for(fut, timeout=30)).get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % token))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True:
                break
        await asyncio.sleep(2.5)
        return ev, profile
    except Exception:
        shutil.rmtree(profile, ignore_errors=True)
        raise


async def main():
    tk_admin = make_token('admin')

    # ① admin：按钮可见 + 点击联动
    ev, profile = await login_and_check(tk_admin, 'admin')
    try:
        s1 = await ev("""(function(){
          const entry=document.getElementById('boardNewEntry');
          const btn=document.getElementById('bandNewBoardBtn');
          return {shown:!!(entry&&entry.style.display!=='none'),
                  btnText:btn?btn.textContent.trim():'',
                  inHead:!!(entry&&entry.closest('.tb-band-head')),
                  isSuper:!!ME.is_super, archN:(ME.arch_scope||[]).length};
        })()""")
        ok(s1.get('shown') is True and s1.get('btnText') == '＋ 新建看板',
           f"① admin 按钮可见（is_super={s1.get('isSuper')}，arch_scope={s1.get('archN')} 项，文案={s1.get('btnText')!r}）")
        ok(s1.get('inHead') is True, '① 按钮位于看板带标题行（tb-band-head 内、右端槽位）')

        await ev("bandNewBoard()")
        await asyncio.sleep(2)
        s2 = await ev("""(function(){
          const bc=document.getElementById('boardConfigModal');
          const bm=document.getElementById('boardModal');
          const bcz=parseInt(bm.style.zIndex||'0'), ccz=parseInt(bc.style.zIndex||'0');
          return {bcOpen:bc.style.display&&bc.style.display!=='none',
                  bmOpen:bm.style.display&&bm.style.display!=='none',
                  bmOverBc:bcz>0?bcz>0&&bm.style.zIndex!=='':true,
                  bmZ:bm.style.zIndex};
        })()""")
        ok(s2.get('bcOpen') is True and s2.get('bmOpen') is True,
           f"① 点击 → 看板管理打开（{s2.get('bcOpen')}）且新建看板弹窗自动叠加（{s2.get('bmOpen')}，z={s2.get('bmZ')}）")
        await ev("closeModal('boardModal')")
        await asyncio.sleep(0.5)
        s3 = await ev("(function(){const bc=document.getElementById('boardConfigModal');"
                      "return {bcStill:bc.style.display&&bc.style.display!=='none'};})()")
        ok(s3.get('bcStill') is True, '③ 关闭新建弹窗 → 回到看板管理（仍打开）')
        await ev("closeModal('boardConfigModal')")
    finally:
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205e_admin')
        shutil.rmtree(profile, ignore_errors=True)

    # ② 无权限用户：editor 且非架构负责人 → 按钮不渲染
    c = sqlite3.connect(DB)
    c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
              (U1, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    try:
        ev, profile = await login_and_check(make_token(U1), 'editor')
        try:
            s4 = await ev("""(function(){
              const entry=document.getElementById('boardNewEntry');
              return {hidden:!!entry&&entry.style.display==='none',
                      isSuper:!!ME.is_super, archN:(ME.arch_scope||[]).length, role:ME.role};
            })()""")
            ok(s4.get('hidden') is True,
               f"② 无权限用户（{s4.get('role')}，arch_scope={s4.get('archN')}）→ 按钮不渲染（display:none）")
        finally:
            from cdp_test_helper import kill_profile_chrome
            kill_profile_chrome('cdp_t205e_editor')
            shutil.rmtree(profile, ignore_errors=True)
    finally:
        c = sqlite3.connect(DB)
        c.execute('DELETE FROM users WHERE username=?', (U1,))
        c.commit()
        n = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%\\_t205e%' ESCAPE '\\'").fetchone()[0]
        c.close()
        print('夹具清理后残留:', n)


asyncio.run(main())
fails = [m for p, m in _results if not p]
print('结果: %d/%d' % (len(_results) - len(fails), len(_results)))
sys.exit(1 if fails else 0)
