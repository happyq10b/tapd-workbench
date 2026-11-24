# -*- coding: utf-8 -*-
"""T-209 板块【类别】维度 API 实测（2026-11-24）

规则（用户需求）：
  ① board_columns.category：必选，默认「年度重点工作」，五大类别枚举
     （年度重点工作/业财融合工作/财务数智化工作/其他重点工作/文化及团队建设）
  ② 存量板块迁移回填「年度重点工作」（SQLite ADD COLUMN 常量 DEFAULT 全量生效）
  ③ 新建/编辑板块写入；编辑留空 = 沿用原值；非法枚举 400
  ④ 复制板块（单板块 + #205ab 深复制）category 随原板块
  ⑤ cols 载荷（visible_columns，SELECT *）下发 category 供筛选

夹具纪律 §3.3：前缀 __t209_ + try/finally 自清理 + 零残留自查。
运行约定：从项目根运行（DB 相对路径无关，本测试用绝对路径；服务须 8100 在线）。
"""
import json, os, sys, urllib.request, urllib.error, sqlite3, atexit

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, COLUMN_CATEGORIES, COLUMN_CATEGORY_DEFAULT

BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'
RES = []
P = '__t209_'
CAT2 = '业财融合工作'


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
        return {'__http__': e.code, 'detail': (e.read().decode() or '')[:160]}


