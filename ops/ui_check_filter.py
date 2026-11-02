#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""筛选栏 + 顶部栏布局专项验证（Chrome headless + CDP）。

覆盖：
  1) 人员筛选是可输入 + 多选控件；周数筛选是可输入 + 多选控件
  2) 人员筛选锚定在负责人维度：与负责人下拉**互不覆盖**，服务端取交集
  3) 人员树状展开/收起：人员随父节点折叠、展开状态跨弹窗保持、父节点级联三态
  4) 顶部栏左右分栏：左半三列多行（部门/板块/统计），右半公告独立区
运行：python ops/ui_check_filter.py [用户名 密码]
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9341
BASE = 'http://127.0.0.1:8100'
USER = sys.argv[1] if len(sys.argv) > 1 else 'admin'
PWD = sys.argv[2] if len(sys.argv) > 2 else 'At159357'

PASS, FAIL = [], []


def ok(cond, msg):
    if cond:
        PASS.append(msg); print('  ✓ ' + msg)
    else:
        FAIL.append(msg); print('  ✗ ' + msg)


def start_chrome():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read()); return True
        except Exception:
            time.sleep(0.5)
    return False


def kill_chrome():
    subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                    '/FORMAT:CSV'], capture_output=True, text=True)
    out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine',
                          '/FORMAT:CSV'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'cdp_profile' in line:
            pid = line.strip().split(',')[-1].strip()
            if pid.isdigit():
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)


