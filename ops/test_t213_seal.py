# -*- coding: utf-8 -*-
"""T-213 板块结存 API 实测（2026-11-24）

规则（用户需求）：
  ① 结存板块：不可见（visible_columns/cards/col_count 全链路排除）+ 不可编辑/删除（403）
  ② 结存保存：看板封存同口径权限（归属部门架构负责人/管理员）；跨看板板块 400
  ③ 取消勾选 = 解封

夹具纪律 §3.3：前缀 __t213_ + atexit 自清理 + 零残留自查。从项目根运行；8100 在线。
"""
import json, os, sys, urllib.request, urllib.error, sqlite3, atexit

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
RES = []
P = '__t213_'


def ok(cond, name, dbg=None):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name + (('  ← ' + json.dumps(dbg, ensure_ascii=False)[:200]) if (dbg is not None and not cond) else ''))


def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=15).read() or '{}')
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'detail': (e.read().decode() or '')[:200]}


_c = sqlite3.connect(DB, timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
CLEAN_SQL = [
    "DELETE FROM board_columns WHERE board_id LIKE ?",
    "DELETE FROM board_config WHERE board_id LIKE ?",
    "DELETE FROM boards WHERE board_id LIKE ?",
    "DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)",
    "DELETE FROM org_nodes WHERE name LIKE ?",
    "DELETE FROM team_members WHERE name LIKE ? OR account LIKE ?",
    "DELETE FROM users WHERE username LIKE ?",
]
for q in CLEAN_SQL:
    _c.execute(q, (P + '%',) * q.count('?'))
_c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?, 'editor',1)", (P + 'dh', 'x'))
_c.execute("INSERT INTO team_members(name,account,created_at,status) VALUES(?,?,datetime('now'),'active')", (P + 'dh', P + 'dh'))
_mid = _c.execute("SELECT id FROM team_members WHERE account=?", (P + 'dh',)).fetchone()[0]
_did = _c.execute("INSERT INTO org_nodes(name,node_type,parent_id,sort) VALUES(?, 'dept', 0, 989)", (P + 'D',)).lastrowid
_c.execute("INSERT INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) VALUES(?,?, 'dept_head',1,datetime('now'))", (_did, _mid))
_c.execute("INSERT INTO boards(board_id,board_name,owner,participants,creator,archived,created_at,sort) VALUES(?, '', '', '', 'admin',0,datetime('now'),0)", (P + 'B1',))
_c.execute("INSERT INTO board_config(board_id,dept,dept_node_id,attr,status) VALUES(?, '测试部门', ?, '日常','启用')", (P + 'B1', _did))
for i, cat in enumerate(['年度重点工作', '文化及团队建设']):
    ck = (P + 'B1::') + P + ('col%d' % i)
    _c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,nature,category,year,completion,sealed) "
               "VALUES(?,?,?,?,?,?, '日常',?, '2026','open',0)", (ck, 'COL_t213_%d' % i, P + 'B1', P + ('col%d' % i), '2026-01-01', 'admin', cat))
_c.commit(); _c.close()
CK0, CK1 = (P + 'B1::') + P + 'col0', (P + 'B1::') + P + 'col1'


def _cleanup():
    _c = sqlite3.connect(DB, timeout=15)
    _c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        _c.execute(q, (P + '%',) * q.count('?'))
    _c.commit()
    n = _c.execute("SELECT COUNT(*) FROM boards WHERE board_name LIKE ?", (P + '%',)).fetchone()[0]
    n += _c.execute("SELECT COUNT(*) FROM board_columns WHERE col_key LIKE ?", (P + '%',)).fetchone()[0]
    _c.close()
    print('零残留自查: %s（%d 条）' % ('PASS' if n == 0 else '✗ FAIL', n))


atexit.register(_cleanup)

