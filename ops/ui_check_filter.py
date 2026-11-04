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
              navBands:document.querySelectorAll('.tb-navgroup .tb-band').length,
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
        # ⚠️ 2026-11-03（菜单顺序调整）：左半由三带变五带 ——
        #    架构部门 / 架构管理 / 可选看板 / 看板管理 / 统计概览
        #    （两个管理入口带插在各自内容带之后）
        # ⚠️ 2026-11-03：管理入口已并入各带的**标题行右侧**（.tb-band-head-entry），
        #    统计带已移到公告栏下方 → .tb-navgroup 内只有 2 条带（架构部门 / 可选看板）。
        ok(r.get('navBands') == 2, '导航区内两「带」（架构部门/可选看板）：%s' % r.get('navBands'))
        ok(len((r.get('mainCols') or '').split()) == 3, '左半主区为三列：%s' % r.get('mainCols'))
        ok(len((r.get('deptCols') or '').split()) == 3, '部门带为三列：%s' % r.get('deptCols'))
        ok(len((r.get('boardCols') or '').split()) == 3, '板块带为三列：%s' % r.get('boardCols'))
        ok(len((r.get('statCols') or '').split()) == 4, '统计带为四列（2026-11-04 增「进行中」卡）：%s' % r.get('statCols'))
        ok(r.get('statCards') == 4, '统计带 4 张卡片（2026-11-04 增「进行中」）：%s' % r.get('statCards'))
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
              pReadonly:pi?pi.readOnly:null,
              wInput:!!wi, wType:wi?wi.tagName:'', wPlaceholder:wi?wi.placeholder:'',
              pDrop:!!pd, wDrop:!!wd,
              pTreeBtn:!!document.getElementById('personFilterTreeBtn'),
              pChips:!!document.getElementById('personFilterChips'),
              wChips:!!document.getElementById('weekFilterChips'),
              hasInputFilter:!!document.querySelector('.cf-input'),
              pTitle:(document.getElementById('personFilterInput')||{}).title||'',
              pAria:(document.getElementById('personFilterInput')||{}).getAttribute
                     ?document.getElementById('personFilterInput').getAttribute('aria-label')||'':'',
              wTitle:(document.getElementById('weekFilterInput')||{}).title||'',
              wAria:(document.getElementById('weekFilterInput')||{}).getAttribute
                     ?document.getElementById('weekFilterInput').getAttribute('aria-label')||'':'',
              oldPersonBtn:!!document.getElementById('personFilterBtn'),
              oldWeekBtn:!!document.getElementById('weekFilterBtn'),
            };
        })()""")
        ok(r.get('pInput') is True and r.get('pType') == 'INPUT', '人员筛选是可输入控件（input）')
        ok(r.get('wInput') is True and r.get('wType') == 'INPUT', '周数筛选是可输入控件（input）')
        # ⚠️ 2026-11-03：placeholder 已清空（界面精简），提示改由 title / aria-label 承载
        ok('架构树' in ((r.get('pPlaceholder') or '') + (r.get('pTitle') or '') + (r.get('pAria') or '')),
           '人员输入框提示指向架构树：%s' % ((r.get('pTitle') or r.get('pPlaceholder') or '')))
        # ⚠️ 2026-11-03：周数提示由 aria-label 承载（placeholder/title 已清空）
        ok('数字' in ((r.get('wAria') or '') + (r.get('wTitle') or '') + (r.get('wPlaceholder') or '')),
           '周数输入框提示支持数字输入：%s' % ((r.get('wAria') or r.get('wTitle') or '')))
        # 人员筛选的入口已转移到架构树：没有下拉面板、没有独立的 🌳 按钮
        ok(r.get('pDrop') is False, '人员控件无候选下拉面板（入口=架构树）')
        ok(r.get('pTreeBtn') is False, '人员控件右侧的 🌳 按钮已移除')
        ok(r.get('pReadonly') is True, '人员输入框为只读触发器')
        ok(r.get('wDrop') is True, '周数控件有候选下拉面板（多选）')
        ok(r.get('pChips') is True and r.get('wChips') is True, '两者都有已选 chips 展示（多选）')
        ok(r.get('oldPersonBtn') is False and r.get('oldWeekBtn') is False, '旧的纯下拉按钮已移除')

        # 点击人员输入框 → 直接打开架构树弹窗（含搜索框）
        await ev("document.getElementById('personFilterInput').click();")
        await asyncio.sleep(2.0)
        r = await ev("""(function(){
            var p=TREE_PICK&&TREE_PICK.panel;
            return {opened:!!p,
                    search:!!document.getElementById('tp_search'),
                    persons:p?p.querySelectorAll('.tp-person').length:0,
                    optsBar:p?!!p.querySelector('.tp-opts'):false};
        })()""")
        ok(r.get('opened') is True, '点击人员输入框直接打开架构树弹窗')
        ok(r.get('search') is True, '树弹窗内有搜索框（按姓名筛选）')
        ok(r.get('persons', 0) > 0, '树上渲染出末级人员：%s' % r.get('persons'))
        ok(r.get('optsBar') is True, '树上有「显示选项」区（「无负责人」独立启用）')
        await ev("closeTreePick();")
        await asyncio.sleep(0.6)

        # ⚠️ 2026-11-04 #53：纯数字「41」已移除支持，格式统一「2026-41」
        r = await ev("(function(){return typeof normWeekInput==='function'?normWeekInput('41'):'__err__';})()")
        ok(r == '', '纯数字「41」不再归一（返回空）：%s' % r)
        r = await ev("(function(){return normWeekInput('2026-41');})()")
        ok(r == '2026年第41周', '「2026-41」归一为「2026年第41周」：%s' % r)
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

        # 「无负责人」在【架构树】的「显示选项」区 → 筛选栏本身不出现该文案
        r = await ev("""(function(){
            var w=document.getElementById('personFilterWrap');
            return {noneText:(w.innerText.match(/无负责人/g)||[]).length,
                    dropExists:!!document.getElementById('personFilterDrop')};
        })()""")
        ok(r.get('noneText') == 0, '人员控件上不出现「无负责人」文案：%s 处' % r.get('noneText'))
        ok(r.get('dropExists') is False, '人员控件已无候选下拉面板')

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
        await ev("document.getElementById('personFilterInput').click();")
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
            // ⚠️ 2026-11-04：弹窗现在**默认展开「财务中心」**→ 第一个箭头可能已是
            //    展开态（▼），点击会变成收起 → 全局位为 false 的假失败。
            //    改点第一个**收起态**（▶）的箭头，保证断言的是「展开写入全局」。
            var first=null;
            p.querySelectorAll('.tp-arrow[id^="tp_arrow_"]').forEach(function(a){
              if(!first&&a.textContent.indexOf('▶')>=0)first=a; });
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
        await ev("document.getElementById('personFilterInput').click();")
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
        # ⚠️ 需求5（2026-11-02）已废除「窄屏改变布局形态」策略，改为
        #    「窄屏锁定最小宽度 1200px + 横向滚动，所有元素大小位置不变」。
        #    → 旧断言「窄屏 700 → 顶部栏 1 栏」失效（同 T-002 根因）。
        #    → 现断言：**任何视口下顶部栏都保持 2 栏**（宽/中/窄一致）。
        print('\n【用例5】响应式断点（需求5 后：窄屏锁定宽度，栏数不变）')
        base_top = None
        for w, expect_cols, label in ((1440, 2, '宽屏 1440'), (1024, 2, '中屏 1024'),
                                       (700, 2, '窄屏 700'), (1600, 2, '宽屏 1600')):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.6)
            rr = await ev("""(function(){
                var t=document.getElementById('topbar');
                var cs=getComputedStyle(t);
                var d=document.getElementById('tbDepts');
                return {top:cs.gridTemplateColumns,
                        dept:d?getComputedStyle(d).gridTemplateColumns:'',
                        minW:getComputedStyle(document.documentElement).minWidth};
            })()""")
            ncols = len((rr.get('top') or '').split())
            ok(ncols == expect_cols, '%s：顶部栏 %d 栏（实际 %s）' % (label, expect_cols, rr.get('top')))
            if base_top is None:
                base_top = rr.get('top')
            if w < 1200:
                ok(rr.get('minW') == '1200px',
                   '%s：文档最小宽度锁定 1200px（实际 %s）' % (label, rr.get('minW')))
        # 窄屏（≤1199px）必须与 1200px 基准**完全一致** ——
        # 需求5 的核心诉求：窗口缩小后元素大小位置不变（不压缩、不变形）。
        # ⚠️ 1440px 不能当基准 —— @media(max-width:1440px) 会把公告列收到 340px，
        #    左栏因此比 1600px 时更宽（1023 vs 958），拿它做基准会误判。
        # ⚠️ 1200px 也可能被污染：@media(max-width:900px) 的 `gap:10px` 与
        #    @media(max-width:640px) 的 `padding:10px 12px 0` 会在更窄时生效，
        #    却因断点声明顺序只覆盖了 grid-template-columns、漏掉 gap/padding
        #    → 列宽算差 4px。这属于**布局/尺寸**问题，已登记 T-004 交 UI设计师。
        #    故此处断言**直接检查 gap/padding 是否被窄屏断点改掉**（根因层面），
        #    宽度一致性作为参考信息一并输出。
        await send('Emulation.setDeviceMetricsOverride',
                   {'width': 1200, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
        await asyncio.sleep(0.6)
        base = await ev("""(function(){
            var t=document.getElementById('topbar');
            var cs=getComputedStyle(t);
            return {top:cs.gridTemplateColumns, gap:cs.columnGap,
                    padL:cs.paddingLeft, padR:cs.paddingRight,
                    deptW:Math.round(document.getElementById('tbDepts').getBoundingClientRect().width)};
        })()""")
        for w, label in ((1000, '窄屏 1000'), (700, '窄屏 700')):
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': w, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(0.6)
            rr = await ev("""(function(){
                var t=document.getElementById('topbar');
                var cs=getComputedStyle(t);
                return {top:cs.gridTemplateColumns, gap:cs.columnGap,
                        padL:cs.paddingLeft, padR:cs.paddingRight,
                        deptW:Math.round(document.getElementById('tbDepts').getBoundingClientRect().width)};
            })()""")
            # 根因断言：列间距 / 内边距不得被窄屏断点改掉
            ok(rr.get('gap') == base.get('gap'),
               '%s：顶部栏列间距与 1200px 基准一致（实际 %s vs %s）'
               % (label, rr.get('gap'), base.get('gap')))
            ok(rr.get('padL') == base.get('padL') and rr.get('padR') == base.get('padR'),
               '%s：顶部栏内边距与 1200px 基准一致（实际 %s/%s vs %s/%s）'
               % (label, rr.get('padL'), rr.get('padR'), base.get('padL'), base.get('padR')))
            # 参考信息：完整宽度一致性
            same = (rr.get('top') == base.get('top') and rr.get('deptW') == base.get('deptW'))
            print('     （参考）%s 顶部栏栏宽 %s（基准 %s）、部门栅格 %spx（基准 %spx）%s'
                  % (label, rr.get('top'), base.get('top'), rr.get('deptW'), base.get('deptW'),
                     '一致' if same else '不一致 → 见 T-004'))
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