async def main():
    if not start_chrome():
        print('Chrome 启动失败'); return 1
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]

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

        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': str(r['exceptionDetails'])[:300]}
            return r.get('result', {}).get('value')

        await send('Page.enable'); await send('Runtime.enable')
        # 固定视口宽度：headless 默认窗口只有 ~800px，会触发 900px 断点（单栏），
        # 导致「两栏/三列」的断言全部误判为失败
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
        await asyncio.sleep(1.5)

        # ================= 用例 1：顶部栏左右分栏 =================
        print('\n【用例1】顶部栏左右分栏 + 三列多行')
        r = await ev("""(function(){
            var top=document.getElementById('topbar');
            if(!top)return {none:true};
            var cs=getComputedStyle(top);
            var main_=document.getElementById('boardTabs');
            var aside=document.getElementById('topbarAside');
            var mc=main_?getComputedStyle(main_):null;
            var d=document.getElementById('tbDepts'), b=document.getElementById('tbBoards');
            var dc=d?getComputedStyle(d):null, bc=b?getComputedStyle(b):null;
            var stat=document.getElementById('progressOverview');
            var sc=stat?getComputedStyle(stat):null;
            var mainRect=main_?main_.getBoundingClientRect():null;
            var asideRect=aside?aside.getBoundingClientRect():null;
            return {
              topCols:cs.gridTemplateColumns,
              mainCols:mc?mc.gridTemplateColumns:'',
              deptCols:dc?dc.gridTemplateColumns:'',
              boardCols:bc?bc.gridTemplateColumns:'',
              statCols:sc?sc.gridTemplateColumns:'',
              bands:document.querySelectorAll('.tb-band').length,
              statCards:document.querySelectorAll('#progressOverview .stat-card').length,
              noticeExists:!!document.getElementById('noticeBar'),
              noticeInAside:!!(aside&&document.getElementById('noticeBar')&&aside.contains(document.getElementById('noticeBar'))),
              sideBySide:(mainRect&&asideRect)?(asideRect.left>=mainRect.right-2):false,
              mainW:mainRect?Math.round(mainRect.width):0,
              asideW:asideRect?Math.round(asideRect.width):0,
            };
        })()""")
        if isinstance(r, dict) and r.get('__error__'):
            print('  （诊断）' + r['__error__'])
        cols = (r.get('topCols') or '').split()
        ok(len(cols) == 2, '顶部栏为左右两栏：%s' % r.get('topCols'))
        ok(r.get('bands') == 3, '左半三「带」（部门/板块/统计）：%s' % r.get('bands'))
        ok(len((r.get('mainCols') or '').split()) == 3, '左半主区为三列：%s' % r.get('mainCols'))
        ok(len((r.get('deptCols') or '').split()) == 3, '部门带为三列：%s' % r.get('deptCols'))
        ok(len((r.get('boardCols') or '').split()) == 3, '板块带为三列：%s' % r.get('boardCols'))
        ok(len((r.get('statCols') or '').split()) == 3, '统计带为三列：%s' % r.get('statCols'))
        ok(r.get('statCards') == 3, '统计带 3 张卡片：%s' % r.get('statCards'))
        ok(r.get('noticeInAside') is True, '公告区在右半独立容器内')
        ok(r.get('sideBySide') is True, '右半公告区与左半主体左右并排（left=%s right=%s）'
           % (r.get('mainW'), r.get('asideW')))

        # ================= 用例 2：筛选控件为可输入 + 多选 =================
        print('\n【用例2】人员/周数筛选为可输入多选控件')
        r = await ev("""(function(){
            var pi=document.getElementById('personFilterInput');
            var wi=document.getElementById('weekFilterInput');
            var pd=document.getElementById('personFilterDrop');
            var wd=document.getElementById('weekFilterDrop');
            return {
              pInput:!!pi, pType:pi?pi.tagName:'', pPlaceholder:pi?pi.placeholder:'',
              wInput:!!wi, wType:wi?wi.tagName:'', wPlaceholder:wi?wi.placeholder:'',
              pDrop:!!pd, wDrop:!!wd,
              pChips:!!document.getElementById('personFilterChips'),
              wChips:!!document.getElementById('weekFilterChips'),
              hasInputFilter:!!document.querySelector('.cf-input'),
              oldPersonBtn:!!document.getElementById('personFilterBtn'),
              oldWeekBtn:!!document.getElementById('weekFilterBtn'),
            };
        })()""")
        ok(r.get('pInput') is True and r.get('pType') == 'INPUT', '人员筛选是可输入控件（input）')
        ok(r.get('wInput') is True and r.get('wType') == 'INPUT', '周数筛选是可输入控件（input）')
        ok('姓名' in (r.get('pPlaceholder') or ''), '人员输入框提示支持输入：%s' % r.get('pPlaceholder'))
        ok('41' in (r.get('wPlaceholder') or ''), '周数输入框提示支持数字输入：%s' % r.get('wPlaceholder'))
        ok(r.get('pDrop') is True and r.get('wDrop') is True, '两者都有候选下拉面板（多选）')
        ok(r.get('pChips') is True and r.get('wChips') is True, '两者都有已选 chips 展示（多选）')
        ok(r.get('oldPersonBtn') is False and r.get('oldWeekBtn') is False, '旧的纯下拉按钮已移除')

        # 打开人员下拉 → 应列出候选（来自接口）
        # 用 click() 而非 focus()：headless 下窗口未激活，focus() 不派发 focus 事件
        await ev("document.getElementById('personFilterInput').click();")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
            var d=document.getElementById('personFilterDrop');
            return {hidden:d?d.hidden:null, opts:d?d.querySelectorAll('.cf-opt').length:0,
                    tip:d?(d.querySelector('.cf-tip')||{}).textContent||'':''};
        })()""")
        ok(r.get('hidden') is False, '聚焦后人员候选面板展开')
        ok(r.get('opts', 0) > 0, '人员候选有可勾选项：%s' % r.get('opts'))
        ok('负责人' in (r.get('tip') or ''), '提示说明按「负责人」维度生效：%s' % (r.get('tip') or '')[:40])

        # 输入过滤
        await ev("(function(){var i=document.getElementById('personFilterInput');i.value='__不存在的名字__';i.dispatchEvent(new Event('input'));})()")
        await asyncio.sleep(0.6)
        r = await ev("""(function(){
            var d=document.getElementById('personFilterDrop');
            return {opts:d?d.querySelectorAll('.cf-opt').length:0,
                    empty:d?(d.querySelector('.cf-empty')||{}).textContent||'':''};
        })()""")
        ok(r.get('opts', 0) == 0 and '无匹配' in (r.get('empty') or ''),
           '输入不存在的名字 → 候选清空并提示无匹配：%s' % (r.get('empty') or ''))
        await ev("document.getElementById('personFilterInput').value='';")
        await ev("document.getElementById('personFilterInput').dispatchEvent(new Event('input'));")
        await asyncio.sleep(0.5)

        # 周数输入归一：41 → 2026年第41周
        r = await ev("(function(){return typeof normWeekInput==='function'?normWeekInput('41'):'__err__';})()")
        ok(r == '2026年第41周', '周数「41」归一为「2026年第41周」：%s' % r)
        r = await ev("(function(){return typeof normWeekInput==='function'?normWeekInput('2026-41'):'__err__';})()")
        ok(r == '2026年第41周', '周数「2026-41」归一为「2026年第41周」：%s' % r)
        r = await ev("(function(){return typeof normWeekInput==='function'?normWeekInput('2026年第41周'):'__err__';})()")
        ok(r == '2026年第41周', '周数「2026年第41周」保持不变：%s' % r)
        r = await ev("(function(){return typeof normWeekInput==='function'?normWeekInput('第99周'):'__err__';})()")
        ok(r == '', '非法周数被拒绝：%r' % r)

        # ================= 用例 3：独立的「全部负责人」下拉已下线 =================
        print('\n【用例3】「全部负责人」下拉下线，人员筛选独占负责人维度')
        r = await ev("""(function(){
            return {ownerFilterExists:!!document.getElementById('ownerFilter'),
                    ownerWords:(document.body.innerText.match(/全部负责人/g)||[]).length};
        })()""")
        ok(r.get('ownerFilterExists') is False, '筛选栏已无「全部负责人」下拉')
        ok(r.get('ownerWords') == 0, '页面上不再出现「全部负责人」文案')

        # 「无负责人」已从下拉面板移入【架构树】的「显示选项」→ 这里只验证下拉面板里没有它
        await ev("document.getElementById('personFilterInput').click();")
        await asyncio.sleep(1.2)
        r = await ev("""(function(){
            var d=document.getElementById('personFilterDrop');
            return {hasNone:!!d.querySelector('[data-pick-person="__no_owner__"]'),
                    noneText:(d.innerText.match(/无负责人/g)||[]).length};
        })()""")
        ok(r.get('hasNone') is False, '人员下拉面板里已无「无负责人」候选项（改由架构树承载）')
        ok(r.get('noneText') == 0, '人员下拉面板文案不含「无负责人」：%s 处' % r.get('noneText'))
        await ev("(function(){closeFilterCombo();})()")
        await asyncio.sleep(0.5)

        # reload() 提交 person 参数；不再提交 owner 参数
        r = await ev("""(function(){
            return {hasPerson:typeof PERSON_SEL!=='undefined',
                    src:(function(){
                        try{return String(reload).indexOf("ps.set('person'")>=0;}catch(e){return false;}
                    })(),
                    noOwner:(function(){
                        try{return String(reload).indexOf("ps.set('owner'")<0;}catch(e){return false;}
                    })()};
        })()""")
        ok(r.get('src') is True, 'reload() 提交 person 参数（锚定 owner 字段）')
        ok(r.get('noOwner') is True, 'reload() 不再提交 owner 参数（下拉已下线）')

        await ev("PERSON_SEL=new Set();reload(1);")
        await asyncio.sleep(0.8)

        # ================= 用例 4：人员树状展开 =================
        print('\n【用例4】人员树状展开/收起与状态同步')
        await ev("document.getElementById('personFilterTreeBtn').click();")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
            if(!TREE_PICK)return {none:true};
            var p=TREE_PICK.panel;
            var nodes=p.querySelectorAll('.tp-node');
            var persons=p.querySelectorAll('.tp-person');
            // 每个节点的容器与其显示状态
            var rows=[];
            p.querySelectorAll('[id^="tp_children_"]').forEach(function(c){
                rows.push({id:c.id,disp:c.style.display,
                           persons:c.querySelectorAll('.tp-person').length});
            });
            return {open:!!TREE_PICK, nodes:nodes.length, persons:persons.length,
                    rows:rows.slice(0,8),
                    nodeBoxes:p.querySelectorAll('.tp-box-node').length,
                    naBoxes:p.querySelectorAll('.tp-box-na').length};
        })()""")
        if isinstance(r, dict) and r.get('__error__'):
            print('  （诊断）' + r['__error__'])
        ok(r.get('open') is True, '人员树选择器已打开')
        ok(r.get('persons', 0) > 0, '树上渲染出人员条目：%s' % r.get('persons'))
        ok(r.get('naBoxes') == 0, '节点框不再置灰（父节点可点）')
        ok(r.get('nodeBoxes', 0) > 0, '节点框使用可点击样式：%s' % r.get('nodeBoxes'))

        # 人员必须**在可折叠容器内**（否则折叠父节点时人员不会消失 → 展开异常）
        r = await ev("""(function(){
            var p=TREE_PICK.panel;
            var orphan=0, total=0;
            p.querySelectorAll('.tp-person').forEach(function(el){
                total++;
                // 向上找最近的 tp_children_ 容器
                var inBox=false, node=el.parentNode;
                while(node&&node!==p){
                    if(node.id&&node.id.indexOf('tp_children_')===0){inBox=true;break;}
                    node=node.parentNode;
                }
                if(!inBox)orphan++;
            });
            return {total:total,orphan:orphan};
        })()""")
        ok(r.get('orphan') == 0, '人员条目全部位于可折叠容器内（折叠时随父节点隐藏）：%s' % r)

        # 展开 → 折叠：人员可见性应随之变化
        r = await ev("""(function(){
            var p=TREE_PICK.panel;
            var first=null;
            p.querySelectorAll('.tp-arrow[id^="tp_arrow_"]').forEach(function(a){ if(!first)first=a; });
            if(!first)return {none:true};
            var id=first.id.replace('tp_arrow_','');
            var box=document.getElementById('tp_children_'+id);
            var before=box?box.style.display:null;
            first.click();
            var after=box?box.style.display:null;
            return {id:id,before:before,after:after,
                    expanded:TREE_PICK?TREE_PICK.expanded.has(Number(id)):null,
                    globalExpanded:TREE_EXPANDED?TREE_EXPANDED.has(Number(id)):null};
        })()""")
        ok(r.get('before') != r.get('after'), '点击箭头可展开/收起（%s → %s）' % (r.get('before'), r.get('after')))
        ok(r.get('globalExpanded') is True, '展开状态写入全局存储（跨弹窗保持）')

        # 关闭再打开 → 展开状态应保持
        await ev("closeTreePick();")
        await asyncio.sleep(0.5)
        await ev("document.getElementById('personFilterTreeBtn').click();")
        await asyncio.sleep(1.5)
        r = await ev("""(function(){
            if(!TREE_PICK)return {none:true};
            var n=TREE_PICK.expanded.size;
            return {expandedCount:n};
        })()""")
        ok(r.get('expandedCount', 0) >= 1, '重开弹窗后展开状态仍保持：%s' % r.get('expandedCount'))

        # 父节点级联勾选 → 子节点三态
        r = await ev("""(function(){
            var p=TREE_PICK.panel;
            var nodeBox=null,nodeId=null;
            p.querySelectorAll('.tp-box-node').forEach(function(b){
                if(!nodeBox){nodeBox=b;nodeId=Number(b.id.replace('tp_box_',''));}
            });
            if(!nodeBox)return {none:true};
            var node=tpFindNode(nodeId);
            var under=tpPersonUnder(node);
            if(!under.length)return {none:true,noPerson:true};
            nodeBox.click();
            var selCount=TREE_PICK.selected.filter(function(x){return x.indexOf(ORG_PERSON_PREFIX)===0;}).length;
            var onBoxes=p.querySelectorAll('.tp-box.on[data-pbox]').length;
            var halfBoxes=p.querySelectorAll('.tp-box.half').length;
            // 再点一次 → 应取消
            nodeBox.click();
            var selCount2=TREE_PICK.selected.filter(function(x){return x.indexOf(ORG_PERSON_PREFIX)===0;}).length;
            return {under:under.length,selCount:selCount,onBoxes:onBoxes,halfBoxes:halfBoxes,
                    selCount2:selCount2};
        })()""")
        if isinstance(r, dict) and r.get('__error__'):
            print('  （诊断）' + r['__error__'])
        ok(r.get('selCount', 0) > 0, '父节点可级联勾选下属人员（选中 %s 人）' % r.get('selCount'))
        ok(r.get('onBoxes', 0) > 0, '勾选后人员框显示选中态：%s' % r.get('onBoxes'))
        ok(r.get('selCount2') == 0, '再次点击父节点 → 取消全部（%s）' % r.get('selCount2'))

        await ev("closeTreePick();")
        await asyncio.sleep(0.4)

        # ================= 用例 5：响应式断点 =================
        print('\n【用例5】响应式断点')
        for w, expect_cols, label in ((1440, 2, '宽屏 1440'), (1024, 2, '中屏 1024'), (700, 1, '窄屏 700')):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.6)
            rr = await ev("""(function(){
                var t=document.getElementById('topbar');
                var cs=getComputedStyle(t);
                var d=document.getElementById('tbDepts');
                return {top:cs.gridTemplateColumns,
                        dept:d?getComputedStyle(d).gridTemplateColumns:''};
            })()""")
            ncols = len((rr.get('top') or '').split())
            ok(ncols == expect_cols, '%s：顶部栏 %d 栏（实际 %s）' % (label, expect_cols, rr.get('top')))
        await send('Emulation.clearDeviceMetricsOverride')
        await asyncio.sleep(0.5)

        print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
        for f in FAIL:
            print('  FAIL: ' + f)
        return 1 if FAIL else 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        kill_chrome()
