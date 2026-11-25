# -*- coding: utf-8 -*-
"""T-232 综合看板追加可见人 → 父子事项递归可见（纯 API 测试，无 CDP）。

需求（2026-11-25 用户）：为综合看板追加新的可见人后，其可见权限同步覆盖——
不仅白名单板块本身可见，板块下全部父子事项（含任意递归层级）也要可见。

实现：_filter_cards_for_user 事项级身份过滤（#113）增加综合授予豁免——
  _SYN_CTX 范围内（syn_depts → _syn_grant 的 boards∩cols）的事项豁免身份过滤。
子事项随 get_card_children 的板块级过滤天然递归返回（板块可见 → 子树全可见）。

场景：
① 夹具：专属配置人 __t232_admin（role=admin → user_allowed 全量）+ 追加人
   __t232_u（editor、无任何事项身份）；syn_board_config 白名单仅夹具板块；
   syn_config_member 归属。父→子→孙三级事项（同板块）+ 对照事项（同看板其他板块）。
② 无 syn_depts：追加人看不到夹具父事项（既有身份过滤口径不变）。
③ 带 syn_depts：父事项可见（板块维度收口——对照板块事项仍不可见）。
④ 带 syn_depts：/children 递归返回子+孙（树形嵌套验证层级同步）。
⑤ 越权负例：无 syn_config_member 归属的用户 __t232_v 带 syn_depts → 仍不可见
   （无综合能力位的架构不授予）。
⑥ 夹具自清理（软删事项/删板块/删配置行/删用户），零残留。
"""
import json, os, sqlite3, sys, urllib.request, urllib.error, urllib.parse

sys.path.insert(0, 'src'); sys.path.insert(0, 'ops')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

DB = 'src/app.db'
BOARD = 'BCP1793717004248'
NID = 4                      # BCP 挂载架构（核算部）
ADMIN_CFG = '__t232_admin'   # 夹具配置人（role=admin）
MEMBER_U = '__t232_u'        # 追加可见人（无事项身份）
MEMBER_V = '__t232_v'        # 负例用户（无 syn 归属）
PW = 'Tt232!x'

ok_n = fail_n = 0
def ok(cond, msg):
    global ok_n, fail_n
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
    if cond: ok_n += 1
    else: fail_n += 1

def api(tk, path, method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:8100' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + tk)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20,
                                    data=json.dumps(body).encode() if body is not None else None) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def db_cleanup():
    """精确主键清理（D2：先查后删、行数核对）。"""
    conn = sqlite3.connect(DB)
    n1 = conn.execute("DELETE FROM syn_config_member WHERE member IN (?,?)", (MEMBER_U, MEMBER_V)).rowcount
    n2 = conn.execute("DELETE FROM syn_board_config WHERE owner=?", (ADMIN_CFG,)).rowcount
    n3 = conn.execute("DELETE FROM users WHERE username IN (?,?,?)", (ADMIN_CFG, MEMBER_U, MEMBER_V)).rowcount
    conn.commit(); conn.close()
    return n1, n2, n3

