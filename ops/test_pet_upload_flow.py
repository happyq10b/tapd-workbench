# -*- coding: utf-8 -*-
"""T-0179 精灵批量上传/编辑/统一保存 CDP UI 测试（2026-11-12）
流程：批量上传入暂存区（不落库）→ 单张编辑（旋转+裁切确认）→ 统一保存 → 服务端落库。
夹具：__upl_ 前缀分区，结束后清理。
"""
import asyncio, base64, json, os, shutil, sqlite3, struct, subprocess, sys, time, urllib.request, urllib.error, zlib

BASE = 'http://127.0.0.1:8100'
PORT = 9491
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

PASS = []

def ok(cond, msg):
    PASS.append((bool(cond), msg))
    print(('  PASS ' if cond else '  FAIL ') + msg, flush=True)

ZONE = '__upl_test_zone'
PNG1x1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def _png(w, h):
    """生成真实 w×h 红色 PNG（旋转宽高互换验证用）"""
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    raw = b''.join(bytes([0]) + bytes([255, 0, 0, 255]) * w for _ in range(h))
    sig = bytes([0x89]) + b'PNG' + bytes([13, 10, 26, 10])
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


PNG2x1 = _png(2, 1)   # 真实 2×1 PNG（旋转后宽高互换验证）

def api_count():
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM pet_images WHERE zone=?", (ZONE,)).fetchone()[0]
    c.close()
    return n

def cleanup():
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM pet_images WHERE zone=?', (ZONE,))
    c.execute('DELETE FROM pet_zones WHERE name=?', (ZONE,))
    c.commit(); c.close()

