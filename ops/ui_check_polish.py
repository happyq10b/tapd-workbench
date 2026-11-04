# -*- coding: utf-8 -*-
"""#49 UI 实测：六项 UI 打磨（②③用非管理员验证映射修复；①④⑥用 admin 验证权限相关项）。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9451
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
PREFIX = '__ui_'
PWD = 'At159357'
PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def setup():
    from app.app import hash_pw
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 13:00:00'
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)", (PREFIX + '经理', PREFIX + 'mgr', now))
    mid = c.execute("SELECT id FROM team_members WHERE account=?", (PREFIX + 'mgr',)).fetchone()[0]
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at) VALUES (?,?,?,?,?,?)",
              (PREFIX + 'mgr', hash_pw(PWD), 'editor', '*', '*', now))
    wC = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','','*')", (PREFIX + 'C',)).lastrowid
    nC = c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id,function) VALUES (?,?,?,?, '')", (PREFIX + 'C', 'center', 0, wC)).lastrowid
    c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at) VALUES (?,?,?,1,?)", (nC, mid, 'center_head', now))
    # 夹具看板（负责人=mgr）：看板管理准入要求「任一看板可配置」→ 没有它弹窗直接拦截
    bid = PREFIX + 'B1'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, PREFIX + '看板', '', PREFIX + 'mgr', now))
    row = c.execute("SELECT id FROM org_nodes WHERE name='核算部'").fetchone()
    dname = '核算部' if row else '财务中心'
    dnode = row[0] if row else 0
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,?,?,?,'',?)", (bid, dname, dnode, '日常', '启用', now))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM cards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.commit(); c.close()

async def main():
    setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_u%d' % PORT)
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
    ws = [t['webSocketDebuggerUrl'] for t in targets if t.get('type') == 'page'][0]
    try:
        async with websockets.connect(ws, max_size=30 * 1024 * 1024) as ws_:
            i = 0
            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await ws_.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await ws_.recv())
                    if msg.get('id') == mid: return msg.get('result', {})
            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'): return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')
            async def login(u):
                await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
                await ev("document.getElementById('u').value=%s;document.getElementById('p').value=%s;document.getElementById('btn').click();"
                         % (json.dumps(u), json.dumps(PWD)))
                for _ in range(40):
                    await asyncio.sleep(0.5)
                    if await ev("typeof ME!=='undefined'&&!!ME"): break
                await asyncio.sleep(2)
            async def wait_for(expr, timeout=12):
                deadline = time.time() + timeout
                while time.time() < deadline:
                    v = await ev(expr)
                    if v: return v
                    await asyncio.sleep(0.5)
                return None

            # ══════ ②③ 非管理员（映射修复的主验证） ══════
            print('\n【②③ 映射修复】非管理员 %s' % (PREFIX + 'mgr'))
            await login(PREFIX + 'mgr')
            await ev("openBoardConfigModal();")
            btn = await wait_for("document.getElementById('bcf_owner')?true:false")
            r = await ev("(function(){return {sel:!!document.querySelector('select#bcf_owner'),btn:!!document.getElementById('bcf_owner')}})()")
            ok(r.get('btn') is True and r.get('sel') is False,
               '②负责人筛选为树按钮（不再是账号下拉）：%s' % r)
            await ev("bcPickOwnerFilter(document.getElementById('bcf_owner'));")
            panel = await wait_for("document.querySelector('.tree-pick')?true:false")
            r = await ev("""(function(){
              var panel=document.querySelector('.tree-pick');if(!panel)return {found:false};
              var rows=[].slice.call(panel.querySelectorAll('.tp-node.tp-person')).filter(function(x){return x.offsetParent});
              var bad=rows.filter(function(x){return x.textContent.indexOf('未开通账号')>=0});
              var pick=rows.find(function(x){return x.textContent.indexOf('经理')>=0});
              return {found:true,personCount:rows.length,badCount:bad.length,
                      sampleText:pick?pick.textContent.trim().slice(0,40):(rows[0]?rows[0].textContent.trim().slice(0,40):'')};
            })()""")
            ok(r.get('found') is True and (r.get('personCount') or 0) > 0,
               '负责人树已打开（%s 人）' % r.get('personCount'))
            ok((r.get('badCount') or 0) == 0,
               '②树里的人不再误标「未开通账号」（误标 %s 个）' % r.get('badCount'))
            ok('（未开通账号）' not in (r.get('sampleText') or ''),
               '②已开通账号的人正常可选（%s）' % r.get('sampleText'))
            await ev("closeTreePick();")
            await ev("closeModal('boardConfigModal');")
            await asyncio.sleep(1)

            # ══════ ⑤ 架构管理重复提示（非管理员可验证） ══════
            print('\n【⑤ 架构管理提示】')
            await ev("openWgModal();")
            await asyncio.sleep(2)
            r = await ev("(function(){var h=document.getElementById('g_boards_hint');return h?h.textContent:''})()")
            ok(r == '', '未选中节点时的下方重复提示已删（实测 %r）' % r)
            r = await ev("(function(){var w=document.getElementById('g_new_boards');return w?w.textContent:''})()")
            ok('在左侧选中一个节点后' in r, '框内占位保留')
            await ev("closeModal('wgModal');")
            await asyncio.sleep(1)

            # ══════ ①④⑥ admin 视角（权限相关项） ══════
            print('\n【①④⑥ admin 视角】')
            await login('admin')
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            await ev("(function(){var it=document.querySelector('#bcList .bc-item');if(it)it.click();})()")
            sec = await wait_for("document.querySelector('#bcEditArea .bc-owner-sec')?true:false")
            r = await ev("""(function(){
              var sec=document.querySelector('#bcEditArea .bc-owner-sec');
              if(!sec)return {found:false};
              var cs=getComputedStyle(sec);
              return {found:true,border:cs.borderTopWidth};
            })()""")
            ok(r.get('found') is True, '①负责人区块带 bc-owner-sec 样式')
            ok(r.get('border') not in ('0px', '', None), '①外框存在（border=%s）' % r.get('border'))
            r = await ev("(function(){return document.body.textContent.indexOf('+ 配置')>=0})()")
            ok(r is False, '④「+ 配置」按钮已移除')
            await ev("closeModal('boardConfigModal');")
            await asyncio.sleep(1)
            await ev("openColumnModal();")
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              var o=document.getElementById('c_owner_wrap'),p=document.getElementById('c_parts_wrap');
              if(!o||!p)return {found:false};
              var ro=o.getBoundingClientRect(),rp=p.getBoundingClientRect();
              var hint=o.textContent.indexOf('负责人有权修改')>=0||p.textContent.indexOf('参与人可修改')>=0;
              return {found:true,sameRow:Math.abs(ro.top-rp.top)<4,
                      bothBordered:parseFloat(getComputedStyle(o).borderTopWidth)>0&&parseFloat(getComputedStyle(p).borderTopWidth)>0,
                      hintGone:!hint,
                      ownerBtn:o.querySelector('#c_owner_pick_btn').offsetParent!==null,
                      partsBtn:p.querySelector('#c_parts_pick_btn').offsetParent!==null};
            })()""")
            ok(r.get('found') is True, '⑥弹窗结构存在')
            ok(r.get('sameRow') is True, '⑥负责人/参与人并成一排')
            ok(r.get('bothBordered') is True, '⑥两框都有外框')
            ok(r.get('hintGone') is True, '⑥大段说明已删除')
            ok(r.get('ownerBtn') is True and r.get('partsBtn') is True, '⑥两个选择按钮可见（有指派权时）')
            await ev("closeModal('columnModal');")
    finally:
        cleanup()
        shutil.rmtree(profile, ignore_errors=True)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(asyncio.run(main()))