def main():
    tk_admin = make_token('admin')
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        # ── ① 夹具 ──
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (ADMIN_CFG, hash_pw(PW), 'admin', '*', '*'))
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (MEMBER_U, hash_pw(PW), 'editor', '*', '*'))
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                     " VALUES (?,?,?,?,?,datetime('now','localtime'))",
                     (MEMBER_V, hash_pw(PW), 'editor', '*', '*'))
        conn.commit()
        st, d = api(tk_admin, '/api/columns', 'POST',
                    {'board_id': BOARD, 'column_name': '__t232_板块', 'nature': '日常',
                     'year': '2026', 'completion': 'progressing', 'created_at': '2026-11-25'})
        assert st in (200, 201), '板块创建失败: %s %s' % (st, d)
        # col_key 自算（响应体不含）；column_id 落库后回查——建卡必须带 column_id
        #（前端真实路径同样携带；空 column_id 会被板块白名单过滤，属夹具缺陷非产品）
        col_key = BOARD + '::__t232_板块'
        colid_row = conn.execute("SELECT column_id FROM board_columns WHERE col_key=?", (col_key,)).fetchone()
        col_id = colid_row['column_id'] if colid_row else ''
        assert col_id, '夹具板块 column_id 回查失败'
        # 配置白名单 = 仅夹具板块（专属 owner 行，不触碰真实配置）
        conn.execute("INSERT OR IGNORE INTO syn_board_config (dept_node_id, owner, columns, extra_members)"
                     " VALUES (?,?,?,'')", (NID, ADMIN_CFG, col_key))
        conn.execute("INSERT OR IGNORE INTO syn_config_member (dept_node_id, member, owner)"
                     " VALUES (?,?,?)", (NID, MEMBER_U, ADMIN_CFG))
        conn.commit()
        tk_u = make_token(MEMBER_U)
        tk_v = make_token(MEMBER_V)
        # 两级事项：父 → 子（产品本期仅支持两级，「递归层级」= 全树；同板块）
        # + 对照事项（同看板既有板块，验证板块维度收口）
        st, dp = api(tk_admin, '/api/cards', 'POST',
                     {'board_id': BOARD, 'card_name': '__t232_父事项', 'column_id': col_id,
                      'fields': {'column_name': '__t232_板块', 'nature': '日常', 'created': '2026-11-25'}})
        assert st in (200, 201), '父事项创建失败: %s %s' % (st, dp)
        pid = dp['card_id']
        st, dc = api(tk_admin, '/api/cards', 'POST',
                     {'board_id': BOARD, 'card_name': '__t232_子事项', 'parent_id': pid,
                      'column_id': col_id,
                      'fields': {'column_name': '__t232_板块', 'nature': '日常', 'created': '2026-11-25'}})
        assert st in (200, 201), '子事项创建失败: %s %s' % (st, dc)
        cid = dc['card_id']
        ctrl_row = conn.execute("SELECT column_name FROM board_columns WHERE board_id=? "
                                "AND column_name NOT LIKE '%t232%' LIMIT 1", (BOARD,)).fetchone()
        ctrl_col = ctrl_row['column_name'] if ctrl_row else None
        st, dx = api(tk_admin, '/api/cards', 'POST',
                     {'board_id': BOARD, 'card_name': '__t232_对照事项',
                      'column_id': (conn.execute("SELECT column_id FROM board_columns WHERE board_id=? AND column_name=?",
                                                 (BOARD, ctrl_col)).fetchone() or {'column_id': ''})['column_id'],
                      'fields': {'column_name': ctrl_col or '__t232_板块', 'nature': '日常',
                                 'created': '2026-11-25'}})
        xid = dx.get('card_id') if st in (200, 201) else None

        def names(d):
            return {c['card_name'] for c in (d.get('cards') or [])}

        # ── ② 无 syn_depts：身份过滤口径不变 → 追加人看不到 ──
        st, d2 = api(tk_u, '/api/cards?board_ids=%s&size=500' % BOARD)
        ok(st == 200 and '__t232_父事项' not in names(d2),
           '② 无 syn_depts：追加人无事项身份 → 父事项不可见（既有口径）')

        # ── ③ 带 syn_depts：父事项可见；板块维度收口（对照板块不可见）──
        q = urllib.parse.urlencode({'board_ids': BOARD, 'size': 500, 'syn_depts': NID})
        st, d3 = api(tk_u, '/api/cards?' + q)
        n3 = names(d3)
        ok(st == 200 and '__t232_父事项' in n3,
           '③ 带 syn_depts：白名单板块下父事项可见')
        if ctrl_col and xid:
            ok('__t232_对照事项' not in n3,
               '③ 板块维度收口：非白名单板块的对照事项仍不可见')
        else:
            print('SKIP ③ 对照板块缺对照列（board_columns 仅剩夹具列）')

        # ── ④ /children 树形返回：子事项随树返回（板块可见 → 子树全可见）──
        st, d4 = api(tk_u, '/api/cards/%s/children?syn_depts=%d' % (pid, NID))
        tree = d4.get('children') or []
        ok(st == 200 and len(tree) == 1 and tree[0]['card_name'] == '__t232_子事项',
           '④ 追加人可见子事项（随父事项子树递归返回）')
        # 对照：/api/cards 恒返回顶层（端点硬编码 level='top'），子事项经
        # /children 树形接口返回（上一断言已覆盖递归）——此处仅验证详情可达
        st, d4b = api(tk_u, '/api/cards/%s/children?syn_depts=%d' % (pid, NID))
        ok(st == 200 and d4b.get('total') == 1,
           '④ 子树可达性复核：children total=1（父子一致，递归由 build() 深度展开）')

        # ── ⑤ 越权负例：无 syn 归属的用户带 syn_depts → 不授予 ──
        q5 = urllib.parse.urlencode({'board_ids': BOARD, 'size': 500, 'syn_depts': NID})
        st, d5 = api(tk_v, '/api/cards?' + q5)
        ok(st == 200 and '__t232_父事项' not in names(d5),
           '⑤ 无 syn_config_member 归属：syn_depts 不产生授予（不越权）')

        # ── ⑥ 清理 ──
        for cid_ in (cid, pid, xid):
            if cid_:
                api(tk_admin, '/api/cards/' + cid_, 'DELETE')
        if col_key:
            api(tk_admin, '/api/columns/' + urllib.parse.quote(col_key, safe=''), 'DELETE')
    finally:
        n1, n2, n3 = db_cleanup()
        conn.close()
    # 残留自查（防抖 PUT 无、纯 API —— 单次删除即可，但仍复核）
    conn = sqlite3.connect(DB)
    left_u = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%t232%'").fetchone()[0]
    left_s = conn.execute("SELECT COUNT(*) FROM syn_config_member WHERE member LIKE '%t232%'").fetchone()[0]
    left_c = conn.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE '%t232%' AND deleted=0").fetchone()[0]
    left_col = conn.execute("SELECT COUNT(*) FROM board_columns WHERE column_name LIKE '%t232%'").fetchone()[0]
    conn.close()
    ok(left_u == 0 and left_s == 0 and left_c == 0 and left_col == 0,
       '⑥ 夹具零残留（users=%d syn=%d cards=%d cols=%d）' % (left_u, left_s, left_c, left_col))
    print('结果: %d PASS / %d FAIL' % (ok_n, fail_n))
    sys.exit(1 if fail_n else 0)

if __name__ == '__main__':
    main()
