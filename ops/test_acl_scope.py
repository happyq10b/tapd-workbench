#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""专项测试：权限来源收敛后的可见性口径 + 空板块/空看板清理

⚠️ **本文件在 2026-11-02 被重写**（用户拍板：负责人 = 管理权，不收窄可见性）。

旧版测的是「配了 owner/参与人 → 仅他们可见该看板」（ACL 收窄语义），
该语义**已整体下线**：
  · 负责人 = 看板 / 板块的**管理权**（可改基本信息），不是可见性开关
  · **谁能看见看板** → 统一由【架构管理】的看板绑定决定
  · 参与人（participants）机制**下线**
  → 负责人 / 管理权的测试已迁至 `ops/test_owner_scope.py`（24 断言）

本文件现在负责**剩余仍然有效**的部分：
  1. 可见性口径：架构绑定是唯一来源（配了负责人也不额外收窄）
  2. 未在架构绑定内的账号 → 看不到任何看板（fail-closed）
  3. 数据清理：无事项的板块删除；空看板一并删除（+ 幂等）

⚠️ 夹具纪律（§3.3）：
  · 夹具建在 `__acl_` 专属前缀命名空间
  · try/finally 保证无论断言成败都清理干净（删全相关表）
  · 断言里的数字全部来自**夹具自己造的数据**，绝不引用真实库的全量基线
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

BASE = 'http://127.0.0.1:8100'
PREFIX = '__acl_'
BID = PREFIX + 'board'
DEPT_NODE = 4          # 核算部

PASS = 0
FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS ' + msg)
    else:
        FAIL += 1
        print('  FAIL ' + msg)


def http(path, token=None, method='GET', body=None):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'__err': e.code}
    except Exception as e:
        return {'__err': str(e)}


def cleanup():
    import sqlite3
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'),
                   ('board_columns', 'board_id'), ('board_columns', 'column_id'),
                   ('boards', 'board_id'), ('board_config', 'board_id'),
                   ('users', 'username'), ('team_members', 'account'),
                   ('team_members', 'name')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("""DELETE FROM org_appointments WHERE member_id IN
                 (SELECT id FROM team_members WHERE account LIKE ?)""", (PREFIX + '%',))
    c.commit()
    c.close()


