#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""组织架构树状图交互专项验证（Chrome headless + CDP）

覆盖：
  1) 顶部工具栏：存在「展开全部 / 折叠全部」两个按钮
  2) 一键展开全部：多级节点批量展开（所有子容器由隐藏 → 显示）
  3) 一键折叠全部：全部收起，且**顶层节点仍可见**
  4) 展开/折叠状态与筛选条件互不影响（折叠不清掉已选的「无负责人」）
  5) 「无负责人」作为独立显示选项：树上以标签节点呈现
  6) 确认后「无负责人」进入 PERSON_SEL 并真正筛出负责人为空的事项

运行：ops/.localvenv/Scripts/python.exe ops/ui_check_tree.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = os.environ.get('TAPD_BASE', 'http://127.0.0.1:8100')
USER = os.environ.get('TAPD_USER', 'admin')
PWD = os.environ.get('TAPD_PWD', 'At159357')
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = int(os.environ.get('TREE_CDP_PORT', '9390'))

PASS = 0
FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS ' + msg)
    else:
        FAIL += 1
        print('  FAIL ' + msg)


def start_chrome():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--no-default-browser-check', '--remote-debugging-port=%d' % PORT,
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
                return True
        except Exception:
            time.sleep(0.5)
    return False


def kill_chrome():
    subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# 读取树弹窗当前状态
STATE_JS = """(function(){
    var p = TREE_PICK && TREE_PICK.panel;
    if(!p) return {err:'no panel'};
    var vis=0, hid=0;
    p.querySelectorAll('[id^=tp_children_]').forEach(function(d){
        if(d.style.display==='none') hid++; else vis++;
    });
    // 顶层节点：treePickNodes 渲染时 padding-left = dep*16px，dep=0 即顶层
    var tops=[].slice.call(p.querySelectorAll('.tp-node')).filter(function(e){
        var pl=e.style.paddingLeft||'';
        return pl===''||pl==='0px';
    });
    var noneOpt=document.getElementById('tp_opt_none');
    return {
        expanded: TREE_PICK.expanded.size,
        visContainers: vis, hidContainers: hid,
        topLevelCount: tops.length,
        noneNode: !!p.querySelector('.tp-none-node'),
        noneChecked: noneOpt ? noneOpt.checked : null,
        selected: [...TREE_PICK.selected],
        toolBtns: [].slice.call(p.querySelectorAll('.tp-tool-btn')).map(function(b){return b.textContent.trim();}),
    };
})()"""


