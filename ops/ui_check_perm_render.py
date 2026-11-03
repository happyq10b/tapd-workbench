#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI 实测：菜单顺序 + 权限动态渲染（2026-11-03）。

用例：
  A. 菜单顺序：架构管理入口带在「架构部门」带之后；看板管理入口带在「可选看板」带之后；
     且两者都不再出现在顶栏。
  B. 管理员：两个入口带都可见。
  C. 架构负责人：两个入口带可见；看板管理里只列可配置看板；架构管理里
     管辖范围外的节点置灰（org-node-ro）、岗位任命禁用。
  D. 只读：两个入口带**整带隐藏**。
  E. 接口侧越权：只读账号调看板管理写接口 → 403 + 统一错误体。

⚠️ 夹具纪律（2026-11-02 立规）：
  · 账号/成员一律用 __pr_ 前缀专属命名空间
  · try/finally 保证清理（cleanup 要删全所有相关表）
  · **断言不硬编码全局基线数字** —— 用夹具自己造的数据比对
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9463
PREFIX = '__pr_'
U_ADMIN = PREFIX + 'admin'
U_ARCH = PREFIX + 'arch'      # 架构负责人（管一个子节点）
U_VIEWER = PREFIX + 'viewer'  # 只读
PWD = 'At159357'

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  ✓ ' if cond else '  ✗ ') + msg)


def setup():
    """造夹具：一个父节点（中心）+ 两个子部门，父部门归 A，B 在 A 的范围外。
    A 是父部门负责人 → 管辖 A + 其后代；B 在 A 的范围外 → 应被置灰。
    另造一个看板，归属 A → A 应能配置它。
    """
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    now = '2026-11-03 12:00:00'
    # 账号与成员
    for acct, role in ((U_ADMIN, 'admin'), (U_ARCH, 'editor'), (U_VIEWER, 'viewer')):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
        c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        c.execute("""INSERT INTO users (username, password_hash, role, allowed_boards,
                       allowed_columns, created_at) VALUES (?,?,?,?,?,?)""",
                  (acct, hash_pw(PWD), role, '*', '*', now))
    # 架构节点：__pr_center（中心） → __pr_dept_a / __pr_dept_b
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
              (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    ids = {}
    for name, ntype, parent in ((PREFIX + 'center', 'center', 0),
                                (PREFIX + 'dept_a', 'dept', 0),
                                (PREFIX + 'dept_b', 'dept', 0)):
        cur = c.execute("INSERT INTO org_nodes (name, node_type, parent_id, function) VALUES (?,?,?,'')",
                         (name, ntype, parent))
        ids[name] = cur.lastrowid
    # 把两个部门挂到中心下
    c.execute("UPDATE org_nodes SET parent_id=? WHERE id=?", (ids[PREFIX + 'center'], ids[PREFIX + 'dept_a']))
    c.execute("UPDATE org_nodes SET parent_id=? WHERE id=?", (ids[PREFIX + 'center'], ids[PREFIX + 'dept_b']))
    # 任命：U_ARCH 为 dept_a 的部门长（→ 管辖 dept_a 及其后代）
    role_key = 'dept_head'
    if not c.execute("SELECT 1 FROM org_roles WHERE node_type='dept' AND role_key=?", (role_key,)).fetchone():
        role_key = 'group_leader'
    # ⚠️ member_id 要**先查出来再单独执行** ——
    #    嵌套在 INSERT 的参数里 execute() 会让 sqlite3 游标互相干扰，
    #    实测导致任命行根本没插进去（架构负责人身份识别失败）。
    member_row = c.execute("SELECT id FROM team_members WHERE account=?", (U_ARCH,)).fetchone()
    member_id = member_row[0]
    cur = c.execute("""INSERT INTO org_appointments (node_id, member_id, role_key, is_primary, created_at)
                       VALUES (?,?,?,1,?)""",
                    (ids[PREFIX + 'dept_a'], member_id, role_key, now))
    appt_id = cur.lastrowid
    # 看板：归属 dept_a
    bid = 'P' + str(int(time.time() * 1000))[-12:]
    c.execute("INSERT INTO boards (board_id, board_name, workspace_id, owner, sort, created_at) "
              "VALUES (?,?,'','',0,?)", (bid, PREFIX + '看板', now))
    cur = c.execute("""INSERT INTO board_config (board_id, dept, dept_node_id, attr, status, remark, created_at)
                       VALUES (?,?,?,?,?,'',?)""",
                    (bid, PREFIX + 'dept_a', ids[PREFIX + 'dept_a'], '日常', '启用', now))
    cfg_id = cur.lastrowid
    c.commit()
    c.close()
    return {'node_a': ids[PREFIX + 'dept_a'], 'node_b': ids[PREFIX + 'dept_b'],
            'node_c': ids[PREFIX + 'center'], 'board': bid, 'cfg': cfg_id, 'appt': appt_id}


def fixture_selfcheck(fx):
    """夹具自检（2026-11-02 立规的延伸）：断言夹具真的造出了预期的身份。
    ⚠️ 不做这一步 → 「夹具没生效」会被误判成「功能坏了」，
    排查方向完全跑偏（本轮就踩过：嵌套 execute 导致任命行没插进去）。
    """
    from app.app import dbq, me
    from app.perm import _arch_leader_nodes
    leaders = _arch_leader_nodes(dbq, U_ARCH)
    ok(fx['node_a'] in leaders, '夹具自检：U_ARCH 是 dept_a 的架构负责人')
    r = me(U_ARCH)
    ok(fx['board'] in (r.get('editable_boards') or []),
       '夹具自检：U_ARCH 可配置归属 dept_a 的看板')
    ok(len(r.get('arch_scope') or []) >= 1, '夹具自检：U_ARCH 有架构管辖范围')
    ok(fx['node_b'] not in (r.get('arch_scope') or []),
       '夹具自检：dept_b 在 U_ARCH 管辖范围外（用于验证置灰）')


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        c.execute("DELETE FROM board_config WHERE board_id=?", (fx['board'],))
        c.execute("DELETE FROM boards WHERE board_id=?", (fx['board'],))
        c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
                  (PREFIX + '%',))
        c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    for acct in (U_ADMIN, U_ARCH, U_VIEWER):
        c.execute("DELETE FROM users WHERE username=?", (acct,))
        c.execute("DELETE FROM team_members WHERE account=?", (acct,))
    c.commit()
    c.close()


