#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""看板管理页脚改造的 UI 验证（2026-11-04）。

需求：
  1) 「应用到已选 N 个看板」按钮移除
  2) 「删除该看板配置」→「删除看板」（删看板本身，两次确认）
  3) 「保存负责人」+「保存配置」合并为一个【保存看板】

场景（管理员视角，夹具看板 __bf_ 前缀）：
  A. 打开看板管理 → 选中夹具看板 → 页脚按钮集合正确
  B. 「应用到已选 N 个看板」不存在
  C. 「删除看板」按钮存在、文案正确；点它 → 两次确认 → 看板真的被删掉
  D. 【保存看板】按钮存在且唯一（无「保存负责人」「保存配置」）
  E. 删除后看板从列表消失

⚠️ 夹具纪律：专属前缀 __bf_；try/finally 清理；不硬编码全局基线数字。
"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9387
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__bf_'
U_ADMIN = P + 'admin'
PWD = 'At159357'
PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  x ') + msg)


def setup():
    c = sqlite3.connect(DB)
    now = '2026-11-04 22:00:00'
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.execute("INSERT INTO team_members (name, workgroups, account, created_at) VALUES (?,'',?,?)",
              (P + U_ADMIN, U_ADMIN, now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
              " VALUES (?,?,?,?,?,?)", (U_ADMIN, hash_pw(PWD), 'admin', '*', '*', now))
    bid = 'BF' + str(int(time.time() * 1000))[-11:]
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,'','','',0,?)", (bid, P + '看板', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (bid, '核算部', 0, '日常', '启用', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,"
              "nature,year,pinned,owner,participants,completion)"
              " VALUES (?,?,?,?,?,?,?,?,0,'','',?)",
              (bid + '::' + P + 'A', P + 'col', bid, P + 'A', now, U_ADMIN, '日常', '2026', 'open'))
    c.commit(); c.close()
    return {'bid': bid}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        bid = fx['bid']
        c.execute("DELETE FROM card_subtasks WHERE card_id IN (SELECT card_id FROM cards WHERE board_id=?)", (bid,))
        c.execute("DELETE FROM cards WHERE board_id=?", (bid,))
        c.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
        c.execute("DELETE FROM board_config WHERE board_id=?", (bid,))
        c.execute("DELETE FROM boards WHERE board_id=?", (bid,))
    c.execute("DELETE FROM users WHERE username=?", (U_ADMIN,))
    c.execute("DELETE FROM team_members WHERE account=?", (U_ADMIN,))
    c.commit(); c.close()


async def main():
    fx = setup()
    profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_bf%d' % PORT)
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

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})

            # ── 登录 ──
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value=%s;"
                     "document.getElementById('p').value=%s;"
                     "document.getElementById('btn').click();" % (json.dumps(U_ADMIN), json.dumps(PWD)))
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)

            # ── A/B/D. 打开看板管理并选中夹具看板 ──
            print('\n【A/B/D】页脚按钮集合')
            await ev("openBoardConfigModal();")
            await asyncio.sleep(2.5)
            # 精确选中夹具看板（按 data-bid 定位，避免误选生产看板）
            await ev("(function(){var it=document.querySelector('#bcList .bc-item[data-bid=\"%s\"]');"
                     "if(it)it.click();})()" % fx['bid'])
            await asyncio.sleep(1.5)
            r = await ev("""(function(){
              var foot=document.querySelector('#bcEditArea .bc-footer');
              if(!foot)return {noFooter:true};
              var btns=[].slice.call(foot.querySelectorAll('button')).map(function(x){return x.textContent.trim();});
              return {btns:btns,
                      hasBulk:!!document.querySelector('button[onclick*="applyBulkConfig"]'),
                      hasSaveAll:!!document.querySelector('button[onclick*="saveBoardAll"]'),
                      hasSaveAcl:!!document.querySelector('button[onclick*="saveBoardAcl"]'),
                      hasSubmit:!!document.querySelector('button[onclick*="submitBoardConfigForm"]'),
                      hasDelOne:!!document.querySelector('button[onclick*="bcDeleteOne"]'),
                      hasDelCfg:!!document.querySelector('button[onclick*="删除该看板配置"]')};
            })()""")
            ok(isinstance(r, dict) and not r.get('noFooter'), '编辑区页脚已渲染')
            ok(isinstance(r, dict) and r.get('hasBulk') is False,
               '「应用到已选 N 个看板」按钮已移除')
            ok(isinstance(r, dict) and r.get('hasDelCfg') is False,
               '「删除该看板配置」按钮已移除')
            ok(isinstance(r, dict) and r.get('hasDelOne') is True,
               '「删除看板」按钮存在')
            ok(isinstance(r, dict) and r.get('hasSaveAll') is True,
               '【保存看板】按钮存在')
            ok(isinstance(r, dict) and r.get('hasSaveAcl') is False
               and r.get('hasSubmit') is False,
               '旧的「保存负责人」「保存配置」按钮已合并掉')
            btns = (r or {}).get('btns') or []
            ok('删除看板' in btns, '页脚按钮文案含「删除看板」（实际 %s）' % btns)
            ok('保存看板' in btns, '页脚按钮文案含「保存看板」（实际 %s）' % btns)

            # ── C. 两次确认 + 真删 ──
            print('\n【C】删除看板：两次确认 → 看板真被删')
            # 注入 confirm 计数器：前两次返回 true（放行），记录调用次数
            await ev("""(function(){
              window.__cf=0; window.__cfLog=[];
              var orig=window.confirm;
              window.confirm=function(m){ window.__cf++; window.__cfLog.push(m); return true; };
              window.__origConfirm=orig;
            })()""")
            await ev("bcDeleteOne('%s');" % fx['bid'])
            await asyncio.sleep(3)
            cf = await ev("window.__cf")
            log = await ev("window.__cfLog")
            ok(cf == 2, '删除弹了两次确认（实际 %s 次）' % cf)
            ok(isinstance(log, list) and len(log) == 2
               and '看板' in (log[0] or '') and '不可撤销' in (log[1] or ''),
               '两次确认文案含看板名与不可撤销提示')
            # 数据库侧核对
            c = sqlite3.connect(DB)
            n = c.execute("SELECT COUNT(*) FROM boards WHERE board_id=?", (fx['bid'],)).fetchone()[0]
            nc = c.execute("SELECT COUNT(*) FROM board_config WHERE board_id=?", (fx['bid'],)).fetchone()[0]
            ncol = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id=?", (fx['bid'],)).fetchone()[0]
            c.close()
            ok(n == 0, '看板本体已从 boards 表删除（实际 %s 行）' % n)
            ok(nc == 0, '看板配置已删除（实际 %s 行）' % nc)
            ok(ncol == 0, '看板下的板块已删除（实际 %s 行）' % ncol)
            # 列表侧核对
            inlist = await ev("(function(){var it=document.querySelector('#bcList .bc-item[data-bid=\"%s\"]');"
                              "return !!it;})()" % fx['bid'])
            ok(inlist is False, '删除后看板从「看板管理」列表消失')
    finally:
        cleanup(fx)
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  FAILED: ' + f)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
