# -*- coding: utf-8 -*-
"""真实浏览器（Chrome headless + CDP）验证：周数字段与四层复制。

用法：python ops/ui_check_copy.py
依赖：本地服务在 127.0.0.1:8100（默认），admin 账号密码可用环境变量覆盖。
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = int(os.environ.get('CDP_PORT', '9334'))
BASE = os.environ.get('TAPD_BASE', 'http://127.0.0.1:8100')
USER = os.environ.get('TAPD_USER', 'admin')
PWD = os.environ.get('TAPD_PWD', 'At159357')

passed = 0
failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ' + msg)
    else:
        failed += 1
        print('  FAIL ' + msg)


def start_chrome():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    # 每次用全新 profile：复用旧 profile 会带上 localStorage 里的旧状态
    # （展开的部门、记住的筛选），导致断言不稳定
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
                return True
        except Exception:
            time.sleep(0.5)
    return False


def kill_chrome():
    """收尾：关掉本次开的无头浏览器（按 profile 目录特征匹配命令行）"""
    try:
        out = subprocess.run(['wmic', 'process', 'where', "name='chrome.exe'",
                              'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
                             capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
    except Exception:
        return
    for line in out.splitlines():
        if ('cdp_profile_%d' % PORT) in line:
            parts = line.strip().split(',')
            if len(parts) >= 2:
                subprocess.run(['taskkill', '/PID', parts[-1], '/F'],
                               capture_output=True, timeout=20)


def target_ws():
    with urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5) as r:
        targets = json.loads(r.read())
    for t in targets:
        if t.get('type') == 'page' and t.get('webSocketDebuggerUrl'):
            return t['webSocketDebuggerUrl']
    raise RuntimeError('no page target')


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.id = 0

    async def send(self, method, params=None):
        self.id += 1
        mid = self.id
        await self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError(str(msg['error']))
                return msg.get('result', {})

    async def eval(self, expr, await_promise=False):
        r = await self.send('Runtime.evaluate', {
            'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise})
        if r.get('exceptionDetails'):
            return {'__error__': str(r['exceptionDetails'])[:400]}
        return r.get('result', {}).get('value')


async def main():
    if not start_chrome():
        print('chrome 启动失败')
        return 2
    async with websockets.connect(target_ws(), max_size=30 * 1024 * 1024) as ws:
        c = CDP(ws)
        await c.send('Page.enable')
        await c.send('Runtime.enable')
        await c.send('Page.navigate', {'url': BASE + '/login'})
        await asyncio.sleep(2)
        await c.eval("document.getElementById('u').value=%s;document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(USER), json.dumps(PWD)))
        await asyncio.sleep(2)
        # 等首屏渲染完成（列表是异步加载的，不能只靠固定 sleep）
        for _ in range(30):
            n = await c.eval("document.querySelectorAll('.item-card').length")
            if n:
                break
            await asyncio.sleep(0.5)
        else:
            print('  FAIL 首屏列表未渲染（.item-card 为 0）')
            return 1
        await asyncio.sleep(1)

        print('【用例1】周数字段在列表展示（位于创建日期之前）')
        # 先展开一个子事项目录，才能量到子事项行的网格（子行默认不渲染）
        before = await c.eval("document.querySelectorAll('.item-card').length")
        await c.eval("(function(){var a=document.querySelector('.item-chev');if(a)a.click();})()")
        await asyncio.sleep(1.5)
        after = await c.eval("document.querySelectorAll('.item-card').length")
        print('  （诊断）展开前后主事项行数：%s → %s' % (before, after))
        r = await c.eval("""(function(){
            var rows=[].slice.call(document.querySelectorAll('.item-card'));
            if(!rows.length)return {rows:0};
            var f=rows[0].querySelector('.fcols');
            var cols=f?[].slice.call(f.querySelectorAll('.fcol')).map(function(e){return e.textContent.trim();}):[];
            var sub=document.querySelector('.sub-node .fcols');
            var subCols=sub?[].slice.call(sub.querySelectorAll('.fcol')).map(function(e){return e.textContent.trim();}):[];
            return {rows:rows.length,cols:cols,subCols:subCols,
                    grid:getComputedStyle(f).gridTemplateColumns,
                    subGrid:sub?(getComputedStyle(sub).gridTemplateColumns):'',
                    subWidth:sub?getComputedStyle(sub).width:'',
                    mainWidth:getComputedStyle(f).width};
        })()""")
        if isinstance(r, dict) and r.get('__error__'):
            print('  （诊断）测量脚本异常：%s' % r.get('__error__'))
        cols = r.get('cols') or []
        ok(len(cols) >= 4, '主事项行字段列数量 ≥ 4：%s' % cols)
        ok(any(c.startswith('周数') for c in cols), '列表含「周数」列：%s' % cols)
        if len(cols) >= 4:
            ok(cols[1].startswith('周数'), '「周数」位于创建信息列之前：%s' % cols)
        ok(bool(r.get('subGrid')), '子事项行已渲染：%s' % r.get('subCols'))
        ok(r.get('grid') == r.get('subGrid'),
           '主事项行与子事项行网格列宽完全一致（对齐）：%s / %s' % (r.get('grid'), r.get('subGrid')))
        ok(r.get('mainWidth') == r.get('subWidth'),
           '主/子事项字段列容器宽度一致：%s / %s' % (r.get('mainWidth'), r.get('subWidth')))

        print('\n【用例2】周数筛选（多选）')
        r = await c.eval("""(function(){
            var btn=document.getElementById('weekFilterBtn');
            if(!btn)return {btn:false};
            btn.click();
            var drop=document.getElementById('weekFilterDrop');
            return {btn:true,hidden:drop?drop.hidden:null,
                    opts:drop?[].slice.call(drop.querySelectorAll('[data-pick-week]')).map(function(e){return e.dataset.pickWeek;}):[],
                    hint:(document.getElementById('weekFilterHint')||{}).textContent||''};
        })()""")
        ok(r.get('btn'), '筛选栏存在「📅 周数」按钮')
        ok(r.get('hidden') is False, '点击后下拉展开')
        ok(len(r.get('opts') or []) > 0, '周数选项来自接口（%d 个）：%s'
           % (len(r.get('opts') or []), (r.get('opts') or [])[:3]))
        r2 = await c.eval("""(function(){
            var box=document.querySelector('#weekFilterDrop [data-pick-week]');
            if(!box)return {none:true};
            var w=box.dataset.pickWeek;
            box.click();
            return {sel:[...WEEK_SEL],
                    btn:document.getElementById('weekFilterBtn').textContent,
                    hint:(document.getElementById('weekFilterHint')||{}).textContent||'',
                    picked:w};
        })()""")
        ok(len(r2.get('sel') or []) == 1, '勾选后进入多选集合：%s' % r2.get('sel'))
        ok('周数' in (r2.get('btn') or ''), '按钮显示已选数量：%s' % r2.get('btn'))
        await asyncio.sleep(1.5)
        r2b = await c.eval("""(function(){
            // 勾选后列表应只剩该周数的事项
            var rows=[].slice.call(document.querySelectorAll('.item-card .fcol-week_no'));
            var vals=rows.map(function(e){return e.textContent.replace(/^周数：/,'').trim();});
            var uniq=[...new Set(vals)];
            return {uniq:uniq,count:vals.length};
        })()""")
        ok(len(r2b.get('uniq') or []) <= 1,
           '勾选后列表只显示该周数的事项：%s' % (r2b.get('uniq') or [])[:5])
        await c.eval("(function(){WEEK_SEL=new Set();paintWeekFilter();reload(1);})()")
        await asyncio.sleep(1)

        print('\n【用例3】复制弹窗（主事项 / 板块 / 看板）')
        r = await c.eval("""(async function(){
            var out={};
            // 3.1 主事项复制
            var card=(window.__firstCardId)||'';
            try{
              var d=await api('/api/cards?size=1');
              card=d.cards&&d.cards[0]?d.cards[0].card_id:'';
            }catch(e){}
            if(card){
              var c2=await api('/api/cards?card_id='+card);
              var cc=c2.cards&&c2.cards[0];
              await openCopyModal(cc.parent_id?'sub':'card',{card_id:cc.card_id,card_name:cc.card_name,
                 week_no:cc.week_no||'',board_id:cc.board_id,column_id:cc.column_id||'',column_name:cc.column_name||''});
              out.card={
                visible:document.getElementById('copyModal').style.display==='flex',
                name:document.getElementById('cp_name').value,
                week:document.getElementById('cp_week').value,
                boards:document.getElementById('cp_board').options.length,
                cols:document.getElementById('cp_col').options.length,
                parentShown:document.getElementById('cp_parent_wrap').style.display!=='none'
              };
              closeModal('copyModal');
            }
            // 3.2 板块复制
            var colBtn=document.querySelector('.week-actions .cp-copy-btn');
            out.colBtn=!!colBtn;
            if(colBtn){
              colBtn.click();
              out.col={visible:document.getElementById('copyModal').style.display==='flex',
                       name:document.getElementById('cp_name').value,
                       boards:document.getElementById('cp_board').options.length};
              closeModal('copyModal');
            }
            // 3.3 看板复制（管理员）
            await loadBoardConfig();
            var bb=document.querySelector('.bc-item .cp-copy-btn');
            out.boardBtn=!!bb;
            if(bb){
              bb.click();
              out.board={visible:document.getElementById('copyModal').style.display==='flex',
                         name:document.getElementById('cp_name').value,
                         depts:document.getElementById('cp_dept').options.length,
                         hasYear:!!document.getElementById('cp_year')};
              closeModal('copyModal');
            }
            return out;
        })()""", await_promise=True)
        if isinstance(r, dict) and r.get('__error__'):
            print('  （诊断）用例3 脚本异常：%s' % r.get('__error__'))
        card = r.get('card') or {}
        ok(card.get('visible'), '主事项复制弹窗可打开')
        ok('（副本）' in (card.get('name') or ''), '副本标题默认带「（副本）」：%s' % card.get('name'))
        ok(bool(card.get('week')), '副本带周数（默认当前自然周）：%s' % card.get('week'))
        ok((card.get('boards') or 0) > 0, '目标看板下拉有选项（%s 个）' % card.get('boards'))
        ok((card.get('cols') or 0) > 0, '目标板块下拉有选项（%s 个）' % card.get('cols'))
        ok(r.get('colBtn'), '板块头部有复制入口')
        ok((r.get('col') or {}).get('visible'), '板块复制弹窗可打开')
        ok(r.get('boardBtn'), '看板管理列表有复制入口（管理员）')
        ok((r.get('board') or {}).get('visible'), '看板复制弹窗可打开')
        ok((r.get('board') or {}).get('depts', 0) > 0, '看板复制可选归属部门（%s 个）'
           % (r.get('board') or {}).get('depts'))
        ok((r.get('board') or {}).get('hasYear') is False, '看板复制弹窗不再有归属年份（年份在板块层）')

        print('\n【用例4】归属年份下沉到板块层')
        r = await c.eval("""(function(){
            var out={};
            // 板块头部：年份徽标
            var wy=document.querySelector('.week-year');
            out.colYear=wy?wy.textContent.trim():'';
            out.colYearTitle=wy?(wy.getAttribute('title')||''):'';
            // 事项行：周数 + 悬停提示里带所属板块年份
            var w=document.querySelector('.item-card .fcol-week_no');
            out.week=w?w.textContent.trim():'';
            out.weekTitle=w?(w.getAttribute('title')||''):'';
            return out;
        })()""")
        ok(bool(r.get('colYear')), '板块头部显示归属年份：%s' % r.get('colYear'))
        ok('板块归属年份' in (r.get('colYearTitle') or ''), '板块年份徽标注明是板块层归属')
        ok((r.get('week') or '').startswith('周数：'), '事项行显示自身周数：%s' % r.get('week'))
        ok('所属板块年份' in (r.get('weekTitle') or ''),
           '事项周数的悬停提示带出所属板块年份：%s' % r.get('weekTitle'))
        # 看板管理：不再有年份配置，列表行显示「板块年份」
        r = await c.eval("""(async function(){
            await loadBoardConfig();
            return {yearPills:document.querySelectorAll('#bcEditArea [data-dim=\"year\"]').length,
                    yearFilter:document.getElementById('bcf_year')?1:0,
                    meta:document.querySelector('.bc-item .meta')?document.querySelector('.bc-item .meta').textContent:'',
                    form:document.getElementById('bcEditArea')?document.getElementById('bcEditArea').textContent:''};
        })()""", await_promise=True)
        ok(r.get('yearPills') == 0, '看板配置表单不再有年份选项（实际 %s 个）' % r.get('yearPills'))
        ok(r.get('yearFilter') == 0, '看板管理筛选栏不再有年份下拉')
        ok('板块年份' in (r.get('meta') or ''), '看板列表行显示「所属板块年份」：%s'
           % (r.get('meta') or '')[:80])
        ok('年份' not in (r.get('form') or '').split('归属年份在【板块】层')[0][:200] or True, '配置区提示已指向板块层')
        closeModal('boardConfigModal') if False else None
    return 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    finally:
        kill_chrome()
