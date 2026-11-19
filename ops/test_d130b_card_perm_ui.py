# -*- coding: utf-8 -*-
"""#124/#130 CDP 实测：非负责人的前端拦截（待办新增行隐藏 / 状态按钮 toast 禁止）"""
import asyncio, json, os, sqlite3, shutil, subprocess, sys, time, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9437
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
P = '__pm_'
BID = P + 'board'
CA = P + 'cardA'
CB = P + 'cardB'
U1 = P + 'u1'
PASS, FAIL = [], []


def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  ✗    ') + m)


def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id=? OR card_name LIKE ?", (BID, P + '%'))
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM board_columns WHERE board_id=?", (BID,))
    c.execute("DELETE FROM boards WHERE board_id=?", (BID,))
    c.execute("DELETE FROM actions WHERE card_id LIKE ?", (P + '%',))
    c.execute("DELETE FROM users WHERE username=?", (U1,))
    c.execute("DELETE FROM team_members WHERE name=? OR account=?", (P + '测试员', U1))
    c.commit(); c.close()


def make_fixtures():
    from app.app import hash_pw
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO boards(board_id,board_name,sort,created_at) VALUES(?,?,0,datetime('now'))",
              (BID, P + '权限测试看板'))
    c.execute("INSERT INTO board_columns(col_key,board_id,column_name,nature) VALUES(?,?,?,?)",
              (BID + '::' + P + '板块', BID, P + '板块', '日常'))
    for cid, owner, cc in ((CA, P + '测试员', ''), (CB, P + '别人', P + '测试员')):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_name,card_name,status,owner,cc,"
                  "week_no,created,deleted) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),0)",
                  (cid, BID, P + '权限测试看板', P + '板块', P + ('卡A负责人视角' if cid == CA else '卡B参与人视角'),
                   'open', owner, cc, '2026年第46周'))
    c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq) "
              "VALUES(?,?,?,?,?,1)", (U1, hash_pw('x'), 'x', 'editor', BID))
    c.execute("INSERT INTO team_members(name,account) VALUES(?,?)", (P + '测试员', U1))
    c.commit(); c.close()


async def main():
    import websockets
    cleanup()
    make_fixtures()
    try:
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_d130')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                          '--remote-debugging-port=%d' % PORT, '--user-data-dir=' + profile, 'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % PORT, timeout=2); break
            except Exception:
                time.sleep(0.5)
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        async with websockets.connect(ws, max_size=50 * 1024 * 1024) as w:
            i = 0

            async def send(m, p=None):
                nonlocal i; i += 1; mid = i
                await w.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
                while True:
                    msg = json.loads(await w.recv())
                    if msg.get('id') == mid:
                        return msg.get('result', {})

            async def ev(e, aw=False):
                r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
                if r.get('exceptionDetails'):
                    return {'__error__': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

            async def toasts():
                return await ev("[...document.querySelectorAll('.toast')].map(function(x){return x.textContent})")

            await send('Page.enable'); await send('Runtime.enable')
            await send('Emulation.setDeviceMetricsOverride',
                       {'width': 1600, 'height': 950, 'deviceScaleFactor': 1, 'mobile': False})
            await send('Page.navigate', {'url': BASE + '/login'}); await asyncio.sleep(2)
            await ev("document.getElementById('u').value='%s';"
                     "document.getElementById('p').value='x';document.getElementById('btn').click();" % U1)
            for _ in range(40):
                await asyncio.sleep(0.5)
                if await ev("typeof ME!=='undefined'&&!!ME"):
                    break
            await asyncio.sleep(2)
            who = await ev("ME.display_name+'/'+ME.username")
            print('登录身份：', who)

            await ev("pickBoard('%s')" % BID)
            await asyncio.sleep(2)

            print('【① 负责人视角（卡 A）：待办新增行可见 + 可添加】')
            await ev("openEdit('%s')" % CA)
            await asyncio.sleep(1.5)
            r1 = await ev("""(function(){
              var row=document.getElementById('e_subtask_add_row');
              return {rowVisible:row&&row.style.display!=='none'};
            })()""")
            ok(r1.get('rowVisible'), '负责人的待办新增入口可见')
            await ev("(function(){var i=document.getElementById('e_subtask_new');i.value='负责人待办';addSubtask();})()")
            await asyncio.sleep(2)
            n1 = await ev("EDIT_SUBTASKS.length")
            ok(n1 == 1, '负责人成功添加待办（%s 条）' % n1)
            await ev("closeEdit();")
            await asyncio.sleep(1)

            print('【② 参与人视角（卡 B）：新增行隐藏 + 状态按钮拦截】')
            await ev("openEdit('%s')" % CB)
            await asyncio.sleep(1.5)
            r2 = await ev("""(function(){
              var row=document.getElementById('e_subtask_add_row');
              return {rowHidden:row&&row.style.display==='none'};
            })()""")
            ok(r2.get('rowHidden'), '非负责人的待办新增入口已隐藏')
            # 点头部状态按钮选「已完成」→ 拦截 toast
            await ev("pickStatus('e','done')")
            await asyncio.sleep(1)
            t2 = await toasts()
            joined = '|'.join(t2 or [])
            ok('仅事项负责人' in joined, '状态按钮拦截提示：%s' % joined[-60:])
            st = await ev("(window._editCard||{}).status")
            ok(st == 'open', '状态未被修改（仍为 open）')
            await ev("closeEdit();")

            print('【③ 详情弹窗状态按钮同样拦截】')
            await ev("openDetail('%s')" % CB)
            await asyncio.sleep(2)
            await ev("pickStatus('d','done')")
            await asyncio.sleep(1)
            t3 = await toasts()
            joined3 = '|'.join(t3 or [])
            ok('仅事项负责人' in joined3, '详情弹窗状态按钮拦截：%s' % joined3[-60:])
            await ev("closeModal('detailModal')")
    finally:
        cleanup()
        c = sqlite3.connect(DB)
        left = c.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE ?", (P + '%',)).fetchone()[0]
        c.close()
        print('残留自查：cards=%d（应为 0）' % left)

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  -', f)


if __name__ == '__main__':
    asyncio.run(main())
