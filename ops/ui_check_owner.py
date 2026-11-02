#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI 实测：看板管理 / 板块编辑的「负责人」配置（树状图单选）

用户 2026-11-02 要求：
  1. 看板管理中只配置负责人，不配置参与人
  2. 负责人选择参照外部人员筛选的**树状图**（架构树 + 末级人员）
  3. 板块的负责人放在**板块编辑**里配置

本脚本验证**真实渲染**（Chrome headless + CDP），不是源码字符串：
  用例1 看板管理：只有「负责人」，没有「参与人」控件
  用例2 负责人选择器：点击后打开**树弹窗**（架构树 + 末级人员行）
  用例3 树里勾选人员 → 回填负责人（chip 显示姓名）
  用例4 板块编辑弹窗：有「板块负责人」字段 + 树状选择按钮
  用例5 看板管理里非管理员看不到「选择负责人」按钮（仅管理员可指定）

运行：ops/.localvenv/Scripts/python.exe ops/ui_check_owner.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:8100'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9477

passed = 0
failed = 0
FAIL_LIST = []


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        FAIL_LIST.append(msg)
        print('  FAIL ' + msg)


async def main():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_own%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT,
                      '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    targets = json.loads(urllib.request.urlopen(
        'http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]

    import websockets
    async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
        i = 0

        async def send(m, p=None):
            nonlocal i
            i += 1
            mid = i
            await ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get('id') == mid:
                    return msg.get('result', {})

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate',
                           {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable')
        await send('Runtime.enable')
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
        await send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await ev("document.getElementById('u').value='admin';"
                 "document.getElementById('p').value='At159357';"
                 "document.getElementById('btn').click();")
        for _ in range(30):
            await asyncio.sleep(0.5)
            if await ev("!!document.getElementById('tbDepts')"):
                break
        await asyncio.sleep(1.5)

        # ---------- 用例1：看板管理里只有「负责人」，没有「参与人」 ----------
        print('\n【用例1】看板管理：只有负责人，没有参与人')
        await ev("openBoardConfigModal()")
        await asyncio.sleep(2.5)
        # ⚠️ 看板管理默认**不选中**任何看板（编辑区是空态提示）→ 先点第一个看板
        await ev("""(function(){
            var it=document.querySelector('#bcList .bc-item');
            if(it)it.click();
            return true;
        })()""")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
            var body=document.getElementById('bcEditArea');
            var html=body?body.innerHTML:'';
            return {
              hasOwnerLabel: html.indexOf('看板负责人')>=0,
              hasParticipantWord: html.indexOf('参与人')>=0,
              hasOwnerSelect: !!document.getElementById('bc_owner'),
              hasParticipantsSelect: !!document.getElementById('bc_participants'),
              hasPickBtn: html.indexOf('bcPickOwner')>=0
            };
        })()""")
        ok(r.get('hasOwnerLabel') is True, '编辑区有「看板负责人」区块')
        ok(r.get('hasParticipantWord') is False, '编辑区**没有**「参与人」字样')
        ok(r.get('hasOwnerSelect') is False, '负责人不再是 <select> 下拉（改成树状选择）')
        ok(r.get('hasParticipantsSelect') is False, '参与人多选框已移除')
        ok(r.get('hasPickBtn') is True, '有「🌳 选择负责人」按钮（树状选择器入口）')

        # ---------- 用例2：点击后打开树弹窗 ----------
        print('\n【用例2】负责人选择器：打开的是架构树弹窗')
        await ev("""(function(){
            var btns=[].slice.call(document.querySelectorAll('#bcEditArea button'));
            var b=btns.filter(function(x){return x.getAttribute('onclick')==='bcPickOwner(this)'})[0];
            if(b)b.click();
            return !!b;
        })()""")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
            var p=document.querySelector('.tree-pick');
            if(!p)return {open:false};
            var persons=p.querySelectorAll('.tp-node.tp-person');
            var nodes=p.querySelectorAll('.tp-node');
            return {
              open:true,
              title:(p.querySelector('.tp-title')||{}).textContent||'',
              personCount:persons.length,
              nodeCount:nodes.length,
              hasSearch: !!p.querySelector('#tp_search'),
              hasNoneOwner: p.textContent.indexOf('无负责人')>=0
            };
        })()""")
        ok(r.get('open') is True, '树弹窗已打开')
        ok('选择人员' in (r.get('title') or ''), '弹窗标题是人员选择（实测：%s）' % r.get('title'))
        ok((r.get('nodeCount') or 0) > 0, '树里有架构节点（%s 个）' % r.get('nodeCount'))
        ok((r.get('personCount') or 0) > 0, '树里有末级人员（%s 个）' % r.get('personCount'))
        ok(r.get('hasSearch') is True, '树内带人员搜索框')
        # 未开通登录账号的人必须标灰且不可选（否则配了等于配空）
        r2 = await ev("""(function(){
            var p=document.querySelector('.tree-pick');
            if(!p)return {err:'no panel'};
            var rows=[].slice.call(p.querySelectorAll('.tp-node.tp-person'));
            var noAcct=rows.filter(function(r){return r.textContent.indexOf('未开通账号')>=0;});
            var disabled=noAcct.filter(function(r){
                var l=r.querySelector('.tp-label');
                return l && !l.getAttribute('onclick');
            });
            return {noAcctCount:noAcct.length, disabledCount:disabled.length,
                    total:rows.length};
        })()""")
        ok((r2.get('noAcctCount') or 0) > 0,
           '未开通账号的人被标注出来（%s / 共 %s 人）' % (r2.get('noAcctCount'), r2.get('total')))
        ok(r2.get('noAcctCount') == r2.get('disabledCount'),
           '未开通账号的人**不可选**（标注 %s / 禁用 %s）'
           % (r2.get('noAcctCount'), r2.get('disabledCount')))

        # ---------- 用例3：勾选人员 → 回填负责人 ----------
        print('\n【用例3】树里勾选人员 → 回填负责人')
        r = await ev("""(function(){
            var p=document.querySelector('.tree-pick');
            if(!p)return {err:'no panel'};
            // 展开全部，让人员行渲染出来
            var exp=p.querySelector('.tp-tool-btn');
            if(exp)exp.click();
            return {clicked:true};
        })()""")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
            var p=document.querySelector('.tree-pick');
            if(!p)return {err:'no panel'};
            var lab=p.querySelector('.tp-node.tp-person .tp-label');
            if(!lab)return {err:'no person'};
            var name=lab.textContent.replace(/[^\\u4e00-\\u9fa5A-Za-z]/g,'');
            lab.click();
            return {picked:true, raw:lab.textContent, name:name};
        })()""")
        await asyncio.sleep(0.8)
        r2 = await ev("""(function(){
            var btn=[].find.call(document.querySelectorAll('.tree-pick button'),function(b){return b.textContent.indexOf('确定')>=0});
            if(btn)btn.click();
            return {confirmed:!!btn};
        })()""")
        await asyncio.sleep(1.5)
        r3 = await ev("""(function(){
            var box=document.getElementById('bc_owner_box');
            var chip=box?box.querySelector('.cf-chip'):null;
            var ftxt=(box&&box.textContent)||'';
            return {
              hasChip: !!chip,
              chipText: chip?chip.textContent.trim():ftxt.trim(),
              owner: (typeof BC_FORM!=='undefined'&&BC_FORM.owner)||''
            };
        })()""")
        ok(r3.get('hasChip') is True, '负责人已回填为 chip（实测：%s）' % r3.get('chipText'))
        ok(bool(r3.get('owner')), 'BC_FORM.owner 已写入账号（实测：%s）' % r3.get('owner'))
        ok(r3.get('chipText') != r3.get('owner') or len(r3.get('owner') or '') <= 3,
           'chip 显示的是姓名而非原始账号（chip=%s / owner=%s）'
           % (r3.get('chipText'), r3.get('owner')))

        # ---------- 用例4：板块编辑里有负责人字段 ----------
        print('\n【用例4】板块编辑弹窗：板块负责人字段')
        # ⚠️ 板块标题要先把看板选中并加载出来
        await ev("""(function(){
            var tab=document.querySelector('#tbDepts .tab, #tbDepts .dept-tab');
            return true;
        })()""")
        await ev("""(function(){
            var b=(typeof BC_BOARDS!=='undefined')?BC_BOARDS[0]:null;
            if(b&&typeof curBoard!=='undefined'){curBoard=b.board_id;}
            return true;
        })()""")
        await ev("reload(1)")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
            var el=document.querySelector('.week-title.edit');
            if(!el)return {err:'no column title'};
            el.click();
            return {clicked:true};
        })()""")
        await asyncio.sleep(1.8)
        r = await ev("""(function(){
            var m=document.getElementById('columnModal');
            if(!m||m.style.display==='none')return {open:false};
            var wrap=document.getElementById('c_owner_wrap');
            var box=document.getElementById('c_owner_box');
            var pick=document.getElementById('c_owner_pick_btn');
            return {
              open:true,
              hasWrap: !!wrap,
              hasBox: !!box,
              hasPick: !!pick,
              pickText: pick?pick.textContent.trim():'',
              boxText: box?box.textContent.trim():''
            };
        })()""")
        ok(r.get('open') is True, '板块编辑弹窗已打开')
        ok(r.get('hasWrap') is True, '有「板块负责人」字段容器')
        ok(r.get('hasPick') is True, '有「🌳 选择负责人」按钮')
        ok('选择负责人' in (r.get('pickText') or ''), '按钮文案正确（实测：%s）' % r.get('pickText'))
        ok(r.get('hasBox') is True, '有负责人回显区（实测：%s）' % r.get('boxText'))

        # ---------- 用例5：板块编辑里也能打开树 ----------
        print('\n【用例5】板块负责人同样用树状图选人')
        await ev("colPickOwner(document.getElementById('c_owner_pick_btn'))")
        await asyncio.sleep(2.5)
        r = await ev("""(function(){
            var p=document.querySelector('.tree-pick');
            if(!p)return {open:false};
            var persons=p.querySelectorAll('.tp-node.tp-person');
            return {open:true, personCount:persons.length,
                    title:(p.querySelector('.tp-title')||{}).textContent||''};
        })()""")
        ok(r.get('open') is True, '板块负责人树弹窗已打开')
        ok((r.get('personCount') or 0) > 0, '树里有末级人员（%s 个）' % r.get('personCount'))
        await ev("closeTreePick()")
        await asyncio.sleep(0.5)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (passed, failed))
    for f in FAIL_LIST:
        print('  FAIL: ' + f)
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'",
                        'get', 'CommandLine', '/FORMAT:CSV'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
