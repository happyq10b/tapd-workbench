# -*- coding: utf-8 -*-
"""T-191k 校验：①编辑事项弹窗无「复制」按钮（目录已有入口）；②编辑板块删除按钮 = 编辑事项删除按钮同款简单样式。"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9552
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191k')
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                             '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up = False
    for _ in range(40):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
            up = True
            break
        except Exception:
            time.sleep(0.5)
    if not up:
        print('ENV-FAIL: headless Chrome 不可用', flush=True)
        proc.kill()
        return
    t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
    import websockets
    w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
    pending, seq = {}, [0]

    async def send(m, p=None):
        seq[0] += 1
        fut = asyncio.get_event_loop().create_future()
        pending[seq[0]] = fut
        await w.send(json.dumps({'id': seq[0], 'method': m, 'params': p or {}}))
        return (await asyncio.wait_for(fut, timeout=60)).get('result', {})

    async def ev(e, aw=False):
        r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
        if r.get('exceptionDetails'):
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:160], flush=True)
            return {'__err__': True}
        return r.get('result', {}).get('value')

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)

    asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    await ev('document.cookie=%s;location.href="/";' % json.dumps('tk=%s; path=/; SameSite=Lax' % t0))
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await ev("typeof ME!=='undefined'&&!!ME&&ME.username==='admin'") is True:
            break
    await asyncio.sleep(1.5)

    # 取一个真实事项进编辑弹窗
    r0 = await ev("(async function(){const r=await fetch('/api/cards?size=1',{headers:{Authorization:'Bearer '+TOKEN}});const d=await r.json();if(!d.cards.length)return null;await openEdit(d.cards[0].card_id);return 'ok'})()", True)
    await asyncio.sleep(1.2)
    r1 = await ev("""(function(){
      const f=document.querySelector('#editModal .modal-footer');
      const btns=[...f.querySelectorAll('button')].map(b=>b.textContent.trim());
      const del=f.querySelector('button[onclick="deleteCard()"]');
      return {btns:btns,copy:btns.some(t=>t.indexOf('复制')>=0),
        delTxt:del?del.textContent.trim():null,
        delCls:del?del.className:null};})()""")
    print('  ', json.dumps(r1, ensure_ascii=True), flush=True)
    ok(isinstance(r1, dict) and r1.get('copy') is False, '编辑事项 footer 无「复制」按钮')
    ok(isinstance(r1, dict) and r1.get('delTxt') == '删除', '编辑事项「删除」按钮保持原样')
    ok(isinstance(r1, dict) and set(r1.get('btns') or []) >= {'取消', '保存'}, '取消/保存仍在')
    await ev("closeEdit()")

    # 打开板块编辑弹窗（任选一个可见板块）
    r2 = await ev("""(async function(){
      const cm=(window.COLS_META||[])[0];
      if(!cm)return 'no-col';
      await openColumnEdit({colkey:cm.col_key,bid:cm.board_id,cname:cm.column_name,year:cm.year,
        nature:cm.nature,created:cm.created_at,creator:cm.creator,owner:cm.owner,parts:cm.participants,
        completion:cm.completion,desc:cm.description,due:cm.due_date},false);
      return 'ok';})()""", True)
    await asyncio.sleep(1.0)
    r3 = await ev("""(function(){
      const del=document.getElementById('c_delete_btn');
      const cs=getComputedStyle(del);
      const eDel=document.querySelector('#editModal .modal-footer button[onclick="deleteCard()"]');
      const eDelCls=eDel?eDel.className:null;
      return {txt:del.textContent.trim(),cls:del.className,emoji:/[\\uD83C-\\uDBFF\\uDC00-\\uDFFF]/.test(del.textContent),
        mrAuto:cs.marginRight==='auto',dis:del.style.display,
        eCls:eDelCls,sameCls:del.className===eDelCls};})()""")
    print('  ', json.dumps(r3, ensure_ascii=True), flush=True)
    ok(isinstance(r3, dict) and r3.get('txt') == '删除', '板块删除按钮文案 =「删除」（去掉 emoji 与「板块」后缀）')
    ok(isinstance(r3, dict) and r3.get('emoji') is False, '无 emoji 图标')
    ok(isinstance(r3, dict) and r3.get('mrAuto') is False, '不再独占一行（去掉 margin-right:auto，与事项 footer 同排）')
    ok(isinstance(r3, dict) and r3.get('sameCls') is True, '按钮类名与编辑事项「删除」完全一致（btn-default）')

    try:
        await send('Browser.close')
    except Exception:
        pass
    fails = [m for c2, m in N if not c2]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
except Exception as e:
    print('ERR', repr(e)[:200], flush=True)
