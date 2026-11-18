# -*- coding: utf-8 -*-
"""T-205ab：板块复制连带完整复制全部事项 CDP + API 实测（2026-11-18）
用户需求：复制板块时连同该板块下的全部事项（含所有子项、配置及相关数据）一并
完整复制，不得遗漏；复制后副本事项与原板块完全一致。
① 板块配置（负责人/参与人/性质/归属年份/完成情况）随附（原实现连 owner/participants 都丢）；
② 事项全字段保真复制（状态/完成时间/创建人/创建时间/日期/周数/逾期结算…逐列比对）；
③ 子事项层级保持（子→主重映射，实测三层：主→子→孙）；
④ 勾选清单（card_subtasks）全量复制（勾选状态/勾选人/勾选时间/子任务层级）；
⑤ 原板块零改动（复制前后源数据逐字节一致）；⑥ CDP 弹窗文案 + 真实提交流程。
夹具（__t205ab_ 前缀）测完即删。
⚠️ 坑：POST subtasks 返回体只有 {ok:true} 无 id → 层级/勾选场景先 POST 再 GET 回读按标题取 id。"""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BOARD = 'BCP1793717004248'
TK = make_token('admin')
DB = 'src/app.db'
SRC_NAME = '__t205ab_源板块'
# cards 表复制时的重映射字段（身份与归属）—— 其余字段必须逐列保真
REMAP = {'card_id', 'board_id', 'board_name', 'column_id', 'column_name',
         'workspace_id', 'parent_id', 'copy_from', 'pinned'}
_n = {'ok': 0, 'fail': 0}
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    _n['ok' if cond else 'fail'] += 1

