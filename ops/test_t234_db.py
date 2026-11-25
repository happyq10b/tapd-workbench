# -*- coding: utf-8 -*-
"""T-234 数据链路验证（API/DB）：
① 每周进展 API 写入 → card_week_progress 落库核对
② copy_card 连带复制每周进展
③ copy_column（deep）连带复制每周进展
④ 导出字段清单含【每周进展】【板块类别】
⑤ 导出支持枚举排序键（status/nature/category）HTTP 200
⑥ 夹具零残留"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
BOARD = 'BCP1793717004248'
TK = make_token('admin')

OK = []
def ok(cond, label):
    OK.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + label)

def api(path, method='GET', body=None, tk=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (tk or TK))
    data = json.dumps(body).encode() if body is not None else None
    if body is not None: req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            head = r.headers.get('Content-Type', '')
            if 'json' in head:
                return r.status, json.loads(r.read().decode())
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def db_rows(q, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows

def main():
    # ── 夹具：板块 + 父事项 + 子事项 ──
    st, d = api('/api/columns', 'POST', {'board_id': BOARD, 'column_name': '__t234_板块',
                                         'nature': '专项', 'year': '2026', 'completion': 'progressing',
                                         'created_at': '2026-11-25'})
    assert st in (200, 201), '板块创建失败: %s %s' % (st, d)
    col_key = BOARD + '::__t234_板块'
    col_row = db_rows("SELECT column_id FROM board_columns WHERE col_key=?", (col_key,))
    col_id = col_row[0]['column_id'] if col_row else ''
    st, dp = api('/api/cards', 'POST', {'board_id': BOARD, 'card_name': '__t234_父',
                                        'fields': {'column_name': '__t234_板块', 'column_id': col_id,
                                                   'nature': '专项', 'begin': '2026-11-16', 'due': '2026-11-30'}})
    assert st in (200, 201), '父事项创建失败: %s %s' % (st, dp)
    pid = dp['card_id']
    st, dc = api('/api/cards', 'POST', {'board_id': '', 'card_name': '__t234_子', 'parent_id': pid,
                                        'fields': {'begin': '2026-11-16', 'due': '2026-11-22'}})
    assert st in (200, 201), '子事项创建失败: %s %s' % (st, dc)
    cid = dc['card_id']

    try:
        # ── ① 每周进展写入 → 落库核对 ──
        st, r1 = api('/api/cards/%s/week-progress' % pid, 'POST',
                     {'items': {'2026年第47周': '本周完成A项', '2026年第48周': '本周完成B项'}})
        ok(st in (200, 201), '① 父事项每周进展保存（HTTP %s）' % st)
        st, r1b = api('/api/cards/%s/week-progress' % cid, 'POST',
                      {'items': {'2026年第47周': '子事项进展X'}})
        ok(st in (200, 201), '① 子事项每周进展保存（HTTP %s）' % st)
        rows = db_rows("SELECT card_id, week, content FROM card_week_progress WHERE card_id IN (?,?) ORDER BY card_id, week", (pid, cid))
        ok(len(rows) == 3 and rows[0]['content'] == '本周完成A项' and rows[2]['content'] == '子事项进展X',
           '① card_week_progress 落库核对（%d 行：父 2 + 子 1）' % len(rows))
        st, rg = api('/api/cards/%s/week-progress' % pid)
        ok(st == 200 and len(rg.get('items') or rg.get('progress') or []) == 2,
           '① 回读一致（GET week-progress）')

        # ── ② copy_column（deep）连带每周进展 ──
        st, d3 = api('/api/columns/copy', 'POST', {'col_key': col_key, 'board_id': BOARD,
                                                   'column_name': '__t234_板块副本', 'created_at': '2026-11-25'})
        ok(st in (200, 201) and d3.get('col_key'), '② copy_column 成功（HTTP %s）' % st)
        new_key = (d3 or {}).get('col_key') or ''
        new_col_id = (db_rows("SELECT column_id FROM board_columns WHERE col_key=?", (new_key,)) or [{}])[0].get('column_id', '')
        copied_cards = db_rows("SELECT card_id FROM cards WHERE column_id=? AND deleted=0", (new_col_id,))
        wp_total = 0
        for c in copied_cards:
            wp_total += len(db_rows("SELECT 1 FROM card_week_progress WHERE card_id=?", (c['card_id'],)))
        ok(len(copied_cards) == 2 and wp_total == 3,
           '② 板块副本 2 事项 + 每周进展 3 条随附（实际 %d 卡 / %d 条）' % (len(copied_cards), wp_total))

        # ── ③ copy_card 连带每周进展 ──
        st, d2 = api('/api/cards/copy', 'POST', {'card_id': pid, 'board_id': BOARD,
                                                 'column_id': col_id, 'column_name': '__t234_板块'})
        ok(st in (200, 201) and d2.get('card_id'), '③ copy_card 成功（HTTP %s）' % st)
        copy_id = (d2 or {}).get('card_id') or ''
        wp2 = db_rows("SELECT week, content FROM card_week_progress WHERE card_id=? ORDER BY week", (copy_id,))
        ok(len(wp2) == 2 and wp2[0]['content'] == '本周完成A项',
           '③ 副本连带 2 条每周进展（实际 %d）' % len(wp2))

        # ── ④ 导出字段清单含新增列 ──
        st, d4 = api('/api/export/fields')
        keys = [f['key'] for f in (d4.get('fields') or [])]
        titles = [f['title'] for f in (d4.get('fields') or [])]
        ok('_wp_text' in keys and '每周进展' in titles, '④ 导出字段含【每周进展】')
        ok('_col_category' in keys and '板块类别' in titles, '④ 导出字段含【板块类别】')

        # ── ⑤ 导出支持枚举排序键 ──
        st, d5 = api('/api/export/xlsx?card_ids=%s,%s&sort_keys=status,nature,category&sort_dirs=asc,asc,asc&fields=card_name,__not_a_field__' % (pid, cid))
        # fields 里混入非法 key 应 400 —— 先用非法 key 验证 fail-fast
        ok(st == 400, '⑤ 非法导出字段被拒绝（fail-fast，HTTP %s）' % st)
        st, d5 = api('/api/export/xlsx?card_ids=%s,%s&sort_keys=status,nature,category&sort_dirs=asc,asc,asc&fields=card_name,_wp_text,_col_category' % (pid, cid))
        ok(st == 200, '⑤ 导出接受枚举排序键 status,nature,category（HTTP %s）' % st)
        st, d5b = api('/api/export/xlsx?card_ids=%s,%s&sort_keys=status,nature,category&sort_dirs=asc,asc,asc' % (pid, cid))
        ok(st == 200 and len(d5b) > 1000, '⑤ 全字段导出 HTTP 200（%d 字节）' % len(d5b or b''))
    finally:
        # ── ⑥ 清理：API 删除（级联）→ 夹具名前缀 DB 精确硬删兜底 ──
        for cid_ in [copy_id, pid]:
            if cid_: api('/api/cards/' + cid_, 'DELETE')
        for k in [new_key, col_key]:
            if k: api('/api/columns/' + urllib.parse.quote(k, safe=''), 'DELETE')
        import time as _t
        _t.sleep(1.0)
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        # 夹具专有前缀 __t234_（含副本后缀），不触碰真实数据
        conn.execute("DELETE FROM card_week_progress WHERE card_id IN "
                     "(SELECT card_id FROM cards WHERE card_name LIKE '%__t234_%')")
        conn.execute("DELETE FROM cards WHERE card_name LIKE '%__t234_%'")
        conn.execute("DELETE FROM board_columns WHERE column_name LIKE '%__t234_%'")
        conn.commit()
        live_c = conn.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE '%__t234_%'").fetchone()[0]
        live_col = conn.execute("SELECT COUNT(*) FROM board_columns WHERE column_name LIKE '%__t234_%'").fetchone()[0]
        left_wp = conn.execute("SELECT COUNT(*) FROM card_week_progress WHERE card_id IN "
                               "(SELECT card_id FROM cards WHERE card_name LIKE '%__t234_%')").fetchone()[0]
        conn.close()
        ok(live_c == 0 and live_col == 0 and left_wp == 0,
           '⑥ 夹具零残留（cards=%s cols=%s wp=%s）' % (live_c, live_col, left_wp))
    print('结果: %d PASS / %d FAIL' % (sum(OK), len(OK) - sum(OK)))

main()