PROBE = r"""
(function(){
  function vis(id){var e=document.getElementById(id);if(!e)return 'MISSING';
    return (e.style.display==='none'||getComputedStyle(e).display==='none')?'H':'V';}
  var bands=[].slice.call(document.querySelectorAll('.tb-navgroup .tb-band')).map(function(e){
    var b=e.getBoundingClientRect();
    return {id:e.id||'',title:(e.querySelector('.tb-band-title')||{}).textContent||'',
            y:Math.round(b.y),display:getComputedStyle(e).display};
  }).sort(function(a,b){return a.y-b.y;});
  var hdrIds=[].slice.call(document.querySelectorAll('.header-actions .header-btn')).map(function(b){return b.id;});
  return {
    ready:(typeof ME!=='undefined'&&!!ME),
    user:(typeof ME!=='undefined'&&ME)?ME.username:'',
    bandTitles:bands.map(function(b){return b.title;}),
    archBand:vis('archEntryBand'),boardBand:vis('boardEntryBand'),
    wgBtn:vis('wgBtn'),boardCfgBtn:vis('boardConfigBtn'),
    hdrHasWg:hdrIds.indexOf('wgBtn')>=0,
    hdrHasBoardCfg:hdrIds.indexOf('boardConfigBtn')>=0,
    roNodes:document.querySelectorAll('.org-node-ro').length,
    allNodes:document.querySelectorAll('.org-node-row').length,
    role:(document.getElementById('roleTag')||{}).textContent||''
  };
})()
"""