# ---------------- 夹具搭建 ----------------
_c = sqlite3.connect(DB, timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
CLEAN_SQL = [
    "DELETE FROM board_columns WHERE board_id LIKE ? OR column_name LIKE ?",
    "DELETE FROM cards WHERE board_id LIKE ?",
    "DELETE FROM boards WHERE board_id LIKE ? OR board_name LIKE ?",
    "DELETE FROM board_config WHERE board_id LIKE ?",
    "DELETE FROM users WHERE username LIKE ?",
]
for q in CLEAN_SQL:
    _c.execute(q, (P + '%',) * q.count('?'))
_c.execute("INSERT INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
           (P + 'adm', 'x', 'admin'))
# 两个夹具看板（归属核算部，超管可建板）
for bn in (P + 'B1', P + 'B2'):
    _c.execute("INSERT INTO boards(board_id,board_name,owner,participants,creator,archived,created_at,sort) "
               "VALUES(?,?,'admin','', 'admin',0,datetime('now'),0)", (bn, bn))
    _c.execute("INSERT INTO board_config(board_id,dept,dept_node_id,attr,status) "
               "VALUES((SELECT board_id FROM boards WHERE board_id=?),'核算部',"
               "(SELECT id FROM org_nodes WHERE node_type='dept' ORDER BY sort LIMIT 1),'日常','启用')", (bn,))
_c.commit(); _c.close()


def _cleanup():
    _c = sqlite3.connect(DB, timeout=15)
    _c.execute('PRAGMA busy_timeout=15000')
    for q in CLEAN_SQL:
        _c.execute(q, (P + '%',) * q.count('?'))
    _c.commit()
    # 零残留自查（SELECT COUNT 形式）
    n = 0
    for q in ("SELECT COUNT(*) FROM board_columns WHERE board_id LIKE ?",
              "SELECT COUNT(*) FROM cards WHERE board_id LIKE ?",
              "SELECT COUNT(*) FROM boards WHERE board_id LIKE ?",
              "SELECT COUNT(*) FROM board_config WHERE board_id LIKE ?",
              "SELECT COUNT(*) FROM users WHERE username LIKE ?"):
        n += _c.execute(q, (P + '%',)).fetchone()[0]
    _c.close()
    print('零残留自查: %s（%d 条）' % ('PASS' if n == 0 else '✗ FAIL', n))


atexit.register(_cleanup)

try:
    tok = make_token('admin')

    print('【A】枚举常量与存量回填')
    ok(len(COLUMN_CATEGORIES) == 5 and COLUMN_CATEGORY_DEFAULT == '年度重点工作',
       'A1 COLUMN_CATEGORIES 五项 + 默认值')
    _c = sqlite3.connect(DB)
    _cnt = _c.execute("SELECT COUNT(*) FROM board_columns WHERE category IS NULL OR category=''").fetchone()[0]
    _c.close()
    ok(_cnt == 0, 'A2 存量板块 category 全量非空（迁移回填生效）')

    print('【B】新建板块 category')
    import time as _t
    created = _t.strftime('%Y-%m-%d')
    r = req(tok, '/api/columns', 'POST', {'board_id': P + 'B1', 'column_name': P + 'C1',
                                          'created_at': created, 'year': '2026', 'nature': '日常',
                                          'category': CAT2})
    ok(r.get('ok') and r.get('category') == CAT2, 'B1 新建指定类别 → 落库并回显', r)
    r = req(tok, '/api/columns', 'POST', {'board_id': P + 'B1', 'column_name': P + 'C2',
                                          'created_at': created, 'year': '2026', 'nature': '日常'})
    ok(r.get('ok') and r.get('category') == '年度重点工作', 'B2 新建未传类别 → 默认「年度重点工作」', r)
    r = req(tok, '/api/columns', 'POST', {'board_id': P + 'B1', 'column_name': P + 'C3',
                                          'created_at': created, 'year': '2026', 'nature': '日常',
                                          'category': '不存在的类别'})
    ok(r.get('__http__') == 400, 'B3 非法类别 → 400')

    print('【C】编辑板块 category')
    ck1 = (P + 'B1') + '::' + (P + 'C1')
    ck2 = (P + 'B1') + '::' + (P + 'C2')
    r = req(tok, '/api/columns', 'PUT', {'col_key': ck1, 'board_id': P + 'B1',
                                         'column_name': P + 'C1', 'created_at': created,
                                         'nature': '日常', 'category': '文化及团队建设'})
    ok(r.get('ok') and r.get('category') == '文化及团队建设', 'C1 编辑改类别 → 更新', r)
    r = req(tok, '/api/columns', 'PUT', {'col_key': ck1, 'board_id': P + 'B1',
                                         'column_name': P + 'C1', 'created_at': created,
                                         'nature': '日常'})
    ok(r.get('ok') and r.get('category') == '文化及团队建设', 'C2 编辑留空类别 → 沿用原值', r)
    r = req(tok, '/api/columns', 'PUT', {'col_key': ck2, 'board_id': P + 'B1',
                                         'column_name': P + 'C2', 'created_at': created,
                                         'nature': '日常', 'category': '财务数智化工作'})
    ok(r.get('ok') and r.get('category') == '财务数智化工作', 'C3 编辑默认类别板块 → 可改', r)

    print('【D】cols 载荷下发 category')
    cards_resp = req(tok, '/api/cards')   # 全量（board_id 参数经 cards 过滤，夹具无事项会被裁）
    _hit = [x for x in cards_resp.get('columns', []) if x.get('board_id') == P + 'B1']
    ok(len(_hit) >= 2 and all(x.get('category') in (CAT2, '文化及团队建设', '财务数智化工作')
                              for x in _hit),
       'D1 cols 载荷携带板块类别（夹具行命中）',
       [(x.get('column_name'), x.get('category')) for x in _hit])

    print('【E】复制板块 category 随原板块')
    r = req(tok, '/api/columns/copy', 'POST', {'col_key': ck1, 'board_id': P + 'B2'})
    ok(r.get('ok') and r.get('category') == '文化及团队建设', 'E1 单板块复制 → 类别沿用', r)
    r = req(tok, '/api/columns/copy', 'POST', {'col_key': ck1, 'board_id': P + 'B2', 'deep': True})
    ok(r.get('ok') and r.get('category') == '文化及团队建设', 'E2 深复制（连带事项）→ 类别沿用', r)
    _c = sqlite3.connect(DB)
    _row = _c.execute("SELECT category FROM board_columns WHERE board_id=? AND column_name LIKE ?",
                      (P + 'B2', P + 'C1%')).fetchall()
    _c.close()
    ok(len(_row) >= 2 and all(x[0] == '文化及团队建设' for x in _row),
       'E3 副本板块行 category 落库一致')

    print('【F】校验与提交')
    ok(len(RES) and all(x for x, _ in RES), 'F1 全部断言通过')

finally:
    pass

_np = sum(1 for x, _ in RES if x)
_nf = len(RES) - _np
print('结果: PASS=%d FAIL=%d' % (_np, _nf))
sys.exit(0 if _nf == 0 else 1)