def build_fixture():
    """造夹具：1 个看板（归属核算部）+ 3 个板块 + 3 个账号。

    账号：
      __acl_in    —— 任命在核算部（架构授权范围内）
      __acl_out   —— 未任命（无架构授权）
      __acl_owner —— 任命在核算部，且被设为看板负责人（验证负责人不收窄可见性）
    """
    import sqlite3
    from app.app import hash_pw
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-02 22:00:00'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,'',0,?)",
              (BID, '【可见性】测试看板', 'ws_acl', PREFIX + 'owner', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (BID, '核算部', DEPT_NODE, '日常', '启用', now))
    for cid, cname in ((PREFIX + 'colA', '板块甲'), (PREFIX + 'colB', '板块乙'),
                       (PREFIX + 'colC', '板块丙')):
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
                  "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
                  (BID + '::' + cname, cid, BID, cname, now, 'seed', '日常'))
        for k in range(2):
            c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,
                          workspace_id,card_name,status,status_name,creator,created,parent_id,version,deleted)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                      ('%sc_%s_%d' % (PREFIX, cid[-4:], k), BID, '【可见性】测试看板', cid, cname,
                       'ws_acl', '【可见性】%s事项%d' % (cname, k), 'done', '已完成', 'seed', now))
    for acct, appointed in ((PREFIX + 'in', True), (PREFIX + 'out', False),
                             (PREFIX + 'owner', True)):
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        if appointed:
            c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
                      " VALUES (?,?,'member',0,?)", (DEPT_NODE, mid, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
    c.commit()
    c.close()


def main():
    from app.app import make_token
    cleanup()
    build_fixture()
    try:
        run_tests(make_token)
    finally:
        cleanup()
        print('\n=== 夹具已清理 ===')
    print('\n结果：%d 通过 / %d 失败' % (PASS, FAIL))
    return 1 if FAIL else 0


def run_tests(make_token):
    tok_in = make_token(PREFIX + 'in')
    tok_out = make_token(PREFIX + 'out')
    tok_owner = make_token(PREFIX + 'owner')
    tok_admin = make_token('admin')

    print('\n【用例1】可见性唯一来源 = 架构管理的看板绑定')
    for name, tok, expect in (('核算部成员', tok_in, True),
                               ('看板负责人', tok_owner, True),
                               ('未任命账号', tok_out, False),
                               ('管理员', tok_admin, True)):
        ids = [b['board_id'] for b in (http('/api/me', tok).get('boards') or [])]
        ok((BID in ids) == expect,
           '%s：可见该看板 = %s（实际 %s）' % (name, expect, BID in ids))

    print('\n【用例2】配了负责人**不额外收窄**可见性')
    # 该看板 owner = __acl_owner；若负责人语义仍是「仅负责人可见」，
    # 则核算部普通成员 __acl_in 就看不到它 —— 现在应看得见。
    ids = [b['board_id'] for b in (http('/api/me', tok_in).get('boards') or [])]
    ok(BID in ids, '看板配了负责人后，同部门普通成员仍可见（实际 %s）' % (BID in ids))
    r = http('/api/boards/%s/acl' % BID, tok_admin, 'PUT', {'owner': ''})
    ok(r.get('ok') is True, '管理员可清除负责人')
    ids = [b['board_id'] for b in (http('/api/me', tok_in).get('boards') or [])]
    ok(BID in ids, '清除负责人后，可见性不变（实际 %s）' % (BID in ids))
    http('/api/boards/%s/acl' % BID, tok_admin, 'PUT', {'owner': PREFIX + 'owner'})

    print('\n【用例3】越权看板在所有入口都被过滤')
    for path, label in (('/api/boards', '看板列表'),
                        ('/api/cards?board_id=' + BID, '事项列表'),
                        ('/api/overview?board_id=' + BID, '统计')):
        r = http(path, tok_out)
        if path.startswith('/api/boards'):
            hit = [b for b in (r.get('boards') or []) if b['board_id'] == BID]
            ok(not hit, '越权账号在「%s」中看不到该看板' % label)
        else:
            ok(r.get('total') == 0, '越权账号在「%s」中取到 0 条（实际 %s）' % (label, r.get('total')))

    print('\n【用例4】可见范围内的账号：板块与事项数一致')
    r = http('/api/boards/%s/columns' % BID, tok_in)
    names = sorted(c.get('column_name') for c in (r.get('columns') or []))
    ok(names == ['板块丙', '板块乙', '板块甲'], '核算部成员可见 3 个板块（实际 %s）' % names)
    cards = http('/api/cards?board_id=%s&size=99' % BID, tok_in)
    ov = http('/api/overview?board_id=%s' % BID, tok_in)
    ok(cards.get('total') == 6, '可见事项 6 条（实际 %s）' % cards.get('total'))
    ok(ov.get('total') == 6, '统计数 6 与事项数一致（实际 %s）' % ov.get('total'))

    print('\n【用例5】搜索结果与可见范围一致')
    q = urllib.parse.quote('可见性')
    for name, tok, expect in (('核算部成员', tok_in, 6), ('未任命账号', tok_out, 0)):
        r = http('/api/cards?q=%s&size=99' % q, tok)
        ok(r.get('total') == expect,
           '%s：搜索命中 %d 条（实际 %s）' % (name, expect, r.get('total')))

    print('\n【用例6】数据清理：无事项的板块删除，空看板一并删除')
    import sqlite3
    from app.app import cleanup_empty_columns_and_boards
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
              (BID + '::空板块', PREFIX + 'colEmpty', BID, '空板块', '2026-11-02 22:00:00', 'seed', '日常'))
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,'','',0,?)", (PREFIX + 'emptyboard', '【可见性】空看板', 'ws_acl',
                                            '2026-11-02 22:00:00'))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
              (PREFIX + 'emptyboard::空板块', PREFIX + 'colEmpty2', PREFIX + 'emptyboard',
               '空板块', '2026-11-02 22:00:00', 'seed', '日常'))
    c.commit()
    c.close()
    res = cleanup_empty_columns_and_boards()
    ok(res['deleted_columns'] >= 2, '空板块被删除（删了 %d 个）' % res['deleted_columns'])
    ok(res['deleted_boards'] >= 1, '空看板被一并删除（删了 %d 个）' % res['deleted_boards'])
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    n = c.execute("SELECT COUNT(*) FROM board_columns WHERE column_id=?", (PREFIX + 'colEmpty',)).fetchone()[0]
    ok(n == 0, '空板块已从库中消失')
    n = c.execute("SELECT COUNT(*) FROM boards WHERE board_id=?", (PREFIX + 'emptyboard',)).fetchone()[0]
    ok(n == 0, '空看板已从库中消失')
    n = c.execute("SELECT COUNT(*) FROM board_columns WHERE board_id=?", (BID,)).fetchone()[0]
    ok(n == 3, '有事项的看板下 3 个板块全部保留（实际 %d）' % n)
    c.close()

    print('\n【用例7】清理幂等：再跑一次不应重复删或报错')
    res2 = cleanup_empty_columns_and_boards()
    ok(res2['deleted_columns'] == 0 and res2['deleted_boards'] == 0,
       '二次清理无新增删除（板块 %d / 看板 %d）' % (res2['deleted_columns'], res2['deleted_boards']))


if __name__ == '__main__':
    sys.exit(main())