async def main():
    if not start_chrome():
        print('无法启动 Chrome')
        return 1
    targets = json.loads(urllib.request.urlopen(
        'http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    import websockets
    async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
        mid = 0

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            m = mid
            await ws.send(json.dumps({'id': m, 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get('id') == m:
                    return msg.get('result', {})

        async def ev(expr, aw=False):
            r = await send('Runtime.evaluate', {'expression': expr, 'returnByValue': True,
                                                'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:400]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        # 固定视口：headless 默认 ~800px 会触发响应式断点，影响布局断言
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                 "document.getElementById('btn').click();" % (json.dumps(USER), json.dumps(PWD)))
        await asyncio.sleep(5)

        # ---------- 用例 1：顶部工具栏 ----------
        print('\n【用例1】树弹窗顶部工具栏')
        await ev("document.getElementById('personFilterInput').click();")
        await asyncio.sleep(2.5)
        r = await ev(STATE_JS)
        ok(r.get('toolBtns') == ['展开全部', '折叠全部'],
           '工具栏含「展开全部 / 折叠全部」：%s' % (r.get('toolBtns')))
        ok(r.get('topLevelCount', 0) >= 1,
           '树有顶层节点可见：%s 个' % r.get('topLevelCount'))

        # ---------- 用例 2：一键展开全部（多级） ----------
        print('\n【用例2】一键展开全部（多级批量）')
        before = await ev(STATE_JS)
        await ev("(function(){var b=[...TREE_PICK.panel.querySelectorAll('.tp-tool-btn')]"
                 ".find(function(x){return x.textContent.trim()==='展开全部'});b.click();})()")
        await asyncio.sleep(1.5)
        after = await ev(STATE_JS)
        ok(after.get('expanded', 0) > before.get('expanded', 0),
           '展开数增加：%s → %s' % (before.get('expanded'), after.get('expanded')))
        ok(after.get('hidContainers') == 0,
           '所有层级子容器都展开（隐藏数=0，实际 %s）' % after.get('hidContainers'))
        ok(after.get('visContainers') >= 2,
           '多级节点均展开（可见容器 %s 个）' % after.get('visContainers'))

        # ---------- 用例 3：一键折叠全部（保留顶层可见） ----------
        print('\n【用例3】一键折叠全部（保留顶层节点可见）')
        await ev("(function(){var b=[...TREE_PICK.panel.querySelectorAll('.tp-tool-btn')]"
                 ".find(function(x){return x.textContent.trim()==='折叠全部'});b.click();})()")
        await asyncio.sleep(1.5)
        r = await ev(STATE_JS)
        ok(r.get('expanded') == 0, '展开数清零：%s' % r.get('expanded'))
        ok(r.get('visContainers') == 0, '所有子容器收起（可见容器 %s）' % r.get('visContainers'))
        ok(r.get('topLevelCount', 0) >= 1,
           '折叠后顶层节点仍可见：%s 个' % r.get('topLevelCount'))

        # ---------- 用例 4：「无负责人」独立选项 ----------
        print('\n【用例4】「无负责人」作为独立显示选项')
        r = await ev(STATE_JS)
        ok(r.get('noneNode') is False, '默认未启用时树上不出现「无负责人」节点')
        ok(r.get('noneChecked') is False, '「无负责人」选项默认关闭')
        await ev("document.getElementById('tp_opt_none').click();")
        await asyncio.sleep(1.5)
        r = await ev(STATE_JS)
        ok(r.get('noneNode') is True, '启用后树上出现「无负责人」标签节点')
        ok(r.get('noneChecked') is True, '「无负责人」选项已勾选')
        ok('__no_owner__' in (r.get('selected') or []),
           '「无负责人」进入选中集合：%s' % (r.get('selected') or []))

        # ---------- 用例 5：展开/折叠与筛选条件互不影响 ----------
        print('\n【用例5】展开/折叠状态与筛选条件互不影响')
        await ev("(function(){var b=[...TREE_PICK.panel.querySelectorAll('.tp-tool-btn')]"
                 ".find(function(x){return x.textContent.trim()==='展开全部'});b.click();})()")
        await asyncio.sleep(1.5)
        r1 = await ev(STATE_JS)
        ok(r1.get('expanded', 0) > 0, '展开全部后展开数 > 0：%s' % r1.get('expanded'))
        ok('__no_owner__' in (r1.get('selected') or []),
           '展开操作未清掉「无负责人」筛选条件')
        await ev("(function(){var b=[...TREE_PICK.panel.querySelectorAll('.tp-tool-btn')]"
                 ".find(function(x){return x.textContent.trim()==='折叠全部'});b.click();})()")
        await asyncio.sleep(1.5)
        r2 = await ev(STATE_JS)
        ok(r2.get('expanded') == 0, '折叠全部后展开数 = 0：%s' % r2.get('expanded'))
        ok('__no_owner__' in (r2.get('selected') or []),
           '折叠操作未清掉「无负责人」筛选条件')

        # ---------- 用例 6：确认后真正筛出负责人为空的事项 ----------
        print('\n【用例6】确认后「无负责人」真正生效')
        await ev("treePickConfirm();")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
            var rows=[].slice.call(document.querySelectorAll('.item-card'));
            var owners=rows.map(function(e){
                var f=e.querySelector('.fcol-owner');
                return f?f.textContent.replace(/^负责人：/,'').trim():'';
            });
            return {personSel:[...PERSON_SEL],
                    chips:(document.getElementById('personFilterChips')||{}).textContent||'',
                    hint:(document.getElementById('filterHint')||{}).textContent||'',
                    rowCount:rows.length,
                    allEmpty:owners.every(function(o){return !o||o==='—';})};
        })()""")
        ok('__no_owner__' in (r.get('personSel') or []),
           '「无负责人」已写入 PERSON_SEL：%s' % (r.get('personSel') or []))
        ok('无负责人' in (r.get('chips') or ''), 'chips 显示「无负责人」：%s' % (r.get('chips') or ''))
        ok('无负责人' in (r.get('hint') or ''), '顶部提示显示「无负责人」：%s' % (r.get('hint') or ''))
        ok(r.get('rowCount', 0) > 0, '筛出 %s 条事项' % r.get('rowCount'))
        ok(r.get('allEmpty') is True, '筛出的事项负责人全部为空')

        # ---------- 用例 7：筛选栏人员控件 = 架构树单一入口 ----------
        print('\n【用例7】筛选栏人员控件只有架构树一个入口')
        await ev("closeTreePick();")
        await asyncio.sleep(0.5)
        r = await ev("""(function(){
            var w=document.getElementById('personFilterWrap');
            var inp=document.getElementById('personFilterInput');
            return {hasDrop:!!document.getElementById('personFilterDrop'),
                    hasTreeBtn:!!document.getElementById('personFilterTreeBtn'),
                    readonly:inp?inp.readOnly:null,
                    noneText:(w.innerText.match(/无负责人/g)||[]).length,
                    btnCount:w.querySelectorAll('button').length};
        })()""")
        ok(r.get('hasDrop') is False, '人员控件无候选下拉面板')
        ok(r.get('hasTreeBtn') is False, '人员控件右侧无独立的 🌳 按钮')
        ok(r.get('readonly') is True, '人员输入框为只读触发器（点击直接开树）')
        ok(r.get('btnCount') == 0, '人员控件内无任何按钮')
        # ⚠️ 用例6 刚勾选了「无负责人」，此时它会作为 chip 显示在人员控件里 ——
        #    这是正确的（已选条件可见），不是"控件上出现该文案"的问题。
        #    这里只验证：控件的**静态部分**（label / placeholder）不含该文案。
        r2 = await ev("""(function(){
            var w=document.getElementById('personFilterWrap');
            var label=(w.querySelector('.cf-label')||{}).textContent||'';
            var ph=document.getElementById('personFilterInput').placeholder||'';
            return {label:label, ph:ph,
                    chipCount:w.querySelectorAll('#personFilterChips .cf-chip').length};
        })()""")
        ok('无负责人' not in (r2.get('label') or '') and '无负责人' not in (r2.get('ph') or ''),
           '人员控件的标签/占位符不含「无负责人」：%s / %s' % (r2.get('label'), r2.get('ph')))

        # 点击输入框 → 树弹窗（含搜索框）
        await ev("document.getElementById('personFilterInput').click();")
        await asyncio.sleep(2.0)
        r = await ev("""(function(){
            var p=TREE_PICK&&TREE_PICK.panel;
            return {opened:!!p, search:!!document.getElementById('tp_search'),
                    persons:p?p.querySelectorAll('.tp-person').length:0};
        })()""")
        ok(r.get('opened') is True, '点击人员输入框 → 直接打开架构树')
        ok(r.get('search') is True, '树内有搜索框（承接原下拉面板的输入匹配能力）')
        ok(r.get('persons', 0) > 0, '树上渲染出末级人员：%s' % r.get('persons'))

        # 树内搜索（走真实 input 事件，与用户打字路径一致）
        await ev("""(function(){
            var i=document.getElementById('tp_search');
            i.focus(); i.value='吴';
            i.dispatchEvent(new Event('input',{bubbles:true}));
        })()""")
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
            var p=TREE_PICK.panel;
            return {persons:p.querySelectorAll('.tp-person').length,
                    nodeRows:p.querySelectorAll('.tp-node:not(.tp-person)').length,
                    names:[].slice.call(p.querySelectorAll('.tp-person')).map(function(e){
                        return e.textContent.replace(/👤/g,'').trim().split('（')[0].trim();})};
        })()""")
        ok(r.get('persons', 0) > 0 and r.get('persons') < 36,
           '搜索「吴」过滤出 %s 人（全部 %s 人）' % (r.get('persons'), 36))
        ok(all('吴' in n for n in (r.get('names') or [])), '过滤结果均含关键字：%s' % (r.get('names') or []))

        # 无匹配 → 空态提示
        await ev("""(function(){
            var i=document.getElementById('tp_search');
            i.focus(); i.value='不存在的名字';
            i.dispatchEvent(new Event('input',{bubbles:true}));
        })()""")
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
            var p=TREE_PICK.panel;
            return {persons:p.querySelectorAll('.tp-person').length,
                    nodeRows:p.querySelectorAll('.tp-node:not(.tp-person)').length,
                    empty:(p.querySelector('.tp-empty')||{}).textContent||''};
        })()""")
        ok(r.get('persons') == 0, '无匹配时没有人员条目')
        ok(r.get('nodeRows') == 0, '无匹配时不残留空节点行')
        ok('未匹配到' in (r.get('empty') or ''), '无匹配时显示空态提示：%s' % (r.get('empty') or ''))

        # ---------- 用例 8：中文输入法（IME）兼容 ----------
        print('\n【用例8】搜索框支持中文输入法（IME）')
        # 记录搜索框 DOM 节点，验证输入过程中节点不被替换
        await ev("""(function(){
            var i=document.getElementById('tp_search');
            i.focus(); i.value='';
            i.dispatchEvent(new Event('input',{bubbles:true}));
            window.__tpNode=i;
            window.__tpLog=[];
            ['compositionstart','compositionend','input'].forEach(function(t){
                i.addEventListener(t,function(e){
                    window.__tpLog.push(t+':'+(e.isComposing===undefined?'':e.isComposing));
                });
            });
        })()""")
        await asyncio.sleep(0.8)
        # 真实 IME 序列：imeSetComposition 建立拼音组合（不提交）→ insertText 上屏汉字
        await send('Input.imeSetComposition', {'text': 'wuting', 'selectionStart': 6, 'selectionEnd': 6})
        await asyncio.sleep(0.8)
        r = await ev("""(function(){
            var i=document.getElementById('tp_search');
            return {value:i.value, keyword:TREE_PICK.keyword,
                    persons:TREE_PICK.panel.querySelectorAll('.tp-person').length,
                    sameNode:document.getElementById('tp_search')===window.__tpNode,
                    focused:document.activeElement.id,
                    log:window.__tpLog};
        })()""")
        ok(r.get('sameNode') is True, '拼音组合期间搜索框 DOM 节点未被替换')
        ok(r.get('focused') == 'tp_search', '拼音组合期间输入框保持焦点')
        ok(r.get('keyword') == '', '拼音组合期间不触发过滤（keyword 仍为空）')
        ok(r.get('persons', 0) == 36, '拼音组合期间树上人员不消失（仍 %s 人）' % r.get('persons'))
        # 上屏汉字 → 正常过滤
        await send('Input.insertText', {'text': '吴婷婷'})
        await asyncio.sleep(1.0)
        r = await ev("""(function(){
            var i=document.getElementById('tp_search');
            return {value:i.value, keyword:TREE_PICK.keyword,
                    persons:TREE_PICK.panel.querySelectorAll('.tp-person').length,
                    names:[].slice.call(TREE_PICK.panel.querySelectorAll('.tp-person')).map(function(e){
                        return e.textContent.replace(/👤/g,'').trim().split('（')[0].trim();}),
                    sameNode:document.getElementById('tp_search')===window.__tpNode,
                    focused:document.activeElement.id,
                    log:window.__tpLog};
        })()""")
        ok(r.get('sameNode') is True, '上屏后搜索框 DOM 节点仍未被替换')
        ok(r.get('focused') == 'tp_search', '上屏后输入框仍保持焦点')
        ok('吴婷婷' in (r.get('value') or ''), '汉字已正常上屏：%s' % (r.get('value') or ''))
        ok(r.get('keyword') == '吴婷婷', '上屏后按汉字过滤：%s' % (r.get('keyword') or ''))
        ok(r.get('persons', 0) >= 1, '上屏后过滤出 %s 人' % r.get('persons'))
        ok(all('吴婷婷' in n for n in (r.get('names') or [])),
           '过滤结果均为该人员：%s' % (r.get('names') or []))

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        kill_chrome()
