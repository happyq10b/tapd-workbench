# -*- coding: utf-8 -*-
"""#51 测试：统计卡片筛选 / 多看板 / 周数倒序 / 板块末级排序。"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__ms_'
PWD = 'At159357'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http(path, method='GET', body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}

def setup():
    from app.app import hash_pw, make_token
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-04 14:00:00'
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    bid1, bid2 = PREFIX + 'B1', PREFIX + 'B2'
    for bid, name in ((bid1, PREFIX + '看板一'), (bid2, PREFIX + '看板二')):
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)", (bid, name, '', 'admin', now))
        c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,0,'日常','启用','',?)", (bid, PREFIX + '部门', now))
        for i, (cname, y) in enumerate((('C早', '2026'), ('C晚', '2026'))):
            c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned) VALUES (?,?,?,?,?,'x','日常',?,0)",
                      (bid + '::' + cname, PREFIX + 'col_%s_%d' % (bid[-2:], i), bid, cname, now, y))
    # 卡片：B1/C早 1 done + 1 progressing；B1/C晚 1 open；B2/C早 1 done
    def ins(cid, bid, cname, st, csort):
        c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,creator,created,modified,week_no,deleted,parent_id,column_sort)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'',?)""",
                  (cid, bid, PREFIX + ('看板一' if bid == bid1 else '看板二'), PREFIX + 'col_' + ('B1_0' if cname == 'C早' else 'B1_1') if bid == bid1 else PREFIX + 'col_' + ('B2_0' if cname == 'C早' else 'B2_1'),
                   cname, PREFIX + cid, st, 'admin', now, now, '2026年第45周', csort))
    ins(PREFIX + 'K1', bid1, 'C早', 'done', '5')
    ins(PREFIX + 'K2', bid1, 'C早', 'progressing', '5')
    ins(PREFIX + 'K3', bid1, 'C晚', 'open', '9')
    ins(PREFIX + 'K4', bid2, 'C早', 'done', '3')
    c.commit(); c.close()
    return {'b1': bid1, 'b2': bid2, 'tok': make_token('admin')}

def cleanup():
    c = sqlite3.connect(DB)
    for t in ('cards', 'board_columns', 'board_config', 'boards'):
        c.execute("DELETE FROM %s WHERE board_id LIKE ?" % t, (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.commit(); c.close()

def main():
    fx = setup()
    tok = fx['tok']
    try:
        # ── ① 多看板 board_ids ──
        print('\n【多看板】board_ids')
        code, r = http('/api/cards?board_ids=%s,%s' % (fx['b1'], fx['b2']), token=tok)
        ok(code == 200 and len(r.get('cards') or []) == 4, '两看板合计 4 张卡（实际 %s）' % len(r.get('cards') or []))
        code, r = http('/api/cards?board_ids=%s' % fx['b2'], token=tok)
        ok(len(r.get('cards') or []) == 1, '单看板经 board_ids 过滤 → 1 张')
        # 概览
        code, r = http('/api/overview?board_ids=%s,%s' % (fx['b1'], fx['b2']), token=tok)
        ok(r.get('total') == 4 and r.get('done') == 2 and r.get('progressing') == 1 and r.get('open') == 1,
           'overview 多看板合计：total/done/progressing/open = %s/%s/%s/%s' % (r.get('total'), r.get('done'), r.get('progressing'), r.get('open')))
        # cols_meta 限定
        ok(len(r.get('boards') or []) == 2, 'overview 返回 2 个看板的分项')

        # ── ② 状态多选 ──
        print('\n【状态多选】')
        code, r = http('/api/cards?status=done&board_ids=%s,%s' % (fx['b1'], fx['b2']), token=tok)
        ok(len(r.get('cards') or []) == 2, 'status=done（限定夹具看板）→ 2 张')
        code, r = http('/api/cards?status=done,progressing&board_ids=%s,%s' % (fx['b1'], fx['b2']), token=tok)
        ok(len(r.get('cards') or []) == 3, 'status=done,progressing → 3 张')
        code, r = http('/api/cards?status=open&board_ids=%s' % fx['b1'], token=tok)
        ok(len(r.get('cards') or []) == 1 and r['cards'][0]['status'] == 'open', 'status=open → 1 张（未完成语义不含 progressing）')
        # 组合筛选下的 columns 计数一致性
        code, r = http('/api/cards?status=done&board_ids=%s,%s' % (fx['b1'], fx['b2']), token=tok)
        cols = r.get('columns') or []
        tot = sum(c.get('card_count', 0) for c in cols)
        ok(tot == 2, '筛选后 cols_meta 计数一致（合计 %s）' % tot)

        # ── ③ 板块末级排序（column_sort）──
        print('\n【板块末级排序】')
        # 同一板块 created_at 相同时（fixture 同 now）→ column_sort 5 < 9 → C早 在前
        code, r = http('/api/cards?board_ids=%s' % fx['b1'], token=tok)
        cols = [x['column_name'] for x in (r.get('columns') or [])]
        ok(cols and cols[0] == 'C早' and cols[1] == 'C晚',
           'created 相同 → 按 column_sort 升序（C早[5] → C晚[9]）：%s' % cols)
    finally:
        cleanup()
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0

sys.exit(main())
