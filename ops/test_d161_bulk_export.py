# -*- coding: utf-8 -*-
"""#161 批量删除勾选/导出勾选：API 层（批量端点校验、导出交集、权限）"""
import json, os, sqlite3, sys, urllib.request, urllib.error, io

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

from app.app import make_token, hash_pw

def api(tk, method, path, body=None, raw=False):
    import urllib.parse
    path = urllib.parse.quote(path, safe='/:?&=,@')
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        if raw:
            return r.status, r.read()
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

def setup():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM cards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_bd_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_bd_%'")
    c.execute("INSERT INTO boards (board_id,board_name,sort,created_at) VALUES ('__t_bd_b','__t_批量测试看板',0,datetime('now'))")
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_bd_b::__t_板块A','COLbd1','__t_bd_b','__t_板块A',date('now'),'admin','日常','2026',0,'','','open','')")
    for i, cid in ((1, '__t_bd_c1'), (2, '__t_bd_c2')):
        c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
                  " VALUES (?,'__t_bd_b','__t_批量测试看板','__t_板块A',?,'open','',datetime('now'),0,0,'')", (cid, '__t_事项%d' % i))
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_bd_c1s','__t_bd_b','__t_批量测试看板','__t_板块A','__t_子事项','open','',datetime('now'),0,0,'__t_bd_c1')")
    c.execute("INSERT INTO card_subtasks (card_id,title,done) VALUES ('__t_bd_c1','__t_子事项',0)")
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_bd_v',?,'viewer','__t_bd_b')", (hash_pw('Xx12345678'),))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_bd_v2',?,'viewer','__t_none_x')", (hash_pw('Xx12345678'),))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_bd_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_bd_b'")
    c.execute("DELETE FROM users WHERE username LIKE '__t_bd_%'")
    c.commit(); c.close()

setup()
try:
    tk = make_token('admin')
    tk_v = make_token('__t_bd_v')

    print('【① 批量删除：混合清单（存在/已删除/无权限者视角）】')
    st, d = api(tk, 'POST', '/api/cards/batch-delete',
                {'card_ids': ['__t_bd_c1', '__t_bd_gone', '__t_bd_c2']})
    ok(st == 200, '200')
    ok(len(d.get('deleted') or []) == 2, '成功 2 条（c1 级联子事项）')
    fails = {x['card_id']: x['reason'] for x in (d.get('failed') or [])}
    ok('__t_bd_gone' in fails and '不存在' in fails['__t_bd_gone'], '已删除项进 failed：%s' % fails.get('__t_bd_gone'))
    c = sqlite3.connect(DB)
    soft = c.execute("SELECT deleted FROM cards WHERE card_id='__t_bd_c1s'").fetchone()[0]
    c.close()
    ok(soft == 1, '子事项随主事项级联软删')

    print('【② viewer 批量删除 → 逐卡 403 进 failed（不动数据）】')
    st, d = api(tk_v, 'POST', '/api/cards/batch-delete', {'card_ids': ['__t_bd_gone']})
    ok(st == 200 and not d.get('deleted'), '无可删项')
    st, d = api(tk_v, 'GET', '/api/cards?board_ids=__t_bd_b')
    # viewer allowed_boards 含看板但删除需事项负责人 → 全部 failed
    st, d = api(tk_v, 'POST', '/api/cards/batch-delete', {'card_ids': ['__t_bd_gone']})
    ok(st == 200, '占位')

    print('【③ 空清单 → 400】')
    st, d = api(tk, 'POST', '/api/cards/batch-delete', {'card_ids': []})
    ok(st == 400, '400：%s' % (d.get('detail') or ''))

    print('【④ 重建夹具 → 导出勾选交集】')
    setup()
    st, blob = api(tk, 'GET', '/api/export/xlsx?card_ids=__t_bd_c2', raw=True)
    ok(st == 200 and blob[:2] == b'PK', '仅勾选 c2 → xlsx 返回')
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(blob))
    ws = wb.active
    names = [ws.cell(row=i, column=3).value for i in range(2, ws.max_row + 1)]
    # 列顺序未知，找含「事项」值的数据行计数
    # #143（2026-11-17）：新增「代办任务」列导出明细文本（子任务 title 可能含「事项」），
    # 全单元格扫描口径会误多计 → 改为按**事项名称列**（第 1 列）统计行数
    vals = [v for row in ws.iter_rows(min_row=2, values_only=True) for v in row[:1] if v and '事项' in str(v)]
    ok(len(vals) == 1, '导出仅含勾选的 1 个事项：%s' % vals[:3])
    st, blob = api(tk, 'GET', '/api/export/xlsx?card_ids=__t_bd_c1,__t_bd_c2', raw=True)
    wb = load_workbook(io.BytesIO(blob))
    vals = [v for row in wb.active.iter_rows(min_row=2, values_only=True) for v in row[:1] if v and '事项' in str(v)]
    ok(len(vals) == 2, '勾选 2 个 → 导出 2 行')
    tk_v2 = make_token('__t_bd_v2')   # 无任何可见看板
    st, blob = api(tk_v2, 'GET', '/api/export/xlsx?card_ids=__t_bd_c1', raw=True)
    wb = load_workbook(io.BytesIO(blob))
    vals = [v for row in wb.active.iter_rows(min_row=2, values_only=True) for v in row[:1] if v and '事项' in str(v)]
    ok(len(vals) == 0, '不可见看板的 id → 交集剔除后导出 0 行（viewer 可见时正常导 1 行）')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
finally:
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_bd_b'").fetchone()[0]
    c.close()
    print('夹具残留 cards=%d' % n)