def api(path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TK)
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def db_rows(sql, params=()):
    """只读直连（数据核对用；本地 app.db 是副本库，读无风险）"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

def col_row(key):
    rs = db_rows('SELECT * FROM board_columns WHERE col_key=?', (key,))
    return rs[0] if rs else None

def cards_of(colkey):
    """板块下全部未删卡（含子项）—— 按 column_id 匹配，兼容存量空 column_id 双匹配"""
    cid = (col_row(colkey) or {}).get('column_id', '')
    return db_rows('SELECT * FROM cards WHERE board_id=? AND deleted=0'
                   " AND (column_id=? OR (column_id='' AND column_name=?)) ORDER BY card_id",
                   (BOARD, cid, colkey.split('::', 1)[1]))

def subs_of(card_ids):
    if not card_ids: return []
    marks = ','.join('?' * len(card_ids))
    return db_rows('SELECT * FROM card_subtasks WHERE card_id IN (%s) ORDER BY id' % marks, card_ids)

def subtask_ids(cid):
    """GET 回读某卡的勾选清单 id（POST 返回体无 id，只能回读）"""
    stq, dq = api('/api/cards/%s/subtasks' % cid)
    flat = dq.get('flat') or dq.get('subtasks') or []
    return {t.get('title'): t.get('id') for t in flat if t.get('title')}

async def main():
    import websockets
    col_key = None; copy_key = None; ui_key = None
    card_ids = {}
    try:
        # ── 夹具：源板块（专项/负责人/参与人/已完成）+ 4 卡（三层）+ 4 勾选 ──
        st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': SRC_NAME,
                                            'nature': '专项', 'year': '2026', 'created_at': '2026-11-18',
                                            'owner': 'hly', 'participants': 'hqx', 'completion': 'done'})
        if st in (200, 201): col_key = d.get('col_key')
        ok(bool(col_key), '夹具源板块创建（专项/负责人 hly/参与人 hqx/已完成）')
        for name, fields in [
            ('__t205ab_卡甲', {'column_name': SRC_NAME, 'owner': 'hly', 'cc': 'hqx',
                              'begin': '2026-11-10', 'due': '2026-12-20', 'week_no': '2026年第46周',
                              'description': '原始描述文本', 'priority': 'high', 'label': '重要'}),
            ('__t205ab_卡乙', {'column_name': SRC_NAME, 'begin': '2026-11-05', 'owner': 'hly'}),
            ('__t205ab_子一', {'column_name': SRC_NAME, 'owner': 'hly'}),
            ('__t205ab_孙一', {'column_name': SRC_NAME}),
        ]:
            stc, dc = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': name, 'fields': fields})
            if stc in (200, 201): card_ids[name] = dc.get('card_id')
        # 层级：子一 → 卡乙；孙一 → 子一（三层：主→子→孙）
        api('/api/cards/' + card_ids['__t205ab_子一'], 'PUT', {'fields': {'parent_id': card_ids['__t205ab_卡乙']}})
        api('/api/cards/' + card_ids['__t205ab_孙一'], 'PUT', {'fields': {'parent_id': card_ids['__t205ab_子一']}})
        # 卡甲置为已完成（completed 显式随附；overdue_days 由后端按截止日结算）
        api('/api/cards/' + card_ids['__t205ab_卡甲'], 'PUT',
            {'fields': {'status': 'done', 'completed': '2026-12-01 10:00:00'}})
        # 勾选清单：卡甲 2 顶层（其一已完成）+1 层级子任务；卡乙 1 顶层
        # ⚠️ POST 返回体只有 {ok:true} 无 id → 先建再回读
        for cid, title in [(card_ids['__t205ab_卡甲'], '__t205ab_勾甲一'),
                           (card_ids['__t205ab_卡甲'], '__t205ab_勾甲二'),
                           (card_ids['__t205ab_卡乙'], '__t205ab_勾乙一')]:
            api('/api/cards/%s/subtasks' % cid, 'POST', {'title': title})
        idmap_a = subtask_ids(card_ids['__t205ab_卡甲'])
        t1 = idmap_a.get('__t205ab_勾甲一'); t2 = idmap_a.get('__t205ab_勾甲二')
        api('/api/cards/%s/subtasks' % card_ids['__t205ab_卡甲'], 'POST',
            {'title': '__t205ab_勾甲一之子', 'parent_id': t1})
        api('/api/cards/%s/subtasks/%s' % (card_ids['__t205ab_卡甲'], t2), 'PUT', {'done': 1})
        pre_cards = cards_of(col_key)
        pre_subs = subs_of([c['card_id'] for c in pre_cards])
        pre_col = col_row(col_key)
        ok(len(pre_cards) == 4 and len(pre_subs) == 4 and pre_col.get('owner') == 'hly',
           '夹具落库：4 卡（三层）+ 4 勾选 + 板块负责人（实际 %d 卡 / %d 勾选）'
           % (len(pre_cards), len(pre_subs)))
        pre_done = [s for s in pre_subs if s['title'] == '__t205ab_勾甲二'][0]
        ok(pre_done.get('done') == 1 and pre_done.get('done_by') == 'admin',
           '夹具勾选状态落库（勾甲二 done=1、勾选人 admin；实际 done=%s done_by=%s）'
           % (pre_done.get('done'), pre_done.get('done_by')))

        # ── CDP：弹窗文案 + 真实提交流程 ──
        profile = os.path.join(os.environ.get('TEMP', '.'), 'cdp_t205ab')
        shutil.rmtree(profile, ignore_errors=True)
        subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
                          '--disable-gpu', '--no-first-run', '--window-size=1700,960',
                          '--remote-debugging-port=9669', '--user-data-dir=' + profile,
                          'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:9669/json/version', timeout=2); break
            except Exception: time.sleep(0.5)
        t = json.loads(urllib.request.urlopen('http://127.0.0.1:9669/json', timeout=5).read())
        ws = [x['webSocketDebuggerUrl'] for x in t if x.get('type') == 'page'][0]
        w = await websockets.connect(ws, max_size=50 * 1024 * 1024)
        pending = {}
        async def reader():
            while True:
                try: m = json.loads(await w.recv())
                except Exception: return
                if m.get('id') is not None and m['id'] in pending:
                    f = pending.pop(m['id'])
                    if f and not f.done(): f.set_result(m)
        seq = [0]
        async def send(mm, p=None):
            seq[0] += 1; f = asyncio.get_event_loop().create_future(); pending[seq[0]] = f
            await w.send(json.dumps({'id': seq[0], 'method': mm, 'params': p or {}}))
            return (await asyncio.wait_for(f, timeout=30)).get('result', {})
        async def ev(e, aw=False):
            r = await send('Runtime.evaluate', {'expression': e, 'returnByValue': True, 'awaitPromise': aw})
            if r.get('exceptionDetails'):
                return {'__error__': json.dumps(r['exceptionDetails'].get('exception', {}), ensure_ascii=False)[:300]}
            return r.get('result', {}).get('value')
        asyncio.get_event_loop().create_task(reader())
        await send('Page.enable'); await send('Runtime.enable')
        await send('Page.navigate', {'url': 'http://127.0.0.1:8100/'})
        await asyncio.sleep(1)
        await ev("document.cookie=%s;location.href='/';" % json.dumps('tk=%s; path=/; Max-Age=86400' % TK))
        for _ in range(90):
            await asyncio.sleep(0.5)
            if await ev("typeof ME!=='undefined'&&!!ME") is True: break
        await asyncio.sleep(2.5)
        await ev("pickBoard('%s')" % BOARD)
        await asyncio.sleep(3)
        # 弹窗文案：明确「连带完整复制」与「勾选清单」，不再出现「不复制事项」
        # ⚠️ 拆两步取值：async IIFE 内联返回对象经 returnByValue 序列化偶发得 {}（实测），
        #    先 await openCopyModal 完成再单独读 DOM，稳定可靠
        payload = {'col_key': col_key, 'column_name': SRC_NAME, 'board_id': BOARD,
                   'created_at': '2026-11-18', 'nature': '专项', 'year': '2026'}
        await ev("openCopyModal('column', %s)" % json.dumps(payload, ensure_ascii=False), aw=True)
        await asyncio.sleep(0.6)
        r6 = await ev("(function(){return {tip:(document.getElementById('cp_tip')||{}).textContent,"
                      "name:(document.getElementById('cp_name')||{}).value};})()")
        ok(r6 and not r6.get('__error__') and '连带完整复制' in (r6.get('tip') or '')
           and '勾选清单' in (r6.get('tip') or '')
           and '不复制该板块下' not in (r6.get('tip') or ''),
           "⑥ 复制弹窗文案更新（连带完整复制/勾选清单；旧文案「不复制该板块下的事项」已移除；r6=%s)"
           % json.dumps(r6, ensure_ascii=False)[:100])
        ok(r6 and (r6.get('name') or '').endswith('（副本）'), "⑥ 默认副本名 = 原名 +（副本）（%s）" % (r6 or {}).get('name'))
        # 真实提交流程（submitCopy = 弹窗【创建副本】按钮的同一路径）
        await ev("document.getElementById('cp_name').value='__t205ab_源板块_UI副本';submitCopy()")
        await asyncio.sleep(3.5)
        ui_key = BOARD + '::' + '__t205ab_源板块_UI副本'
        ui_cards = cards_of(ui_key)
        ok(bool(col_row(ui_key)) and len(ui_cards) == 4,
           "⑥ CDP 真实提交（submitCopy）→ UI 副本落库且 4 卡全量随附（实际 %d 卡）" % len(ui_cards))
        await ev("closeModal('copyModal')")

        # ── API 复制（第二次，走接口路径）+ 全量一致性核对 ──
        stc, dcopy = api('/api/columns/copy', 'POST', {'col_key': col_key, 'board_id': BOARD})
        ok(stc in (200, 201) and dcopy.get('copied_cards') == 4 and dcopy.get('copied_subtasks') == 4,
           "① API 复制返回计数：事项 4 / 勾选 4（实际 %s / %s）"
           % (dcopy.get('copied_cards'), dcopy.get('copied_subtasks')))
        copy_key = dcopy.get('col_key')

        # ① 板块配置随附
        src_col = col_row(col_key); dst_col = col_row(copy_key)
        ok(dst_col and dst_col.get('copy_from') == col_key
           and dst_col.get('owner') == src_col.get('owner') == 'hly'
           and dst_col.get('participants') == src_col.get('participants') == 'hqx'
           and dst_col.get('nature') == '专项' and dst_col.get('year') == '2026'
           and dst_col.get('completion') == 'done',
           "① 板块配置完整随附：负责人/参与人/性质/年份/完成情况（原实现遗漏 owner/participants）")

        # ② 事项全字段保真（逐列比对，仅重映射字段豁免）
        src_cards = cards_of(col_key); dst_cards = cards_of(copy_key)
        by_copy_from = {c.get('copy_from'): c for c in dst_cards}
        cols_meta = [r['name'] for r in db_rows('PRAGMA table_info(cards)')]
        diff = []
        for s in src_cards:
            dcard = by_copy_from.get(s['card_id'])
            if not dcard: diff.append('%s 缺副本' % s['card_name']); continue
            for k in cols_meta:
                if k in REMAP: continue
                if s.get(k) != dcard.get(k):
                    diff.append('%s.%s: %r≠%r' % (s['card_name'], k, s.get(k), dcard.get(k)))
        ok(len(src_cards) == 4 and len(dst_cards) == 4 and not diff,
           "② 事项全字段保真复制（4 卡逐列一致；差异：%s）" % (diff[:4] or '无'))

        # ③ 子事项层级保持（子→主、孙→子）
        inv = {c['card_name']: c['card_id'] for c in src_cards}
        dm = {c.get('copy_from'): c for c in dst_cards}
        hier_ok = (dm[inv['__t205ab_子一']]['parent_id'] == dm[inv['__t205ab_卡乙']]['card_id']
                   and dm[inv['__t205ab_孙一']]['parent_id'] == dm[inv['__t205ab_子一']]['card_id'])
        ok(hier_ok, "③ 子事项层级保持：子→新主、孙→新子（三层结构不变）")

        # ④ 勾选清单：数量 + 逐条字段 + 层级
        src_subs = subs_of([c['card_id'] for c in src_cards])
        dst_subs = subs_of([c['card_id'] for c in dst_cards])
        title_of = {}
        for s in src_subs:
            title_of[(by_copy_from[s['card_id']]['card_id'], s['title'])] = s
        sdiff = []
        for dsub in dst_subs:
            ssub = title_of.get((dsub['card_id'], dsub['title']))
            if not ssub: sdiff.append('多余:%s' % dsub['title']); continue
            for k in ('done', 'sort', 'done_by', 'done_at', 'created_by', 'created_at'):
                if ssub.get(k) != dsub.get(k):
                    sdiff.append('%s.%s: %r≠%r' % (dsub['title'], k, ssub.get(k), dsub.get(k)))
        src_t1 = [s for s in src_subs if s['title'] == '__t205ab_勾甲一'][0]
        src_t1c = [s for s in src_subs if s['title'] == '__t205ab_勾甲一之子'][0]
        dst_t1 = [s for s in dst_subs if s['title'] == '__t205ab_勾甲一'][0]
        dst_t1c = [s for s in dst_subs if s['title'] == '__t205ab_勾甲一之子'][0]
        sub_hier = dst_t1c['parent_id'] == dst_t1['id'] and src_t1c['parent_id'] == src_t1['id']
        done_sub = [s for s in dst_subs if s['title'] == '__t205ab_勾甲二'][0]
        ok(len(src_subs) == 4 and len(dst_subs) == 4 and not sdiff,
           "④ 勾选清单全量复制（4 条逐字段一致；差异：%s）" % (sdiff[:4] or '无'))
        ok(sub_hier, "④ 勾选子任务层级保持（勾甲一之子 → 新勾甲一）")
        ok(done_sub.get('done') == 1 and (done_sub.get('done_by') or '') != '',
           "④ 已完成勾选状态随附（done=1、勾选人=%s）" % done_sub.get('done_by'))

        # ⑤ 完成状态保真：卡甲 done + completed 日期随附
        sA = [c for c in src_cards if c['card_name'] == '__t205ab_卡甲'][0]
        dA = dm[sA['card_id']]
        ok(dA.get('status') == 'done' and dA.get('completed') == sA.get('completed')
           and dA.get('overdue_days') == sA.get('overdue_days'),
           "⑤ 完成状态/完成时间/逾期结算保真（status=done、completed=%s、逾期=%s）"
           % (dA.get('completed'), dA.get('overdue_days')))

        # ⑦ 源板块零改动（复制前后逐字节一致）
        post_cards = cards_of(col_key); post_subs = subs_of([c['card_id'] for c in post_cards])
        post_col = col_row(col_key)
        ok(post_col == pre_col and post_cards == pre_cards and post_subs == pre_subs,
           "⑦ 源板块零改动（板块行/4 卡/4 勾选复制前后逐字节一致）")

        print('---- 结果: %d PASS / %d FAIL ----' % (_n['ok'], _n['fail']), flush=True)
    finally:
        try:
            # 勾选清单：按卡回读后逐条删（POST/PUT/DELETE 全走 API）
            for c in list(card_ids.values()):
                for tid in subtask_ids(c).values():
                    if tid: api('/api/cards/%s/subtasks/%s' % (c, tid), 'DELETE')
            for cid in list(card_ids.values()):
                if cid: api('/api/cards/' + cid, 'DELETE')
            # 副本下的卡/勾选也要删（copy_from 指向源卡，按板块捞）
            for k in (copy_key, ui_key):
                if not k: continue
                kcards = cards_of(k)
                for c in kcards:
                    for tid in subtask_ids(c['card_id']).values():
                        if tid: api('/api/cards/%s/subtasks/%s' % (c['card_id'], tid), 'DELETE')
                for c in kcards:
                    api('/api/cards/' + c['card_id'], 'DELETE')
                api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
            if col_key:
                api('/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
        except Exception as ex:
            print('cleanup err', ex, flush=True)
        if w:
            try: await w.close()
            except Exception: pass
        from cdp_test_helper import kill_profile_chrome
        kill_profile_chrome('cdp_t205ab')
        shutil.rmtree(profile, ignore_errors=True)

asyncio.run(main())
print('结果: %d PASS / %d FAIL' % (_n['ok'], _n['fail']))
if _n['fail']: sys.exit(1)
