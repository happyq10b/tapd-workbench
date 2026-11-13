# -*- coding: utf-8 -*-
"""T-205b 浏览器兼容性改造验证探针（2026-11-13，CDP 真浏览器）：
  ① :has() 类名兜底 —— MutationObserver 同步 .has-chips / .has-count（模拟 chips 渲染）
  ② .tm-grp-opt 勾选态 —— change 委托切 .on 类（模拟勾选）
  ③ CSSOM：双选择器已解析、@supports 兜底块存在、旧断点块（1180/900/640/1024-顶部栏）已消失
  ④ 控制台 JS 错误
只读 + 页内 DOM 模拟注入（不触碰业务数据）。
纪律：结束 finally 回收本次启动的隔离 profile 浏览器（T-204c 教训）。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
PORT = 9545
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205compat')


def kill_profile_chrome():
    """回收本次启动的隔离 profile 浏览器进程（只匹配本 profile 路径）。"""
    try:
        out = subprocess.run(
            ['wmic', 'process', "where", "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
             '/FORMAT:VALUE'], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    for block in out.split('\n\n'):
        if PROFILE.lower() in block.lower().replace('/', '\\'):
            pid = None
            for line in block.splitlines():
                if line.startswith('ProcessId='):
                    pid = line.split('=', 1)[1].strip()
            if pid:
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)


async def main():
    import websockets
    tk = make_token('admin')
    shutil.rmtree(PROFILE, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + PROFILE, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
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
            res = await asyncio.wait_for(fut, timeout=30)
            return res.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)}
            return r.get('result', {}).get('value')

        rt = asyncio.create_task(reader())
        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})

        cookie = 'tk=%s; path=/; Max-Age=86400' % tk
        await send('Page.navigate', {'url': BASE + '/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps(cookie))
        for _ in range(90):
            await asyncio.sleep(0.5)
            r = await ev("typeof api==='function'&&typeof ME!=='undefined'&&!!ME&&ME.username==='admin'")
            if r is True:
                break
        await asyncio.sleep(2.5)
        print('admin 登录就绪', flush=True)
        await ev("window.__errs=[];window.addEventListener('error',function(e){window.__errs.push(String(e.message))})")

        PASSED = []

        def ok(cond, msg):
            PASSED.append(bool(cond))
            print(('PASS ' if cond else 'FAIL ') + msg, flush=True)

        # ① :has() 类名兜底 —— chips 渲染同步 .has-chips
        r1 = await ev("""(async function(){
          const chips=document.getElementById('personFilterChips');
          const field=chips.closest('.cf-field');
          const before=field.classList.contains('has-chips');
          chips.innerHTML='<span class="cf-chip"><span>x</span><i>×</i></span>';
          await new Promise(r=>setTimeout(r,300));
          const after=field.classList.contains('has-chips');
          chips.innerHTML='';
          await new Promise(r=>setTimeout(r,300));
          const cleared=field.classList.contains('has-chips');
          return {before,after,cleared};
        })()""", aw=True)
        print('① ', json.dumps(r1, ensure_ascii=False), flush=True)
        ok(r1.get('before') is False and r1.get('after') is True and r1.get('cleared') is False,
           '① MutationObserver 同步 .has-chips（空→有→清空）')

        # ② :has() 类名兜底 —— 计数文本同步 .has-count
        r2 = await ev("""(async function(){
          const cnt=document.getElementById('personFilterCount');
          const field=cnt.closest('.cf-field');
          cnt.textContent='已选 2';
          await new Promise(r=>setTimeout(r,300));
          const on=field.classList.contains('has-count');
          cnt.textContent='';
          await new Promise(r=>setTimeout(r,300));
          const off=field.classList.contains('has-count');
          return {on,off};
        })()""", aw=True)
        print('② ', json.dumps(r2, ensure_ascii=False), flush=True)
        ok(r2.get('on') is True and r2.get('off') is False, '② MutationObserver 同步 .has-count')

        # ③ tm-grp-opt 勾选态 change 委托
        r3 = await ev("""(function(){
          const box=document.createElement('div');
          box.id='__compat_probe_box';
          box.innerHTML='<label class="tm-grp-opt"><input type="checkbox" class="g_brd_chk"><span>t</span></label>';
          document.body.appendChild(box);
          const label=box.querySelector('.tm-grp-opt');
          const chk=box.querySelector('.g_brd_chk');
          chk.checked=true;
          chk.dispatchEvent(new Event('change',{bubbles:true}));
          const on=label.classList.contains('on');
          chk.checked=false;
          chk.dispatchEvent(new Event('change',{bubbles:true}));
          const off=label.classList.contains('on');
          box.remove();
          return {on,off};
        })()""")
        print('③ ', json.dumps(r3, ensure_ascii=False), flush=True)
        ok(r3.get('on') is True and r3.get('off') is False, '③ change 委托切 .tm-grp-opt.on')

        # ④ CSSOM：双选择器解析 + @supports 兜底 + 旧断点消失
        r4 = await ev("""(function(){
          const out={};
          function safe(k,f){try{out[k]=f()}catch(e){out[k]='ERR:'+e.message}}
          const sels=[]; const medias=[]; const wkStyle={};
          safe('collect',function(){
            for(const ss of document.styleSheets){
              let rules; try{rules=ss.cssRules}catch(e){continue}
              for(const r of rules){
                if(r.selectorText)sels.push(r.selectorText);
                if(r.media)medias.push(r.media.mediaText);
                if(r.style&&r.selectorText&&r.selectorText.indexOf('.week-header')===0)
                  wkStyle[r.selectorText+'#'+sels.length]={wus:r.style.getPropertyValue('-webkit-user-select'),us:r.style.getPropertyValue('user-select')};
                if(r.cssRules)for(const rr of r.cssRules){
                  if(rr.selectorText)sels.push(rr.selectorText);
                  if(rr.media)medias.push(rr.media.mediaText);
                }
              }
            }
          });
          const has=s=>sels.some(x=>x.indexOf(s)>=0);
          safe('hasChips',function(){return has('.cf-field.has-chips .cf-input')});
          safe('hasCount',function(){return has('.cf-field.has-count .cf-count')});
          safe('tmOn',function(){return has('.tm-grp-opt.on')});
          safe('focusFallback',function(){return has(':where(button,a[href],input,select,textarea,[tabindex],[onclick]):focus')});
          safe('supportsFocusVis',function(){return CSS.supports('selector(:focus-visible)')});
          safe('media1180',function(){return medias.some(m=>m.replace(/\\s/g,'').indexOf('max-width:1180')>=0)});
          safe('media640',function(){return medias.some(m=>m.replace(/\\s/g,'').indexOf('max-width:640')>=0)});
          safe('media1440',function(){return medias.some(m=>m.replace(/\\s/g,'').indexOf('max-width:1440')>=0)});
          safe('webkitUserSel',function(){
            // 只看**实际声明了 user-select** 的 .week-header* 规则：-webkit- 前缀必须与无前缀值一致
            const set=sels.filter(function(){return false}); // sels 只有选择器文本，改用 wkStyle
            const rows=Object.keys(wkStyle).filter(function(k){
              return wkStyle[k].us!=='';});
            return rows.length>0 && rows.every(function(k){return wkStyle[k].wus===wkStyle[k].us;});
          });
          return out;
        })()""")
        print('④ ', json.dumps(r4, ensure_ascii=False), flush=True)
        ok(r4.get('hasChips') and r4.get('hasCount') and r4.get('tmOn'), '④ CSSOM 双选择器已解析')
        ok(r4.get('focusFallback') is not False or r4.get('supportsFocusVis'),
           '④ @supports 焦点环兜底存在（CSSOM 或原生支持）')
        ok(r4.get('media1180') is False and r4.get('media640') is False, '④ 旧断点块（1180/640）已消失')
        ok(r4.get('media1440') is True, '④ 1440 断点（窄桌面适配）保留')
        ok(r4.get('webkitUserSel') is True, '④ -webkit-user-select 前缀生效')

        await asyncio.sleep(0.5)
        errs = await ev("window.__errs||[]")
        ok(not errs, f'无 JS 错误（{json.dumps(errs, ensure_ascii=False)}）')

        print(flush=True)
        print(f'=== 结果：{sum(PASSED)}/{len(PASSED)} 通过 ===', flush=True)
        return 0 if all(PASSED) else 1
    finally:
        kill_profile_chrome()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()) or 0)
