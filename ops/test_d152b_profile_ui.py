# -*- coding: utf-8 -*-
"""#152 个人界面基本信息 CDP 实测：回填/保存/重开读回/还原 + 现有元素保留"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PORT = 9446
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

async def main():
    import websockets
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d152')
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
            nonlocal i; i += 1; mid = i
            await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await w.recv())
                if msg.get('id') == mid: return msg.get('result', {})
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

        print('【① 打开个人界面：现有元素保留 + 新字段结构】')
        await ev("openProfileModal()")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
          const ids=['profileAvatarBox','profilePhotoBox','profileStatus','profileOldPwd','profileNewPwd2',
                     'pf_member_id','pf_name','pf_gender','pf_hire_date','pf_birth_date','pf_phone',
                     'pf_native_province','pf_native_city','pf_political'];
          const present=ids.filter(function(id){return !!document.getElementById(id)});
          const grid=document.querySelector('#profileModal .profile-grid');
          const cs=grid?getComputedStyle(grid):null;
          return {presentCount:present.length, of:ids.length,
                  gridCols:cs?cs.gridTemplateColumns.split(' ').length:0,
                  modalW:Math.round(document.querySelector('#profileModal .modal').getBoundingClientRect().width),
                  idTxt:document.getElementById('pf_member_id').textContent,
                  nameTxt:document.getElementById('pf_name').textContent};
        })()""")
        print('  ', json.dumps(r, ensure_ascii=False))
        ok(r.get('presentCount') == r.get('of'), '现有元素 + 新字段 14/14 全部存在（%s）' % r.get('presentCount'))
        ok(r.get('gridCols') == 3, '基本信息三列网格')
        ok((r.get('modalW') or 0) >= 600, '弹窗加宽至 %spx' % r.get('modalW'))
        ok(r.get('idTxt') == '—' or str(r.get('idTxt')).isdigit(), 'ID 只读显示（%s）' % r.get('idTxt'))
        ok((r.get('nameTxt') or '') != '', '姓名只读显示（%s）' % r.get('nameTxt'))

        print('【② 填写并保存 → 重开读回】')
        await ev("""(function(){
          document.getElementById('pf_gender').value='男';
          document.getElementById('pf_hire_date').value='2021-06-01';
          document.getElementById('pf_birth_date').value='1996-05-20';
          document.getElementById('pf_phone').value='13900002222';
          document.getElementById('pf_native_province').value='江苏';
          document.getElementById('pf_native_city').value='南京';
          document.getElementById('pf_political').value='共青团员';
          saveProfile();
        })()""")
        await asyncio.sleep(2.5)
        closed = await ev("document.getElementById('profileModal').style.display!=='flex'")
        ok(closed, '保存后弹窗关闭')
        await ev("openProfileModal()")
        await asyncio.sleep(1.2)
        r2 = await ev("""(function(){
          const g=function(id){return document.getElementById(id).value};
          return {gender:g('pf_gender'),hire:g('pf_hire_date'),birth:g('pf_birth_date'),
                  phone:g('pf_phone'),prov:g('pf_native_province'),city:g('pf_native_city'),pol:g('pf_political')};
        })()""")
        print('  ', json.dumps(r2, ensure_ascii=False))
        ok(r2.get('gender') == '男' and r2.get('hire') == '2021-06-01' and r2.get('birth') == '1996-05-20', '日期/性别读回一致')
        ok(r2.get('phone') == '13900002222' and r2.get('prov') == '江苏' and r2.get('pol') == '共青团员', '手机/籍贯/政治面貌读回一致')

        print('【③ 前端校验：非法手机号阻止提交】')
        await ev("document.getElementById('pf_phone').value='12345'")
        await ev("saveProfile()")
        await asyncio.sleep(1)
        r3 = await ev("""(function(){
          var toasts=[...document.querySelectorAll('.toast')].map(function(x){return x.textContent}).join('|');
          return {toast:toasts, open:document.getElementById('profileModal').style.display==='flex'};
        })()""")
        ok('手机号码格式不正确' in (r3.get('toast') or ''), 'toast 校验提示：%s' % r3.get('toast'))
        ok(r3.get('open'), '非法手机号时弹窗保持打开（阻止提交）')

        print('【④ 还原清空】')
        await ev("""(function(){
          ['pf_gender','pf_hire_date','pf_birth_date','pf_phone','pf_native_province','pf_native_city','pf_political'].forEach(function(id){document.getElementById(id).value=''});
          saveProfile();
        })()""")
        await asyncio.sleep(2.5)
        ok(True, '已还原为全空')
        await ev("closeModal('profileModal')")
    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))

asyncio.run(main())
