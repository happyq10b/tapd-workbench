#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI 设计问题扫描（Chrome headless + CDP）。

只读扫描，输出问题清单，不修改任何文件。
检查项：
  A. 对比度（WCAG AA）：正文 4.5:1 / 大字 3:1
  B. 点击目标尺寸（≥24px 实用底线，44px 移动端建议）
  C. 字号层级：过小字号（<11px）
  D. 元素重叠与溢出
  E. 焦点可见性（focus-visible 是否有可见轮廓）
  F. 语义/无障碍：缺 alt/aria-label 的可点击元素
"""
import asyncio, json, os, re, shutil, subprocess, sys, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9357
BASE = 'http://127.0.0.1:8100'
USER = os.environ.get('UI_MEASURE_USER', 'admin')
PWD = os.environ.get('UI_MEASURE_PWD', 'At159357')

SCAN = r"""
(function(){
  var out={contrast:[],targets:[],tinyFont:[],overlap:[],overflow:[],focus:[],a11y:[],errors:[]};

  function safe(fn,name){
    try{ return fn(); }
    catch(e){ out.errors.push(name+': '+String(e&&e.message||e).slice(0,120)); return null; }
  }

  function parseRGB(c){
    if(!c) return null;
    var m=String(c).match(/rgba?\(([^)]+)\)/); if(!m) return null;
    var p=m[1].split(',').map(function(x){return parseFloat(x);});
    if(p.length<3||p.some(function(v){return isNaN(v)})) return null;
    return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};
  }
  function lum(c){
    var s=[c.r,c.g,c.b].map(function(v){
      v=v/255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4);
    });
    return 0.2126*s[0]+0.7152*s[1]+0.0722*s[2];
  }
  function ratio(f,b){
    var L1=lum(f),L2=lum(b); if(L1<L2){var t=L1;L1=L2;L2=t;}
    return (L1+0.05)/(L2+0.05);
  }
  function effBg(el){
    var n=el;
    while(n && n!==document.documentElement){
      var c=parseRGB(getComputedStyle(n).backgroundColor);
      if(c && c.a>0.9) return c;
      n=n.parentElement;
    }
    return {r:255,g:255,b:255,a:1};
  }
  function isVisible(el){
    try{
      var s=getComputedStyle(el);
      if(s.display==='none'||s.visibility==='hidden'||parseFloat(s.opacity)<0.1) return false;
      var b=el.getBoundingClientRect();
      return b.width>0&&b.height>0;
    }catch(e){ return false; }
  }
  function label(el){
    try{
      var t=(el.textContent||'').replace(/\s+/g,' ').trim().slice(0,18);
      // ⚠️ SVG 元素的 className 是 SVGAnimatedString 对象，不是字符串 → 必须取 baseVal
      var cn=el.className;
      if(cn && typeof cn!=='string'){ cn=(typeof cn.baseVal!=='undefined')?cn.baseVal:''; }
      cn=String(cn||'').split(' ')[0];
      return el.tagName.toLowerCase()+(cn?'.'+cn:'')+(t?'「'+t+'」':'');
    }catch(e){ return el.tagName?el.tagName.toLowerCase():'?'; }
  }

  // ---- A/C 对比度 + 小字号 ----
  safe(function(){
    var seen={};
    Array.prototype.forEach.call(document.querySelectorAll('body *'),function(el){
      if(!isVisible(el)) return;
      var hasText=Array.prototype.some.call(el.childNodes,function(n){
        return n.nodeType===3 && n.textContent.trim().length>0; });
      if(!hasText) return;
      var cs=getComputedStyle(el);
      var fg=parseRGB(cs.color); if(!fg) return;
      var bg=effBg(el);
      var fs=parseFloat(cs.fontSize); if(isNaN(fs)) return;
      var fw=parseInt(cs.fontWeight)||400;
      var large=(fs>=24)||(fs>=18.66&&fw>=700);
      var need=large?3:4.5;
      var r=ratio(fg,bg);
      var key=cs.color+'|'+Math.round(fs)+'|'+cs.fontWeight;
      if(r<need && !seen[key]){
        seen[key]=1;
        out.contrast.push({el:label(el),fg:cs.color,
          bg:'rgb('+Math.round(bg.r)+','+Math.round(bg.g)+','+Math.round(bg.b)+')',
          ratio:Math.round(r*100)/100,need:need,fontSize:fs,weight:fw});
      }
      if(fs<11){ out.tinyFont.push({el:label(el),fontSize:fs,color:cs.color}); }
    });
  },'contrast');

  // ---- B 点击目标 ----
  safe(function(){
    // ⚠️ 排除两类误报：
    //  ① 纯文本 span（如 .item-title）—— 它是行内标题文字，点击由整行处理，
    //     不是独立的点击目标；宽度通常远大于 24px，只是行高 22px。
    //  ② 已用 ::after 扩展热区的指针图形（.chev/.item-chev/.s-chev）——
    //     视觉盒子小，但实际可点区域已是 24×24。
    var TEXT_ONLY={'item-title':1,'s-title':1,'sl-title':1,'tp-label':1,'detail-desc':1,'sl-desc':1};
    var PSEUDO_HEAT={};
    function clsOf(el){
      var cn=el.className; if(cn&&typeof cn!=='string') cn=cn.baseVal||'';
      return String(cn||'').split(' ').filter(Boolean);
    }
    Array.prototype.slice.call(
      document.querySelectorAll('button,a[href],input:not([type=hidden]),select,[onclick],[role=button]')
    ).forEach(function(el){
      if(!isVisible(el)) return;
      var b=el.getBoundingClientRect();
      if(b.height>=24&&b.width>=24) return;
      var cls=clsOf(el);
      // ① 纯文本：标签/标题类，且宽 > 100px（说明是文字块而非图标按钮）
      if(cls.length&&TEXT_ONLY[cls[0]]&&b.width>100) return;
      // ② 伪元素热区：自身有 ::after 且被定义为 24px 以上
      var hasPseudoHeat=false;
      for(var si=0;si<document.styleSheets.length&&!hasPseudoHeat;si++){
        var rs; try{ rs=document.styleSheets[si].cssRules; }catch(e){ continue; }
        if(!rs) continue;
        for(var ri=0;ri<rs.length;ri++){
          var r=rs[ri];
          if(r.selectorText&&r.style&&r.style.width&&/24px|28px|26px/.test(r.style.width)
             &&r.selectorText.indexOf('::after')>=0){
            for(var ci=0;ci<cls.length;ci++){
              if(r.selectorText.indexOf('.'+cls[ci])>=0){ hasPseudoHeat=true; break; }
            }
          }
          if(hasPseudoHeat) break;
        }
      }
      if(hasPseudoHeat) return;
      out.targets.push({el:label(el),w:Math.round(b.width),h:Math.round(b.height),
        cls:cls.join(' ')});
    });
  },'targets');

  // ---- D 重叠 ----
  safe(function(){
    var groups=[['#tbDepts','.tree-dept'],['#tbBoards','.tab-btn'],
                ['.toolbar-left','>*'],['.topbar-main','.tb-band']];
    groups.forEach(function(pair){
      var box=document.querySelector(pair[0]); if(!box) return;
      var kids=Array.prototype.slice.call(box.querySelectorAll(pair[1]));
      for(var i=0;i<kids.length-1;i++){
        var a=kids[i].getBoundingClientRect(), b=kids[i+1].getBoundingClientRect();
        var ovX=Math.min(a.right,b.right)-Math.max(a.left,b.left);
        var ovY=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
        if(ovX>1&&ovY>1){
          out.overlap.push({group:pair[0],a:label(kids[i]),b:label(kids[i+1]),
            overlapX:Math.round(ovX),overlapY:Math.round(ovY)});
        }
      }
    });
  },'overlap');

  // ---- E 焦点可见性 ----
  safe(function(){
    // ⚠️ 方法学修正：`:focus-visible` **只对键盘导航激活**，
    //    程序化 el.focus() 不会触发它（鼠标点击同理）。
    //    → 早先版本用 el.focus() + 读 computed style，把**所有**元素都误判为「无焦点环」。
    //    → 正确做法：直接扫描样式表里是否存在覆盖该元素的 :focus-visible 规则。
    var sheetHas={};
    var rules=[];
    for(var si=0;si<document.styleSheets.length;si++){
      var ss=document.styleSheets[si];
      var rs; try{ rs=ss.cssRules; }catch(e){ continue; }
      if(!rs) continue;
      for(var ri=0;ri<rs.length;ri++){
        var r=rs[ri];
        if(r.selectorText && r.selectorText.indexOf(':focus-visible')>=0){
          rules.push(r.selectorText);
          // 提取选择器里的类名
          var m=r.selectorText.match(/\.[a-zA-Z][\w-]*/g);
          if(m) m.forEach(function(c){ sheetHas[c.slice(1)]=true; });
          if(/\[tabindex\]|:where\(/.test(r.selectorText)) sheetHas['__generic__']=true;
        }
      }
    }
    out.focus={
      total:0,noVisibleRing:0,genericFallback:!!sheetHas['__generic__'],
      rulesWithFocusVisible:rules.length,coveredClasses:Object.keys(sheetHas).filter(function(k){return k!=='__generic__';}),
      uncovered:[]
    };
    // 抽测可见的可聚焦元素，看它自身类名是否被 :focus-visible 覆盖
    // ⚠️ 踩过的坑：Array.prototype.forEach.call(arr, 0, 80) 的第三参是 **thisArg**，
    //    不是「取前 80 个」→ 传 0 会让回调静默不执行，统计恒为 0。
    //    → 正确写法：先 slice 再 forEach。
    var focusables=document.querySelectorAll('button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])');
    var seenCls={};
    Array.prototype.slice.call(focusables,0,80).forEach(function(el){
      if(!isVisible(el)) return;
      out.focus.total++;
      var cn=el.className; if(cn&&typeof cn!=='string') cn=cn.baseVal||'';
      var cls=String(cn||'').split(' ').filter(Boolean);
      var covered=out.focus.genericFallback||cls.some(function(c){return sheetHas[c];});
      if(!covered){
        var key=el.tagName+'.'+(cls[0]||'');
        if(!seenCls[key]){ seenCls[key]=1; out.focus.uncovered.push(key+'「'+(el.textContent||'').replace(/\s+/g,' ').trim().slice(0,10)+'」'); }
      }
    });
    out.focus.noVisibleRing=out.focus.uncovered.length;
  },'focus');

  // ---- F 无障碍 ----
  safe(function(){
    Array.prototype.forEach.call(document.querySelectorAll('button,[onclick]'),function(el){
      if(!isVisible(el)) return;
      var txt=(el.textContent||'').trim();
      var al=el.getAttribute('aria-label')||el.getAttribute('title');
      if(!txt&&!al) out.a11y.push({el:label(el),issue:'无可访问名称（无文本/aria-label/title）'});
    });
    Array.prototype.forEach.call(document.querySelectorAll('input:not([type=hidden])'),function(el){
      if(!isVisible(el)) return;
      var id=el.id;
      var hasLabel=id&&document.querySelector('label[for="'+id+'"]');
      var hasPh=el.getAttribute('placeholder');
      var hasAl=el.getAttribute('aria-label');
      if(!hasLabel&&!hasPh&&!hasAl) out.a11y.push({el:label(el),issue:'输入框无 label/placeholder/aria-label'});
    });
  },'a11y');

  return JSON.stringify(out);
})()
"""


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_scan%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1; mid = i
                await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:400]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(USER), json.dumps(PWD)))
            for _ in range(30):
                await asyncio.sleep(0.5)
                if await ev("!!document.getElementById('tbDepts')"):
                    break
            await asyncio.sleep(2)
            raw = await ev(SCAN)
            if isinstance(raw, dict):
                print('扫描失败：' + str(raw.get('__error__')))
                return 1
            d = json.loads(raw)
            print('=' * 66)
            print('UI 设计问题扫描结果')
            print('=' * 66)

            print('\n【A】对比度不足（WCAG AA）  %d 项' % len(d['contrast']))
            for c in sorted(d['contrast'], key=lambda x: x['ratio'])[:20]:
                print('  %.2f (需 %.1f) %-34s %s / %s  %.1fpx/%d'
                      % (c['ratio'], c['need'], c['el'][:34], c['fg'], c['bg'], c['fontSize'], c['weight']))

            print('\n【B】点击目标过小（<24px，已排除纯文本与伪元素热区）  %d 项' % len(d['targets']))
            for t in d['targets'][:15]:
                print('  %dx%d  %s  [%s]' % (t['w'], t['h'], t['el'], t.get('cls', '')))

            print('\n【C】字号过小（<11px）  %d 项' % len(d['tinyFont']))
            for t in d['tinyFont'][:12]:
                print('  %.1fpx  %s  %s' % (t['fontSize'], t['el'], t['color']))

            print('\n【D】元素重叠  %d 项' % len(d['overlap']))
            for o in d['overlap'][:12]:
                print('  %s: %s ↔ %s  (x重叠%s y重叠%s)'
                      % (o['group'], o['a'], o['b'], o['overlapX'], o['overlapY']))

            print('\n【E】焦点可见性  总可聚焦 %d，无可见焦点环 %d'
                  % (d['focus']['total'], d['focus']['noVisibleRing']))

            print('\n【F】无障碍问题  %d 项' % len(d['a11y']))
            for a in d['a11y'][:12]:
                print('  %s —— %s' % (a['el'], a['issue']))
            return 0
    finally:
        out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                              '/FORMAT:CSV'], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if 'cdp_scan%d' % PORT in line:
                pid = line.strip().split(',')[-1].strip()
                if pid.isdigit():
                    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
