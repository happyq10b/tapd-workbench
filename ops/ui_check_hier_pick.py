# -*- coding: utf-8 -*-
"""#54 人员选择层级约束 —— UI 实测（真实 Chrome + CDP）
1. 看板弹窗：负责人/参与人并排两框；选人范围 = 归属架构子树；参与人候选剔除负责人
2. 板块弹窗：「👤 选择」（无 🌳）；选人池 = 所属看板的负责人与参与人
3. 事项编辑弹窗：无「从架构选人」按钮；选人池 = 所属板块的负责人与参与人；互斥
"""
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

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9501
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__hz_'
PWD = 'At159357'
U_ADMIN = PREFIX + 'admin'
U_A, U_B, U_C = PREFIX + 'a', PREFIX + 'b', PREFIX + 'c'
NAME_A, NAME_B, NAME_C = PREFIX + '甲', PREFIX + '乙', PREFIX + '丙'

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


def setup():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    now = '2026-11-04 12:00:00'
    for acct, name in ((U_ADMIN, PREFIX + '管理员'), (U_A, NAME_A), (U_B, NAME_B), (U_C, NAME_C)):
        c.execute('DELETE FROM users WHERE username=?', (acct,))
        c.execute('DELETE FROM team_members WHERE account=?', (acct,))
        c.execute("DELETE FROM org_appointments WHERE member_id IN (SELECT id FROM team_members WHERE account=?)", (acct,))
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (name, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,?,?,?,?)", (acct, 'x', 'admin' if acct == U_ADMIN else 'editor', '*', '*', now))
    # 架构：CX(中心) → DY(部门)；A/B/C 都任职于 DY
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    cx = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,function) VALUES (?,?,0,'')", (PREFIX + '中心', 'center')).lastrowid
    dy = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,function) VALUES (?,?,?,'')", (PREFIX + '部门', 'dept', cx)).lastrowid
    mid = {}
    for acct, role in ((U_A, 'dept_head'), (U_B, 'dept_backbone'), (U_C, 'dept_backbone')):
        mid[acct] = c.execute('SELECT id FROM team_members WHERE account=?', (acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)",
                  (dy, mid[acct], role, now))
    # 看板：owner=A, participants=B,C；归属 DY
    bid = 'HZ' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,?,0,?)", (bid, PREFIX + '看板', '', U_A, U_B + ',' + U_C, now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, PREFIX + '部门', dy, '日常', '启用', now))
    # 板块：owner=A, participants=B
    ck = bid + '::' + PREFIX + '板块'
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants)"
              " VALUES (?,?,?,?,?,'x','日常','2026',0,?,?)",
              (ck, PREFIX + 'col1', bid, PREFIX + '板块', now, U_A, U_B))
    # 事项（板块下有一张卡，保证板块在页面上可见）
    c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,creator,owner,cc,created,modified,description,parent_id,deleted)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'','',0)""",
              (PREFIX + 'K1', bid, PREFIX + '看板', PREFIX + 'col1', PREFIX + '板块', PREFIX + '卡1',
               'open', 'admin', '', '', now, now))
    c.commit()
    c.close()
    return {'bid': bid, 'ck': ck, 'cx': cx, 'dy': dy,
            'card': PREFIX + 'K1', 'col': PREFIX + '板块'}


def cleanup(fx):
    c = sqlite3.connect(DB)
    bid = fx['bid']
    for t in ('cards', 'board_columns', 'board_config'):
        c.execute('DELETE FROM ' + t + ' WHERE board_id=?', (bid,))
    c.execute('DELETE FROM boards WHERE board_id=?', (bid,))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    for acct in (U_ADMIN, U_A, U_B, U_C):
        c.execute('DELETE FROM users WHERE username=?', (acct,))
        c.execute('DELETE FROM team_members WHERE account=?', (acct,))
    c.commit()
    c.close()


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_hz%d' % PORT)
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
    ws_url = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
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
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:400]}
                return r.get('result', {}).get('value')

            await send('Page.enable')
            await send('Runtime.enable')
            await send('Page.navigate', {'url': BASE + '/login'})
            await asyncio.sleep(2)
            await ev("document.getElementById('u').value='admin';document.getElementById('p').value='%s';document.getElementById('btn').click();" % PWD)
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)

            # ── 1. 纯函数：架构子树过滤 ──
            print('\n【1】orgTreeForNode / orgTreeWithoutNames')
            await ev("ensureOrgTree(true).then(function(){return 1;});", aw=True)
            await asyncio.sleep(1)
            r = await ev("""(function(){
              const sub=orgTreeForNode(%d);
              const names=[];
              (function col(ns){(ns||[]).forEach(n=>{(n.members||[]).forEach(m=>names.push(m.name||m));col(n.children||[]);});})(sub);
              const allNames=[];
              (function col(ns){(ns||[]).forEach(n=>{(n.members||[]).forEach(m=>allNames.push(m.name||m));col(n.children||[]);});})(ORG_TREE);
              const pruned=orgTreeWithoutNames(ORG_TREE,['%s']);
              const prunedNames=[];
              (function col(ns){(ns||[]).forEach(n=>{(n.members||[]).forEach(m=>prunedNames.push(m.name||m));col(n.children||[]);});})(pruned);
              return {subId:sub.length===1?sub[0].id:null,subNames:names,
                      allHasOther:allNames.some(n=>n.indexOf('__hz_')<0),
                      prunedKept:prunedNames.filter(n=>n!=='%s').length,
                      prunedExcluded:!prunedNames.includes('%s')};
            })()""" % (fx['dy'], NAME_A, NAME_A, NAME_A))
            ok(r.get('subId') == fx['dy'], 'orgTreeForNode(部门) 返回该子树（id=%s）' % r.get('subId'))
            ok(sorted(r.get('subNames') or []) == sorted([NAME_A, NAME_B, NAME_C]),
               '子树成员 = A/B/C：%s' % (r.get('subNames')))
            ok(r.get('allHasOther') is True, '全树含架构外人员（对照）')
            ok(r.get('prunedExcluded') is True, 'orgTreeWithoutNames 剔除负责人')

            # ── 2. 事项编辑弹窗：池 + 无架构按钮 + 互斥 ──
            print('\n【2】事项编辑弹窗（板块池 + 互斥）')
            await ev("window.COLS_META=[{col_key:%s,column_id:'c1',owner:%s,participants:%s}];0;"
                     % (json.dumps(fx['bid'] + '::' + fx['col']), json.dumps(U_A), json.dumps(U_B)))
            await ev("openEdit(%s);" % json.dumps(fx['card']), aw=True)
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              const m=document.getElementById('editModal');
              const hasArch=m.textContent.indexOf('从架构选人')>=0;
              const po=PP['e_owner'],pc=PP['e_cc'];
              return {hasArch:hasArch,
                      ownerPool:po?po.ALL.slice():null,ccPool:pc?pc.ALL.slice():null,
                      ownerPair:po?po.pair:'',ccPair:pc?pc.pair:'',ccIsOwner:pc?pc.isOwner:null};
            })()""")
            ok(r.get('hasArch') is False, '「从架构选人」按钮已移除')
            ok(r.get('ownerPool') == [NAME_A, NAME_B], '负责人池 = 板块负责人+参与人（%s）' % r.get('ownerPool'))
            ok(r.get('ccPool') == [NAME_A, NAME_B], '参与人池同源')
            ok(r.get('ownerPair') == 'e_cc' and r.get('ccPair') == 'e_owner', '互斥配对已建立')
            # 互斥行为：先设参与人 B，再选 B 为负责人 → B 从参与人移除
            await ev("PP['e_cc'].arr.length=0;PP['e_cc'].arr.push(%s);ppSyncTags('e_cc');0;" % json.dumps(NAME_B))
            await ev("ppToggle('e_owner',%s);0;" % json.dumps(NAME_B))
            r = await ev("(function(){return {cc:PP['e_cc'].arr.slice(),owner:PP['e_owner'].arr.slice()}})()")
            ok(r.get('owner') == [NAME_B], '选 B 为负责人')
            ok(r.get('cc') == [], 'B 自动从参与人移除（互斥）')
            # 参与人侧录入负责人 → 拦截
            await ev("ppAddTyped('e_cc',%s);0;" % json.dumps(NAME_B))
            r = await ev("PP['e_cc'].arr.slice()")
            ok(r == [], '参与人侧录入负责人被拦截（cc 仍空）')
            # 池外人录入 → 拦截
            await ev("ppAddTyped('e_cc','生产环境某成员');0;")
            r = await ev("PP['e_cc'].arr.slice()")
            ok(r == [], '池外人员录入被拦截（不在 ALL）')
            await ev("closeModal('editModal');")

            # ── 3. 板块弹窗：👤 看板选人池 ──
            print('\n【3】板块弹窗（看板池）')
            await ev("ME.boards.push({board_id:%s,board_name:%s,owner:%s,participants:%s,can_edit:true,can_assign_owner:true});0;"
                     % (json.dumps(fx['bid']), json.dumps(PREFIX + '看板'), json.dumps(U_A), json.dumps(U_B + ',' + U_C)))
            await ev("openColumnModal();")
            await asyncio.sleep(1)
            await ev("document.getElementById('c_board').value=%s;0;" % json.dumps(fx['bid']))
            r = await ev("""(function(){
              const ob=document.getElementById('c_owner_pick_btn'),pb=document.getElementById('c_parts_pick_btn');
              return {ownerBtn:ob?ob.textContent:'',partsBtn:pb?pb.textContent:'',
                      noTree:ob?ob.textContent.indexOf('🌳')<0:true};
            })()""")
            ok(r.get('ownerBtn') == '👤 选择' and r.get('partsBtn') == '👤 选择',
               '板块按钮为「👤 选择」（%s / %s）' % (r.get('ownerBtn'), r.get('partsBtn')))
            # 打开负责人选人树 → 只含池内人员
            await ev("colPickOwner(document.getElementById('c_owner_pick_btn'));", aw=True)
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              const p=document.querySelector('.tree-pick');
              if(!p)return {panel:false};
              // ⚠️ 用**人员行**断言（.tp-node.tp-person）—— 面板 textContent 会混入
              //    节点行上的任职徽标（部门长：某某），整段 text 不可靠。
              const rows=[].slice.call(p.querySelectorAll('.tp-node.tp-person')).map(x=>x.textContent.replace(/^[\s\S]*👤\s*/u,'').trim());
              return {panel:true,rows:rows,hasA:rows.some(r=>r.indexOf(%s)===0),hasB:rows.some(r=>r.indexOf(%s)===0)};
            })()""" % (json.dumps(NAME_A), json.dumps(NAME_B)))
            ok(r.get('panel') is True, '负责人选人面板打开')
            ok(r.get('hasA') is True and r.get('hasB') is True, '面板含看板负责人与参与人（池内）')
            await ev("(function(){const p=document.querySelector('.tree-pick');if(p)p.remove();})()")
            # 参与人树排除负责人
            await ev("COL_OWNER=%s;colRenderOwner();0;" % json.dumps(U_A))
            await ev("colPickParticipants(document.getElementById('c_parts_pick_btn'));", aw=True)
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              const p=document.querySelector('.tree-pick');
              if(!p)return {panel:false};
              const rows=[].slice.call(p.querySelectorAll('.tp-node.tp-person')).map(x=>x.textContent.replace(/^[\s\S]*👤\s*/u,'').trim());
              return {panel:true,rows:rows,hasOwner:rows.some(r=>r.indexOf(%s)===0),hasB:rows.some(r=>r.indexOf(%s)===0)};
            })()""" % (json.dumps(NAME_A), json.dumps(NAME_B)))
            ok(r.get('panel') is True and r.get('hasOwner') is False,
               '参与人面板已剔除负责人（互斥）')
            ok(r.get('hasB') is True, '参与人面板含 B')
            await ev("(function(){const p=document.querySelector('.tree-pick');if(p)p.remove();})()")
            await ev("closeModal('columnModal');")

            # ── 4. 看板弹窗：两框 + 子树过滤 + 参与人剔除负责人 ──
            print('\n【4】看板弹窗（归属架构子树）')
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            await ev("bcSelect(%s);" % json.dumps(fx['bid']))
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              const sec=document.querySelector('#bcEditArea .bc-owner-sec');
              if(!sec)return {found:false};
              return {found:true,hasOwnerLab:sec.textContent.indexOf('负责人')>=0,
                      hasPartsLab:sec.textContent.indexOf('参与人')>=0,
                      partsChips:[].slice.call(sec.querySelectorAll('#bc_parts_box .cf-chip')).map(x=>x.textContent.replace('✕','').trim())};
            })()""")
            ok(r.get('found') is True, '看板负责人与参与人区块存在')
            ok(r.get('hasOwnerLab') is True and r.get('hasPartsLab') is True, '负责人/参与人并排两框')
            ok(r.get('partsChips') == [NAME_B, NAME_C], '参与人回显 = %s' % (r.get('partsChips'),))
            # 负责人树 = 归属子树（只有 A/B/C，无架构外人员）
            await ev("bcPickOwner(document.getElementById('bc_owner_box'));", aw=True)
            await asyncio.sleep(2)
            r = await ev("""(function(){
              const p=document.querySelector('.tree-pick');
              if(!p)return {panel:false};
              const t=p.textContent;
              const rows=[].slice.call(p.querySelectorAll('.tp-node,.tp-person,.tn-name')).map(x=>x.textContent);
              return {panel:true,hasA:t.indexOf(%s)>=0,hasB:t.indexOf(%s)>=0,
                      outside:t.indexOf('总经理')>=0&&t.indexOf(%s)<0?true:undefined};
            })()""" % (json.dumps(NAME_A), json.dumps(NAME_B), json.dumps(NAME_A)))
            ok(r.get('panel') is True, '负责人选人面板打开')
            ok(r.get('hasA') is True and r.get('hasB') is True, '面板含归属子树成员 A/B')
            await ev("(function(){const p=document.querySelector('.tree-pick');if(p)p.remove();})()")
            # 参与人树剔除负责人 A
            await ev("bcPickParticipants(document.getElementById('bc_parts_box'));", aw=True)
            await asyncio.sleep(2)
            r = await ev("""(function(){
              const p=document.querySelector('.tree-pick');
              if(!p)return {panel:false};
              const rows=[].slice.call(p.querySelectorAll('.tp-node.tp-person')).map(x=>x.textContent.replace(/^[\s\S]*👤\s*/u,'').trim());
              return {panel:true,rows:rows,hasOwner:rows.some(r=>r.indexOf(%s)===0),hasB:rows.some(r=>r.indexOf(%s)===0),hasC:rows.some(r=>r.indexOf(%s)===0)};
            })()""" % (json.dumps(NAME_A), json.dumps(NAME_B), json.dumps(NAME_C)))
            ok(r.get('panel') is True and r.get('hasOwner') is False,
               '看板参与人面板剔除负责人 A（互斥）')
            ok(r.get('hasB') is True and r.get('hasC') is True, '参与人面板含 B/C')
            await ev("(function(){const p=document.querySelector('.tree-pick');if(p)p.remove();})()")
            await ev("closeModal('boardConfigModal');")
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__=='__main__':
    sys.exit(asyncio.run(main()))
