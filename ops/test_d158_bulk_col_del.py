# -*- coding: utf-8 -*-
"""#158 板块复选框+批量删除：API 层（权限/级联/隔离语义）"""
import json, os, sqlite3, sys, urllib.request, urllib.error

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = r'E:/WB缓存/2026-10-26-15-55-08/src/app.db'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

from app.app import make_token, hash_pw

def api(tk, method, path, body=None):
    # 中文路径段编码一次（safe 保留结构字符；勿二次编码，否则 % 会被转 %25）
    import urllib.parse
    path = urllib.parse.quote(path, safe='/:?&=,@')
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

def setup():
    """夹具：看板 2 个板块（各 1 主事项+1 子事项）+ 非负责人账号（viewer）"""
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("DELETE FROM cards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM users WHERE username='__t_ck_u'")
    c.execute("INSERT INTO boards (board_id,board_name,sort,created_at) VALUES ('__t_ck_b','__t_勾选测试看板',0,datetime('now'))")
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_ck_b::__t_板块甲','COLck1','__t_ck_b','__t_板块甲',date('now'),'admin','日常','2026',0,'','','open','')")
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion,description)"
              " VALUES ('__t_ck_b::__t_板块乙','COLck2','__t_ck_b','__t_板块乙',date('now'),'admin','日常','2026',0,'','','open','')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_c1','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_甲事项','open','',datetime('now'),0,0,'')")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_c1s','__t_ck_b','__t_勾选测试看板','__t_板块甲','__t_甲子事项','open','',datetime('now'),0,0,'__t_ck_c1')")
    c.execute("INSERT INTO card_subtasks (card_id,title,done) VALUES ('__t_ck_c1','__t_甲子事项',0)")
    c.execute("INSERT INTO cards (card_id,board_id,board_name,column_name,card_name,status,owner,week_no,created,deleted,parent_id)"
              " VALUES ('__t_ck_c2','__t_ck_b','__t_勾选测试看板','__t_板块乙','__t_乙事项','open','',datetime('now'),0,0,'')")
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards) VALUES ('__t_ck_u',?,'viewer','__t_ck_b')", (hash_pw('Xx12345678'),))
    c.commit(); c.close()

def cleanup():
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM cards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM card_subtasks WHERE card_id LIKE '__t_ck_%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM boards WHERE board_id='__t_ck_b'")
    c.execute("DELETE FROM users WHERE username='__t_ck_u'")
    c.commit(); c.close()

setup()
try:
    tk_admin = make_token('admin')       # 超管 = 看板负责人及以上，直通
    tk_view = make_token('__t_ck_u')     # viewer 无权限

    print('【① 删除前可见性确认】')
    st, d = api(tk_admin, 'GET', '/api/cards?board_ids=__t_ck_b')
    ok(st == 200 and d.get('total') == 2, '主事项 2 条（子事项不进主列表）：%s' % d.get('total'))

    print('【② 非负责人删除板块 → 403】')
    st, d = api(tk_view, 'DELETE', '/api/columns/' + '__t_ck_b::__t_板块甲')
    ok(st == 403, '403：%s' % (d.get('detail') or ''))

    print('【③ 超管删除板块甲 → 200 + 级联软删】')
    st, d = api(tk_admin, 'DELETE', '/api/columns/' + '__t_ck_b::__t_板块甲')
    ok(st == 200 and d.get('deleted_cards') == 2, '200，连带事项 %s 条' % (d.get('deleted_cards') if st == 200 else d.get('detail')))
    st, d = api(tk_admin, 'GET', '/api/cards?board_ids=__t_ck_b')
    ok(d.get('total') == 1, '删除后仅剩乙事项 1 条：%s' % d.get('total'))
    c = sqlite3.connect(DB)
    soft = c.execute("SELECT deleted FROM cards WHERE card_id='__t_ck_c1'").fetchone()[0]
    sub_soft = c.execute("SELECT deleted FROM cards WHERE card_id='__t_ck_c1s'").fetchone()[0]
    sub_gone = c.execute("SELECT COUNT(*) FROM card_subtasks WHERE card_id='__t_ck_c1'").fetchone()[0]
    col_gone = c.execute("SELECT COUNT(*) FROM board_columns WHERE col_key='__t_ck_b::__t_板块甲'").fetchone()[0]
    c.close()
    ok(soft == 1 and sub_soft == 1, '主/子事项均软删（deleted=1）')
    ok(sub_gone == 0, 'card_subtasks 清单行已清')
    ok(col_gone == 0, '板块元信息行已删')

    print('【④ 再删同一板块 → 404（幂等边界）】')
    st, d = api(tk_admin, 'DELETE', '/api/columns/' + '__t_ck_b::__t_板块甲')
    ok(st == 404, '404：%s' % (d.get('detail') or ''))

    print('【⑤ 删除板块乙（验证删除后 board_columns 隔离）】')
    st, d = api(tk_admin, 'DELETE', '/api/columns/' + '__t_ck_b::__t_板块乙')
    ok(st == 200, '200')
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id='__t_ck_b'").fetchone()[0]
    c.close()
    ok(n == 0, '看板下板块全部清空')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))
finally:
    cleanup()
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM cards WHERE board_id='__t_ck_b'").fetchone()[0]
    c.close()
    print('夹具残留 cards=%d' % n)