try:
    tok_adm = make_token('admin')
    tok_dh = make_token(P + 'dh')

    print('【A】结存保存与回读')
    r = req(tok_adm, '/api/columns-seal?board_id=' + (P + 'B1'))
    ok(r.get('can_seal') is True and len(r.get('columns', [])) == 2, 'A1 GET 清单（2 板块，未结存）', r)
    r = req(tok_adm, '/api/columns-seal/' + (P + 'B1'), 'POST', {'sealed': [CK1]})
    ok(r.get('ok') is True and r.get('sealed_total') == 1, 'A2 结存 col1（文化类）')
    r = req(tok_adm, '/api/columns-seal?board_id=' + (P + 'B1'))
    ok([c['sealed'] for c in r['columns']] == [False, True], 'A3 回读结存态 [False,True]')
    r = req(tok_dh, '/api/columns-seal/' + (P + 'B1'), 'POST', {'sealed': []})
    ok(r.get('ok') is True, 'A4 部门长（架构负责人）可解封')
    r = req(tok_adm, '/api/columns-seal/' + (P + 'B1'), 'POST', {'sealed': [CK0, CK1]})
    ok(r.get('ok') is True, 'A5 重新结存两个')

    print('【B】不可见（全链路排除）')
    me = req(tok_adm, '/api/me')
    b1 = [b for b in me.get('boards', []) if b['board_id'] == P + 'B1']
    ok(b1 and b1[0].get('col_count') == 0, 'B1 col_count 不计结存板块（0）', b1)
    cards = req(tok_adm, '/api/cards')
    cols = [c for c in cards.get('columns', []) if c.get('board_id') == P + 'B1']
    ok(len(cols) == 0, 'B2 cols 载荷无结存板块')
    allc = [c for c in cards.get('all_columns', []) if c.get('board_id') == P + 'B1']
    ok(len(allc) == 0, 'B3 徽标全量清单同样排除')
    ok(all(':' + P + 'col' not in c.get('column_name', '') for c in cards.get('cards', [])),
       'B4 事项清单无结存板块事项')

    print('【C】冻结（编辑/删除 403）')
    r = req(tok_adm, '/api/columns', 'PUT', {'col_key': CK1, 'board_id': P + 'B1',
                                             'column_name': P + 'col1', 'created_at': '2026-01-01',
                                             'nature': '日常'})
    ok(r.get('__http__') == 403, 'C1 编辑结存板块 → 403', r)
    import urllib.parse
    r = req(tok_adm, '/api/columns/' + urllib.parse.quote(CK1, safe=''), 'DELETE')
    ok(r.get('__http__') == 403, 'C2 删除结存板块 → 403', r)
    r = req(tok_adm, '/api/cards', 'POST', {'board_id': P + 'B1', 'column_id': 'COL_t213_1',
                                            'card_name': P + 'card', 'fields': {}})
    ok(r.get('__http__') == 403, 'C3 结存板块新增事项 → 403', r)

    print('【D】解封恢复')
    r = req(tok_adm, '/api/columns-seal/' + (P + 'B1'), 'POST', {'sealed': []})
    ok(r.get('ok') is True, 'D1 全不选 = 解封')
    r = req(tok_adm, '/api/columns', 'PUT', {'col_key': CK1, 'board_id': P + 'B1',
                                             'column_name': P + 'col1', 'created_at': '2026-01-01',
                                             'nature': '日常'})
    ok(r.get('ok') is True, 'D2 解封后可编辑')
    r = req(tok_adm, '/api/columns-seal/' + (P + 'B1'), 'POST', {'sealed': ['__t213_B1::不存在']})
    ok(r.get('__http__') == 400, 'D3 跨看板板块 → 400')
    r = req(tok_dh, '/api/columns-seal?board_id=' + (P + 'B1'))
    ok(r.get('can_seal') is True, 'D4 部门长读取 can_seal=True')

    print('【E】校验与提交')
    ok(all(x for x, _ in RES), 'E1 全部断言通过')

finally:
    pass

_np = sum(1 for x, _ in RES if x)
_nf = len(RES) - _np
print('结果: PASS=%d FAIL=%d' % (_np, _nf))
sys.exit(0 if _nf == 0 else 1)
