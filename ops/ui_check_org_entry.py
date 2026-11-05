# -*- coding: utf-8 -*-
"""#62 UI 实测：架构编辑入口调整 + 「+子节点」分级置灰。

断言（2026-11-05 用户需求）：
  ① 点击架构目录节点 → 直接进入编辑态（标题「编辑：节点名」，不再是「节点名 · 岗位与任职」框）
  ② 树行不再有「编辑」按钮（统一以点击节点本身作为编辑入口）
  ③ 「+子节点」按钮：无权限 → 置灰不可点（disabled，非隐藏）
     - 超管：全部可用
     - 架构负责人（中心负责人）：管辖架构内可用、范围外置灰
     - 组长：常规小组下不可再建节点 → 置灰
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9433
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__oe_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    from app.app import hash_pw
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-05 09:00:00'
    # 清残留（前缀级）
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    # 账号：arch（中心负责人 C1）、lead（组长 G1）、none（无岗位）
    mids = {}
    for k in ('arch', 'lead', 'none'):
        acct = PREFIX + k
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + k, acct, now))
        mids[k] = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
                  (acct, hash_pw(PWD), 'editor', '*', '*', now))
    # workgroups 载体 + org_nodes：C1 → D1 → G1；C2 → D2（范围外）
    wids, nids = {}, {}
    for key, ptype, parent in (('C1', 'center', 0), ('C2', 'center', 0), ('D1', 'dept', None), ('D2', 'dept', None), ('G1', 'group', None)):
        wids[key] = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','', '')", (PREFIX + key,)).lastrowid
    tree = [('C1', 'center', 0), ('D1', 'dept', 'C1'), ('G1', 'group', 'D1'), ('C2', 'center', 0), ('D2', 'dept', 'C2')]
    for key, ntype, parent in tree:
        pid = nids.get(parent, 0) if isinstance(parent, str) else parent
        nids[key] = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')",
                              (PREFIX + key, ntype, pid, wids[key])).lastrowid
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wids['C1'], wids['D1']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wids['D1'], wids['G1']))
    c.execute("UPDATE workgroups SET parent_id=? WHERE id=?", (wids['C2'], wids['D2']))
    # 任命
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nids['C1'], mids['arch'], 'center_head', now))
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nids['G1'], mids['lead'], 'group_leader', now))
    c.commit(); c.close()
    return {'nids': nids}

def cleanup(fx):
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.commit(); c.close()

async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_oe%d' % PORT)
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
    page = next(t for t in targets if t.get('type') == 'page')
    ws_url = page['webSocketDebuggerUrl']
    ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
    _id = [0]
    async def send(method, params=None):
        _id[0] += 1
        await ws.send(json.dumps({'id': _id[0], 'method': method, 'params': params or {}}))
        while True:
            m = json.loads(await ws.recv())
            if m.get('id') == _id[0]:
                return m.get('result', {})
    async def ev(expr):
        r = await send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
        return r.get('result', {}).get('value')

    async def login(u, p):
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
        await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;document.getElementById('btn').click();"
                 % (json.dumps(u), json.dumps(p)))
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME"): break
        await asyncio.sleep(2)
        await ev("openWgModal();")
        await asyncio.sleep(2)

    def row_btn_probe(nid):
        return """(function(){
          var row=document.querySelector('.org-node-row[data-org-id="%d"]');
          if(!row) return {found:false};
          var b=row.querySelector('button[onclick*="addWgChild"]');
          return {found:true, addDisabled:!!(b&&b.disabled),
                  hasEdit:!!row.querySelector('button[onclick*="editWg"]')};
        })()""" % nid

    def click_row(nid):
        return "(function(){var el=document.querySelector('.org-node-row[data-org-id=\"%d\"]');if(el&&el.click)el.click();})()" % nid

    try:
        nids = fx['nids']
        # ── 超管 ──
        print('\n【超级管理员】')
        await login('admin', PWD)
        r = await ev('(function(){var rows=[].slice.call(document.querySelectorAll("#wgList .org-node-row"));'
                     'var eb=0,mis=[];'
                     'rows.forEach(function(rw){'
                     'if(rw.querySelector("button[onclick*=\'editWg\']")) eb++;'
                     'var badge=rw.querySelector("span[style*=\'border-radius:3px\']");'
                     'var t=badge?badge.textContent:"";'
                     'var b=rw.querySelector("button[onclick*=\'addWgChild\']");'
                     'var leaf=(t!=="中心"&&t!=="部门");'
                     'if(b&&b.disabled!==leaf) mis.push(t+":"+b.disabled);'
                     '});'
                     'return {editBtns:eb,mismatch:mis,total:rows.length};})()')
        ok(r.get('editBtns') == 0, '树行不再有「编辑」按钮（超管视角）')
        ok(not r.get('mismatch'), '「+子节点」置灰与节点类型一一对应（中心/部门可用，小组置灰）：%s' % r.get('mismatch'))
        # 点击节点 → 直接进入编辑态
        await ev(click_row(nids['D1']))
        await asyncio.sleep(0.5)
        r = await ev("(function(){return {title:(document.getElementById('g_form_title')||{}).textContent||'',"
                     "cancelShown:(document.getElementById('g_cancel_edit')||{}).style?document.getElementById('g_cancel_edit').style.display!=='none':false}})()")
        ok(r.get('title') == '编辑：' + PREFIX + 'D1', '点击节点 → 标题「编辑：节点名」（实际 %s）' % r.get('title'))
        ok(r.get('cancelShown') is True, '编辑态下「取消编辑」按钮可见')
        # 结构字段可编辑（超管）
        r = await ev("(()=>({nameRo:document.getElementById('g_new_name').disabled}))()")
        ok(r.get('nameRo') is False, '超管：结构字段（名称）可编辑')
        # 同节点再点 = 取消编辑
        await ev(click_row(nids['D1']))
        await asyncio.sleep(0.5)
        r = await ev("(document.getElementById('g_form_title')||{}).textContent||''")
        ok(r == '新增节点', '重复点击同一节点 → 取消编辑（实际 %s）' % r)

        # ── 架构负责人（C1 中心负责人）──
        print('\n【架构负责人】' + PREFIX + 'arch')
        await login(PREFIX + 'arch', PWD)
        for key, expect_disabled in (('C1', False), ('D1', False), ('G1', True), ('C2', True), ('D2', True)):
            r = await ev(row_btn_probe(nids[key]))
            ok(r.get('found') is True, '%s 行渲染（架构负责人视角）' % key)
            ok(r.get('addDisabled') is expect_disabled,
               '%s 行「+子节点」%s（实际 disabled=%s）' % (key, '置灰' if expect_disabled else '可用', r.get('addDisabled')))
            ok(r.get('hasEdit') is False, '%s 行无「编辑」按钮' % key)

        # ── 组长（G1 组长）──
        print('\n【组长】' + PREFIX + 'lead')
        await login(PREFIX + 'lead', PWD)
        for key, expect_disabled in (('G1', True), ('D1', True), ('C1', True)):
            r = await ev(row_btn_probe(nids[key]))
            ok(r.get('found') is True, '%s 行渲染（组长视角）' % key)
            ok(r.get('addDisabled') is expect_disabled,
               '%s 行「+子节点」置灰（实际 disabled=%s）' % (key, r.get('addDisabled')))
        # 组长点击自己组 → 编辑态（岗位与板块绑定可配，结构字段置灰）
        await ev(click_row(nids['G1']))
        await asyncio.sleep(0.5)
        r = await ev("(()=>({title:(document.getElementById('g_form_title')||{}).textContent||'',"
                     "nameRo:document.getElementById('g_new_name').disabled}))()")
        ok(r.get('title') == '编辑：' + PREFIX + 'G1', '组长点击本组 → 编辑态（实际 %s）' % r.get('title'))
        ok(r.get('nameRo') is True, '组长：结构字段置灰（结构由管理员维护）')
    finally:
        cleanup(fx)
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
