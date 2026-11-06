# -*- coding: utf-8 -*-
"""需求 1/2/3/6/7 的 UI 实测（真实 Chrome）"""
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9575
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__hui_'
PWD = 'At159357'
now = '2026-11-04 12:00:00'

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


def setup():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    for a in (PREFIX + 'admin', PREFIX + 'owner'):
        c.execute('DELETE FROM users WHERE username=?', (a,))
        c.execute('DELETE FROM team_members WHERE account=?', (a,))
        c.execute('INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,?,?,?)',
                  (PREFIX + a, '', a, now))
        c.execute('INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)'
                  ' VALUES (?,?,?,?,?,?)',
                  (a, hash_pw(PWD), 'admin' if 'admin' in a else 'editor', '*', '*', now))
    stamp = str(int(time.time() * 1000))
    bid = 'UI' + stamp
    c.execute('INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)'
              ' VALUES (?,?,?,?,?,0,?)', (bid, PREFIX + '看板', '', PREFIX + 'owner', '', now))
    c.execute('INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion)'
              ' VALUES (?,?,?,?,?,?,?,?,0,?,?,?)',
              (bid + '::' + PREFIX + 'A', PREFIX + 'col1', bid, PREFIX + 'A', now,
               PREFIX + 'owner', '日常', '2026', PREFIX + 'owner', '', 'done'))
    CARD_COLS = ['card_id', 'board_id', 'board_name', 'column_id', 'column_name', 'card_name',
                 'status', 'status_name', 'creator', 'owner', 'cc', 'begin', 'due', 'created',
                 'modified', 'description', 'week_no', 'deleted', 'parent_id', 'pinned']
    vals = {'card_id': PREFIX + 'c1', 'board_id': bid, 'board_name': PREFIX + '看板',
            'column_id': PREFIX + 'col1', 'column_name': PREFIX + 'A',
            'card_name': PREFIX + '事项1', 'status': 'done', 'status_name': '已完成',
            'creator': PREFIX + 'owner', 'owner': PREFIX + 'owner', 'cc': '',
            'begin': '2026-08-06', 'due': '2026-08-14', 'created': now, 'modified': now,
            'description': '描述', 'week_no': '2026年第45周', 'deleted': 0,
            'parent_id': '', 'pinned': 0}
    c.execute('INSERT INTO cards (%s) VALUES (%s)'
              % (','.join(CARD_COLS), ','.join('?' * len(CARD_COLS))),
              [vals[k] for k in CARD_COLS])
    c.commit()
    c.close()
    return {'bid': bid, 'col_key': bid + '::' + PREFIX + 'A'}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        for t in ('cards', 'board_columns', 'board_config'):
            c.execute('DELETE FROM %s WHERE board_id=?' % t, (fx['bid'],))
        c.execute('DELETE FROM boards WHERE board_id=?', (fx['bid'],))
    for a in (PREFIX + 'admin', PREFIX + 'owner'):
        c.execute('DELETE FROM users WHERE username=?', (a,))
        c.execute('DELETE FROM team_members WHERE account=?', (a,))
    c.commit()
    c.close()


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_hui%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                      '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2) as r:
                json.loads(r.read())
            break
        except Exception:
            time.sleep(0.5)
    import websockets
    targets = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0

            async def send(m, p=None):
                nonlocal i
                i += 1
                mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable')
            await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value='%s';document.getElementById('p').value='%s';document.getElementById('btn').click();"
                     % (PREFIX + 'admin', PWD))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            # 选中夹具看板
            await ev("curBoards=new Set(['%s']);curBoard='%s';reload(1);" % (fx['bid'], fx['bid']))
            await asyncio.sleep(3)

            # ═══ 需求1：清空筛选按钮蓝色底色 ═══
            print('\n【需求1】清空筛选按钮蓝色底色')
            r = await ev("""(function(){
              var b=document.querySelector('.btn-clear');
              if(!b)return {found:false};
              var cs=getComputedStyle(b);
              return {found:true,bg:cs.backgroundColor,color:cs.color,text:b.textContent.trim()};
            })()""")
            ok(r.get('found') is True, '清空筛选按钮存在（.btn-clear）')
            ok(r.get('text') == '清空筛选', '文案为「清空筛选」（%s）' % r.get('text'))
            bg = r.get('bg') or ''
            ok(bg not in ('rgba(0, 0, 0, 0)', 'transparent', ''),
               '按钮有蓝色底色（bg=%s color=%s）' % (bg, r.get('color')))

            # ═══ 需求2：进度条固定宽度 + 与负责人列起点对齐 ═══
            print('\n【需求2】进度条固定宽度 / 与负责人列对齐 / 剩余空间给标题')
            r = await ev("""(function(){
              var hdr=document.querySelector('.week-header');
              if(!hdr)return {noHeader:true};
              var bar=hdr.querySelector('.week-bar');
              var fcols=hdr.querySelector('.week-fcols');
              var owner=fcols?fcols.querySelector('.fcol-owner'):null;
              var title=hdr.querySelector('.week-title');
              var meta=hdr.querySelector('.week-meta');
              if(!bar||!owner)return {noBar:!bar,noOwner:!owner};
              var bb=bar.getBoundingClientRect(), ob=owner.getBoundingClientRect();
              var tb=title?title.getBoundingClientRect():null;
              var mb=meta?meta.getBoundingClientRect():null;
              // 事项行的负责人列起点（用于纵向对齐比对）
              var ic=document.querySelector('.item-card .fcols .fcol-owner');
              var ib=ic?ic.getBoundingClientRect():null;
              return {barW:Math.round(bb.width),barR:Math.round(bb.right),
                      barL:Math.round(bb.left),
                      metaR:mb?Math.round(mb.right):null,
                      ownerL:Math.round(ob.left),
                      titleW:tb?Math.round(tb.width):0,
                      itemOwnerL:ib?Math.round(ib.left):null,
                      fcolsW:fcols?Math.round(fcols.getBoundingClientRect().width):0};
            })()""")
            ok(not r.get('noHeader'), '板块行已渲染')
            ok(not r.get('noBar') and not r.get('noOwner'), '进度条与负责人列都在板块行内')
            barW = r.get('barW', 0)
            # ⚠️ 2026-11-04 再调：进度条占满周数位格（96px）并向左溢出 8px
            #    → 起点紧靠「n/N 完成」（4px），终点距「负责人」16px（翻倍）
            ok(abs(barW - 96) <= 2, '进度条长度 96px（占满周数位格，实测 %s px）' % barW)
            gap = (r.get('ownerL', 0) - r.get('barR', 0))
            ok(12 <= gap <= 20, '进度条终点与负责人列间距 16px（实测 %s px）' % gap)
            gapL = (r.get('barL', 0) - r.get('metaR', 0))
            ok(0 <= gapL <= 8, '进度条起点紧靠「n/N 完成」（间距 %s px）' % gapL)
            if r.get('itemOwnerL'):
                d = r.get('ownerL', 0) - r['itemOwnerL']
                ok(abs(d) <= 4, '板块行负责人列与事项行负责人列纵向对齐（差 %s px）' % d)
            ok(r.get('titleW', 0) > 200, '标题区域获得剩余空间（宽 %s px）' % r.get('titleW'))

            # ═══ 需求3：板块完成情况展示 + 事项完成情况只读 ═══
            print('\n【需求3】板块完成情况 / 事项完成情况只读')
            r = await ev("""(function(){
              var hdr=document.querySelector('.week-header');
              var st=hdr?hdr.querySelector('.slot-status .status-tag'):null;
              var itemSt=document.querySelector('.item-card .slot-status .status-tag');
              return {colTag:st?st.textContent.trim():null,
                      colHasAct:st?st.className.indexOf('status-tag-act')>=0:null,
                      itemTag:itemSt?itemSt.textContent.trim():null,
                      itemHasAct:itemSt?itemSt.className.indexOf('status-tag-act')>=0:null,
                      itemOnclick:itemSt?(itemSt.getAttribute('onclick')||''):null};
            })()""")
            ok(r.get('colTag') == '已完成', '板块行展示完成情况标签（%s）' % r.get('colTag'))
            ok(r.get('colHasAct') is False, '板块完成情况为只读展示')
            ok(r.get('itemTag') in ('已完成', '未完成', '进行中'), '事项行仍展示完成情况（%s）' % r.get('itemTag'))
            ok(r.get('itemHasAct') is False, '事项完成情况去掉可点击态（status-tag-act）')
            ok(not r.get('itemOnclick'), '事项完成情况移除 onclick 交互')

            # ═══ 需求6/7：菜单文案 ═══
            print('\n【需求6/7】导入导出菜单文案')
            r = await ev("""(function(){
              var ops=(typeof ROW_OPS!=='undefined'&&ROW_OPS['toolbarOps'])||[];
              return ops.map(function(x){return x.label});
            })()""")
            labels = r or []
            ok(any('导出（xlsx）' == l for l in labels), '菜单含「导出（xlsx）」（%s）' % labels)
            ok(any('导入（xlsx）' == l for l in labels), '菜单含「导入（xlsx）」')
            # 2026-11-06 #82：模板下载并入导入弹窗、模板管理并入导出弹窗 → 外部按钮移除
            ok(not any('下载导入模板' == l for l in labels), '「下载导入模板」独立按钮已移除（并入导入弹窗）')
            ok(not any('导出模板' == l for l in labels), '「导出模板」独立按钮已移除（并入导出弹窗页签）')
            ok(not any(l.startswith('📄') or l.startswith('📊') or l.startswith('📥') for l in labels),
               '导入/导出/模板三项已去掉 emoji（%s）' % labels)

            # ═══ 需求3：编辑弹窗的完成情况选择器（板块负责人可改 / 其他只读）════════
            print('\n【需求3b】编辑板块弹窗的完成情况选择器')
            await ev("""(function(){
              var t=[].slice.call(document.querySelectorAll('.week-title.edit'))
                     .find(function(x){return x.textContent.indexOf('%s')>=0});
              if(t)openColumnEdit(t);
            })()""" % PREFIX)
            await asyncio.sleep(2)
            r = await ev("""(function(){
              var s=document.getElementById('c_completion');
              if(!s)return {found:false};
              return {found:true,value:s.value,disabled:s.disabled,
                      tip:(document.getElementById('c_completion_tip')||{}).textContent||''};
            })()""")
            ok(r.get('found') is True, '编辑弹窗含「完成情况」选择器')
            ok(r.get('value') == 'done', '回填当前完成情况（%s）' % r.get('value'))
            ok(r.get('disabled') is False, '管理员可编辑完成情况')
            await ev("closeModal('columnModal');")
            await asyncio.sleep(1)
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  - ' + f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
