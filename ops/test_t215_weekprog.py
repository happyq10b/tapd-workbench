# -*- coding: utf-8 -*-
"""T-215 每周进展（2026-11-24）：API 全链路夹具测试。
运行约定：项目根目录（DB 相对路径 src/app.db）；夹具前缀 __t215_，try/finally 自清理。
"""
import sys, os, json, sqlite3, urllib.request, urllib.error
from urllib.parse import quote
sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

DB = 'src/app.db'
P = '__t215_'
BASE = 'http://127.0.0.1:8100'

CLEAN_SQL = [
    "DELETE FROM card_week_progress WHERE card_id LIKE ?",
    "DELETE FROM comments WHERE card_id LIKE ?",
    "DELETE FROM actions WHERE card_id LIKE ?",
    "DELETE FROM cards WHERE card_id LIKE ?",
    "DELETE FROM board_columns WHERE board_id LIKE ? OR column_name LIKE ?",
    "DELETE FROM board_config WHERE board_id LIKE ?",
    "DELETE FROM boards WHERE board_id LIKE ?",
    "DELETE FROM users WHERE username LIKE ?",
]

def cleanup():
    import time
    for _ in range(5):
        try:
            c = sqlite3.connect(DB, timeout=15)
            break
        except sqlite3.OperationalError:
            time.sleep(1)
    c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        c.execute(q, (P + '%',) * q.count('?'))
    c.commit()
    n = 0
    for tbl, cols in [('card_week_progress', ['card_id']), ('comments', ['card_id']),
                      ('actions', ['card_id']), ('cards', ['card_id']),
                      ('board_columns', ['board_id', 'column_name']),
                      ('board_config', ['board_id']), ('boards', ['board_id']),
                      ('users', ['username'])]:
        for col in cols:
            n += c.execute('SELECT COUNT(*) FROM %s WHERE %s LIKE ?' % (tbl, col),
                           (P + '%',)).fetchone()[0]
    c.close()
    print('零残留自查: %s（%d 条）' % ('PASS' if n == 0 else 'FAIL', n))

PASS = 0
def ok(cond, label, detail=None):
    global PASS
    print(('  ✓ ' if cond else '  ✗ ') + label + (('' if cond else '  ← ' + json.dumps(detail, ensure_ascii=False)[:180]) if not cond and detail is not None else ''))
    if cond: PASS += 1

def req(tok, path, method='GET', body=None):
    # 路径段中的非 ASCII（卡片 id 可能含中文）按 RFC3986 编码；query 串原样保留
    if '?' in path:
        p, q = path.split('?', 1)
        path = '/'.join(quote(seg, safe='') for seg in p.split('/')) + '?' + q
    else:
        path = '/'.join(quote(seg, safe='') for seg in path.split('/'))
    r = urllib.request.Request(BASE + path, method=method,
                               headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
                               data=json.dumps(body).encode() if body is not None else None)
    try:
        return json.loads(urllib.request.urlopen(r, timeout=15).read())
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'msg': e.read().decode()[:150]}

tok_adm = make_token('admin')

try:
    # ---- 夹具：看板 B1 + 板块 col1 + 事项 c1（多周）+ c2（无周）----
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute("INSERT INTO boards(board_id,board_name,owner,participants,creator,archived,created_at,sort) "
              "VALUES(?,'x','','','admin',0,datetime('now'),0)", (P + 'B1',))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,category,year,completion) "
              "VALUES(?,?,?,?,datetime('now'),'admin','年度重点工作','2026','open')",
              (P + 'B1::col1', 'COL_t215', P + 'B1', 'col1'))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,owner,creator,"
              "status,week_no,deleted,created) VALUES(?,?,?,?,?,?,?,?,?,?,0,datetime('now'))",
              (P + 'c1', P + 'B1', 'x', 'COL_t215', 'col1', '事项一', 'admin', 'admin', 'open',
               '2026年第47周;2026年第48周;2026年第49周'))
    c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,owner,creator,"
              "status,week_no,deleted,created) VALUES(?,?,?,?,?,?,?,?,?,?,0,datetime('now'))",
              (P + 'c2', P + 'B1', 'x', 'COL_t215', 'col1', '事项二', 'admin', 'admin', 'open', ''))
    c.commit(); c.close()

    print('【A】读写与幂等覆盖')
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok(r.get('progress') == {}, 'A1 初始为空', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST',
            {'items': {'2026年第47周': '方案评审', '2026年第48周': '上线'}})
    ok(r.get('ok') is True, 'A2 保存两周', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok(r['progress'].get('2026年第47周', {}).get('content') == '方案评审', 'A3 回读 47 周', r)
    ok(r['progress'].get('2026年第47周', {}).get('updated_by') == 'admin', 'A4 updated_by 记录', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST',
            {'items': {'2026年第47周': '方案评审 v2', '2026年第48周': '上线'}})
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok(r['progress']['2026年第47周']['content'] == '方案评审 v2', 'A5 同周覆盖（幂等）', r)

    print('【B】周数变更语义（内容按周保留）')
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST',
            {'items': {'2026年第47周': '方案评审 v2', '2026年第48周': '上线', '2026年第50周': '新增周内容'}})
    ok(r.get('ok') is True, 'B1 保存含未勾选周（49→50 变更场景）', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok('2026年第50周' in r['progress'], 'B2 新周内容落库', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST', {'items': {'2026年第48周': ''}})
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok('2026年第48周' not in r['progress'], 'B3 显式清空 = 删除该周记录', r)

    print('【C】校验与权限')
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST', {'items': {'坏周数': 'x'}})
    ok(r.get('__http__') == 400, 'C1 非法周数格式 → 400', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P, 'POST', {'items': {'2026年第47周': 'x' * 3000}})
    ok(r.get('ok') is True, 'C2 超长内容截断不报错', r)
    r = req(tok_adm, '/api/cards/%sc1/week-progress' % P)
    ok(len(r['progress'].get('2026年第47周', {}).get('content', '')) <= 2000, 'C3 服务端截断 2000', r)
    r = req(tok_adm, '/api/cards/%sc2/week-progress' % P, 'POST', {'items': {'2026年第47周': 'x'}})
    ok(r.get('ok') is True, 'C4 无周数事项也可存（前端不渲染输入区）', r)
    r = req(tok_adm, '/api/cards/%s不存在/week-progress' % P)
    ok(r.get('__http__') in (403, 404), 'C5 不存在卡片 → 403/404', r)

    print('【D】端到端可见性（cards 载荷不受影响）')
    r = req(tok_adm, '/api/cards?card_id=%sc1' % P)
    ok(r.get('cards') and r['cards'][0]['card_id'] == P + 'c1', 'D1 card_id 精确取正常', r)
finally:
    cleanup()

print('结果: PASS=%d FAIL=%d' % (PASS, 14 - PASS))
assert PASS == 14, '有断言未通过'
