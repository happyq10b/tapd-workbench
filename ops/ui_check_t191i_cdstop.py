# -*- coding: utf-8 -*-
"""T-191i CDP 校验：倒计时停用规则（板块完成/事项完成 → 倒计时不再显示）。
夹具：板块 completion='done' 且 due=+10 天（若未停用会显示「倒计时 10」）；
      事项甲 status='done'（同样停用）；事项乙 open（正常显示）。

⚠️ 状态注记（2026-11-13）：本脚本功能已实现并经过一轮部分验证
   （板块停用 ✓ / 已完成事项停用 ✓ 两条 PASS，见 HANDOFF §六 #98）；
   「未完成事项正常显示」断言因夹具曾漏 due 已修复，但本机 headless Chrome
   环境此后持续异常（新实例起不来/锁库），未能完整复跑。
   核心功能已由既有测试覆盖：test_column_detail_modules 17/17（前缀回滚）+
   test_t191i_gate 6/6（联动门槛）。环境恢复后可直接复跑本脚本补全。
"""
import asyncio, datetime, json, os, shutil, sqlite3, subprocess, sys, time
import urllib.request

BASE = 'http://127.0.0.1:8100'
PORT = 9548
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = r'E:/WB缓存/2026-10-26-15-55-08'
DB = ROOT + '/src/app.db'
sys.path.insert(0, ROOT + '/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

PASS = []
N = []
P = '__t191i2_'
BID = P + 'bid'
COLKEY = BID + '::' + P + '板块'
TEN = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def setup():
    cleanup()
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT INTO boards(board_id,board_name,owner) VALUES(?,?,?)",
              (BID, P + '看板', 'admin'))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,year,completion,due_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (COLKEY, P + 'cid', BID, P + '板块', '2026-11-13', 'admin', '日常', '2026',
               'done', TEN))   # 板块已完成 + 有截止日期（未停用会显示倒计时 10）
    for cid, name, st in ((P + 'a', P + '事项甲', 'done'), (P + 'b', P + '事项乙', 'open')):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,"
                  "status,owner,cc,due,created,deleted,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,0,'')",
                  (cid, BID, P + '看板', P + 'cid', P + '板块', name, st, '', '', TEN,
                   '2026-11-13'))
    c.commit(); c.close()


def cleanup():
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,)).fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


async def main():
    t0 = make_token('admin')
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t191i2')
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
            print('JSERR:', json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=True)[:200])
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
    await ev("""(async function(){curBoards=new Set([%s]);curBoard=%s;await reload(1);return 'ok'})()"""
             % (json.dumps(BID), json.dumps(BID)), True)
    await asyncio.sleep(1.2)

    r = await ev("""(function(){
      const wh=document.querySelector('.week-header');
      const cd=wh?wh.querySelector('.fcol-cd'):null;
      // 事项行：甲（done，停用）乙（open，正常）
      const cds={};
      document.querySelectorAll('.item-card').forEach(function(r){
        const t=r.querySelector('.item-title');
        const c=r.querySelector('.fcol-cd');
        if(t&&c)cds[t.textContent.trim().slice(0,14)]={txt:c.textContent.trim(),empty:c.className.indexOf('fcol-empty')>=0};
      });
      return {whCd:cd?cd.textContent.trim():null,
        whEmpty:cd?cd.className.indexOf('fcol-empty')>=0:null,
        whOver:cd?cd.className.indexOf('fcol-cd-over')>=0:null,
        cds:cds};})()""")
    print('  ', json.dumps(r, ensure_ascii=True), flush=True)
    ok(isinstance(r, dict) and r.get('whCd') == '倒计时 —' and r.get('whEmpty') is True
       and r.get('whOver') is False,
       '已完成板块行：倒计时停用（显示「倒计时 —」灰占位，无数字无红色）')
    a = {k: v for k, v in (r or {}).get('cds', {}).items() if k.endswith('事项甲')}
    b = {k: v for k, v in (r or {}).get('cds', {}).items() if k.endswith('事项乙')}
    a = a[list(a)[0]] if a else {}
    b = b[list(b)[0]] if b else {}
    ok(isinstance(r, dict) and a.get('txt') == '倒计时 —' and a.get('empty') is True,
       '已完成事项行：倒计时停用（「倒计时 —」）')
    ok(isinstance(r, dict) and b.get('txt') == '倒计时 10' and b.get('empty') is False,
       '未完成事项行：倒计时正常显示「倒计时 10」（带前缀回滚生效）')
    # 服务端复核：乙的 status 与 due
    st = await ev("""(async function(){
      const d=await api('/api/cards?board_ids='+encodeURIComponent(%s)+'&size=50');
      return d.cards.map(c=>({id:c.card_id,st:c.status,due:c.due}));})()""" % json.dumps(BID), True)
    print('  服务端状态:', json.dumps(st, ensure_ascii=True), flush=True)
    await send('Browser.close')   # ⚠️ 不关浏览器会残留 Chrome 进程持有 WAL 连接 → cleanup 锁库


def try_cleanup():
    """cleanup 带重试（WAL 锁瞬时冲突兜底）。"""
    import time as _t
    for attempt in range(5):
        try:
            return cleanup()
        except sqlite3.OperationalError as ex:
            print('cleanup attempt %d locked: %s' % (attempt, ex), flush=True)
            _t.sleep(3)
    return -1


try:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    setup()
    asyncio.run(main())
finally:
    left = try_cleanup()
    fails = [m for c, m in N if not c]
    print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
    if fails or left:
        sys.exit(1)