async def main():
    fx = setup()
    print('\n【夹具自检】')
    fixture_selfcheck(fx)
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_profile_%d' % PORT)
    shutil.rmtree(profile, ignore_errors=True)
    subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})

            async def login(user):
                await send('Page.navigate', {'url': BASE + '/login'})
                await asyncio.sleep(2)
                await ev("document.getElementById('u').value=%s;"
                         "document.getElementById('p').value=%s;"
                         "document.getElementById('btn').click();" % (json.dumps(user), json.dumps(PWD)))
                # ⚠️ 就绪判据用 **ME**（/api/me 返回后才赋值）——
                #    用 tbDepts 判断是错的：它在静态 HTML 里就存在，登录失败也会「就绪」。
                for _ in range(40):
                    await asyncio.sleep(0.5)
                    if await ev("typeof ME!=='undefined'&&!!ME"):
                        break
                await asyncio.sleep(1.5)

            # ── 用例 A/B：管理员 ──
            print('\n【用例A/B】管理员：菜单顺序与入口可见')
            await login(U_ADMIN)
            d = await ev(PROBE)
            if isinstance(d, dict) and d.get('__error__'):
                print('  （诊断）' + d['__error__']); return 1
            ok(d.get('ready') is True, '主页面就绪（ME 已加载）')
            ok(d.get('user') == U_ADMIN, '登录身份正确：%s' % d.get('user'))
            titles = d.get('bandTitles') or []
            print('  导航带顺序：%s' % ' → '.join(titles))
            ok(titles[:2] == ['架构部门', '架构管理'], '架构管理带紧随架构部门带之后')
            ok(titles[2:4] == ['可选看板', '看板管理'], '看板管理带紧随可选看板带之后')
            ok(d.get('hdrHasWg') is False, '顶栏已无【架构管理】按钮（已移至导航带）')
            ok(d.get('hdrHasBoardCfg') is False, '顶栏已无【看板管理】按钮（已移至导航带）')
            ok(d.get('archBand') == 'V', '管理员：架构管理入口带可见')
            ok(d.get('boardBand') == 'V', '管理员：看板管理入口带可见')
            ok(d.get('wgBtn') == 'V', '管理员：架构管理按钮可点')
            ok(d.get('boardCfgBtn') == 'V', '管理员：看板管理按钮可点')

            # ── 用例 C：架构负责人 ──
            print('\n【用例C】架构负责人：入口可见 + 范围内可配 + 范围外置灰')
            await login(U_ARCH)
            d = await ev(PROBE)
            ok(d.get('ready') is True, '主页面就绪')
            ok(d.get('archBand') == 'V', '架构负责人：架构管理入口带可见')
            ok(d.get('boardBand') == 'V', '架构负责人：看板管理入口带可见')
            # 打开架构管理 → 检查范围外节点置灰
            await ev("document.getElementById('wgBtn').click()")
            await asyncio.sleep(2.5)
            d2 = await ev(PROBE)
            ok(d2.get('allNodes', 0) > 0, '架构管理弹窗打开，树已渲染（%s 个节点）' % d2.get('allNodes'))
            ok(d2.get('roNodes', 0) > 0,
               '管辖范围外的节点被置灰（%s/%s 个置灰）' % (d2.get('roNodes'), d2.get('allNodes')))
            # 置灰节点点击应被拒绝（不进配置区）
            roClick = await ev(r"""(function(){
              var ro=document.querySelector('.org-node-ro');
              if(!ro)return {found:false};
              ro.click();
              return {found:true, title:(document.getElementById('g_form_title')||{}).textContent||''};
            })()""")
            ok(isinstance(roClick, dict) and roClick.get('found') is True, '存在置灰节点')
            await ev("closeModal('wgModal')")
            await asyncio.sleep(1)
            # 打开看板管理 → 只列可配置看板
            await ev("document.getElementById('boardConfigBtn').click()")
            await asyncio.sleep(2.5)
            bc = await ev(r"""(function(){
              var items=document.querySelectorAll('#bcList .bc-item');
              var roles=[];
              items.forEach(function(e){var t=e.querySelector('.bc-role-tag');roles.push(t?t.textContent:'');});
              return {count:items.length,roles:roles};
            })()""")
            ok(isinstance(bc, dict) and bc.get('count', 0) == 1,
               '看板管理只列可配置的看板（%s 个）' % (bc.get('count') if isinstance(bc, dict) else '?'))
            ok(isinstance(bc, dict) and any('架构负责人' in x for x in (bc.get('roles') or [])),
               '列表显示身份徽标（架构负责人）：%s' % (bc.get('roles') if isinstance(bc, dict) else '?'))
            # 选中 → 保存负责人按钮应可用（架构负责人可指派）
            await ev("(function(){var it=document.querySelector('#bcList .bc-item');if(it)it.click();})()")
            await asyncio.sleep(1.5)
            d3 = await ev(r"""(function(){
              return {assign:!!document.querySelector('button[onclick*="saveBoardAcl"]'),
                      save:!!document.querySelector('button[onclick*="submitBoardConfigForm"]')};
            })()""")
            ok(d3.get('assign') is True, '架构负责人：可指定看板负责人（保存负责人按钮可见）')
            ok(d3.get('save') is True, '架构负责人：可保存看板配置')
            await ev("closeModal('boardConfigModal')")
            await asyncio.sleep(1)

            # ── 用例 D：只读 ──
            print('\n【用例D】只读：两个入口带整带隐藏')
            await login(U_VIEWER)
            d = await ev(PROBE)
            ok(d.get('ready') is True, '主页面就绪')
            ok(d.get('archBand') == 'H', '只读：架构管理入口带隐藏')
            ok(d.get('boardBand') == 'H', '只读：看板管理入口带隐藏')
            ok(d.get('wgBtn') in ('H', 'MISSING'), '只读：架构管理按钮不可用')
            ok(d.get('boardCfgBtn') in ('H', 'MISSING'), '只读：看板管理按钮不可用')

            # ── 用例 E：接口侧越权拦截 ──
            print('\n【用例E】接口侧：只读账号调看板管理写接口 → 403')
            # ⚠️ 必须用**真实存在的看板 id** —— 用假 id 会先撞 404「看板不存在」，
            #    把真正的权限判定盖掉（实测踩过：404 掩盖 403）。
            res = await ev(r"""(async function(){
              var t=localStorage.getItem('tk')||'';
              var r=await fetch('/api/boards/'+encodeURIComponent(%s)+'/acl',{method:'PUT',
                headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},
                body:JSON.stringify({owner:'x'})});
              return {code:r.status, body:(await r.text()).slice(0,300)};
            })()""" % json.dumps(fx['board']), aw=True)
            ok(isinstance(res, dict) and res.get('code') == 403,
               '只读账号指派看板负责人 → 403（实际 %s）' % (res.get('code') if isinstance(res, dict) else res))
            ok(isinstance(res, dict) and 'PERMISSION_DENIED' in (res.get('body') or ''),
               '返回统一越权错误体（PermError）：%s' % (res.get('body') if isinstance(res, dict) else '')[:90])
    finally:
        cleanup(fx)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print('  FAILED: ' + f)
        return 1
    return 0


sys.exit(asyncio.run(main()))