async def main():
    tk = make_token('admin')
    req = urllib.request.Request(BASE + '/api/admin/pet/zones',
        data=json.dumps({'name': ZONE}).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    st = urllib.request.urlopen(req, timeout=10).status
    ok(st == 200, '前置：测试分区已创建')

    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t0179')
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

    async def reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('id') is not None and msg['id'] in pending:
                fut = pending.pop(msg['id'])
                if fut and not fut.done():
                    fut.set_result(msg)
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
            return {'__err__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
        return r.get('result', {}).get('value')

    rt = asyncio.create_task(reader())
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Log.enable')
    page_errors = []

    async def err_reader():
        while True:
            msg = json.loads(await w.recv())
            if msg.get('method') == 'Runtime.exceptionThrown':
                d = msg['params']['exceptionDetails']
                page_errors.append((d.get('exception', {}).get('description') or d.get('text', ''))[:300])
            if msg.get('method') == 'Log.entryAdded':
                e = msg['params']['entry']
                if e.get('level') == 'error':
                    page_errors.append(('console: ' + e.get('text', ''))[:300])
    et = asyncio.create_task(err_reader())

    await send('Page.navigate', {'url': BASE + '/login'})
    await asyncio.sleep(2.5)
    cookie = 'tk=%s; path=/; SameSite=Lax' % tk
    await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
    for _ in range(60):
        await asyncio.sleep(0.5)
        r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
        if r is True:
            break
    await asyncio.sleep(1.5)

    print('【① 打开弹窗 → 切到测试分区 → 批量上传入暂存区（不落库）】', flush=True)
    await ev("openPetSettingModal()")
    await asyncio.sleep(2)
    await ev("switchPetZone(%s)" % json.dumps(ZONE, ensure_ascii=False))
    await asyncio.sleep(1)
    inject = """
    (function(){
      function mk(b64,name){const bin=atob(b64);const u=new Uint8Array(bin.length);
        for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);
        return new File([u],name,{type:'image/png'});}
      const dt=new DataTransfer();
      dt.items.add(mk('%s','a.png'));
      dt.items.add(mk('%s','b.png'));
      const inp=document.getElementById('petFileInput');
      inp.files=dt.files;
      inp.dispatchEvent(new Event('change'));
      return 'dispatched';
    })()
    """ % (base64.b64encode(PNG1x1).decode(), base64.b64encode(PNG2x1).decode())
    await ev(inject)
    r1 = {}
    for _ in range(20):
        await asyncio.sleep(0.3)
        r1 = await ev("({p:PET_PENDING.length,names:PET_PENDING.map(x=>x.name),zone:PET_ZONE})")
        if isinstance(r1, dict) and r1.get('p') == 2:
            break
    print('  ', json.dumps(r1, ensure_ascii=False), flush=True)
    print('  btn:', await ev("document.getElementById('petSaveAllBtn').style.display+' | '+document.getElementById('petSaveAllBtn').textContent"),
          '| pend-cards:', await ev("document.querySelectorAll('#petUpList [data-pend]').length"),
          '| errors:', json.dumps(page_errors[:6], ensure_ascii=False), flush=True)
    ok(isinstance(r1, dict) and r1.get('p') == 2, '批量上传 2 张 → 暂存区 2 张')
    ok(isinstance(r1, dict) and r1.get('zone') == ZONE, '当前分区=测试分区')
    ok(isinstance(r1, dict) and r1.get('names') == ['a.png', 'b.png'], '暂存区保留原文件名')
    ok(await ev("document.getElementById('petSaveAllBtn').style.display!=='none'") is True,
       '「保存全部」按钮出现')
    ok(await ev("document.getElementById('petSaveAllBtn').textContent.indexOf('（2）')>=0") is True,
       '按钮计数=2')
    ok(api_count() == 0, '暂存阶段未落库（服务端仍 0 张）')
    ok(await ev("!!document.querySelector('#petUpList [data-pend]')") is True, '列表出现待保存卡片')

    print('【② 单张编辑：点卡片进编辑器 → 旋转 → 确认 → 预览回写】', flush=True)
    uid = await ev("PET_PENDING.find(function(x){return x.name==='b.png'}).uid")
    await ev("petEditPending(%d)" % int(uid))
    await asyncio.sleep(1.5)
    ok(await ev("document.getElementById('cropModal').style.display==='flex'") is True, '点击卡片 → 编辑器打开')
    ok(await ev("document.getElementById('cropRotBox').style.display==='inline-flex'") is True,
       '旋转按钮仅小精灵编辑显示')
    ok(await ev("CROP.img0.naturalWidth+'/'+CROP.img0.naturalHeight") == '2/1', '编辑源图 2×1')
    await ev("cropRotate(90)")
    await asyncio.sleep(0.3)
    ok(await ev("CROP.rot") == 90, '旋转 90° 生效')
    ok(await ev("CROP.img.width+'/'+CROP.img.height") == '1/2', '旋转后画布宽高互换（1×2）')
    await ev("confirmCrop()")
    await asyncio.sleep(0.5)
    ok(await ev("document.getElementById('cropModal').style.display==='none'") is True, '确认后编辑器关闭')
    r2 = await ev("(function(){const it=PET_PENDING.find(x=>x.uid===%d);return {adj:it.adjusted,len:it.dataUrl.length}})()" % int(uid))
    ok(isinstance(r2, dict) and r2.get('adj') is True, '该项标记「已调整」')
    ok(isinstance(r2, dict) and r2.get('len', 0) > 1000, 'dataUrl 已回写为裁切结果（预览更新）')
    ok(await ev("PET_EDITING") is None, '编辑态已退出（状态同步）')

    print('【③ 取消编辑：另一张进编辑器 → 取消 → 原样保留】', flush=True)
    uid2 = await ev("PET_PENDING.find(function(x){return x.name==='a.png'}).uid")
    len2 = await ev("PET_PENDING.find(function(x){return x.name==='a.png'}).dataUrl.length")
    await ev("petEditPending(%d)" % int(uid2))
    await asyncio.sleep(1)
    await ev("cancelCrop()")
    await asyncio.sleep(0.3)
    r3 = await ev("(function(){const it=PET_PENDING.find(x=>x.uid===%d);return {adj:it.adjusted,len:it.dataUrl.length}})()" % int(uid2))
    ok(isinstance(r3, dict) and r3.get('adj') is False and r3.get('len') == len2,
       '取消编辑 → 暂存项原样保留（未调整）')

    print('【④ 统一保存：全部入库 → 暂存区清空 → 服务端列表就位】', flush=True)
    await ev("petSaveAll()")
    for _ in range(30):
        await asyncio.sleep(0.5)
        if await ev("PET_SAVING") is False:
            break
    await asyncio.sleep(1)
    diag = await ev("({p:PET_PENDING.length,zone:PET_ZONE,up:PET_UP.length,"
                    "prog:document.getElementById('petUploadProgress').textContent})")
    print('  save-diag:', json.dumps(diag, ensure_ascii=False), flush=True)
    print('  toasts:', json.dumps(await ev("[...document.querySelectorAll('.toast')].map(x=>x.textContent)"), ensure_ascii=False), flush=True)
    print('  page_errors:', json.dumps(page_errors[:6], ensure_ascii=False), flush=True)
    ok(await ev("PET_PENDING.length") == 0, '暂存区清空')
    ok(api_count() == 2, '服务端落库 2 张')
    ok(await ev("PET_UP.length") == 2, '列表刷新为已保存卡片')
    ok(await ev("document.getElementById('petSaveAllBtn').style.display==='none'") is True,
       '保存按钮隐藏（暂存区空）')
    ok(await ev("PET_UP.every(function(m){return m.url.indexOf('/pet/up/')===0})") is True,
       '落库图片 URL 形如 /pet/up/{id}')

    print('【⑤ 编辑/保存状态互斥（防冲突）】', flush=True)
    await ev("PET_PENDING.push({uid:999,name:'c.png',dataUrl:PET_PENDING[0]?'x':'x',adjusted:false})")
    await ev("PET_SAVING=true")
    await ev("petEditPending(999)")
    ok(await ev("PET_EDITING") is None, '保存中点击编辑 → 被拒绝（PET_EDITING 不变）')
    await ev("PET_SAVING=false")
    await ev("petRemovePending(999)")
    ok(await ev("PET_PENDING.length") == 0, '清理后暂存区归零')

    await send('Browser.close')

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
try:
    asyncio.run(main())
finally:
    cleanup()
    print('清理：测试分区与图片已删除', flush=True)

fails = [m for c, m in PASS if not c]
print('\n结果: PASS=%d FAIL=%d' % (len(PASS) - len(fails), len(fails)), flush=True)
sys.exit(1 if fails else 0)
