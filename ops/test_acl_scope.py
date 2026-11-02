#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""专项测试：看板/板块 ACL（负责人 + 参与人）隔离 + 空板块/空看板清理

覆盖用户 2026-11-02 的四项要求：
  1. 术语：看板（boards 表）与板块（board_columns 表）不混用
  2. 看板 ACL：仅负责人 / 参与人可见该看板及其下属板块与事项
  3. 板块 ACL：板块对非 owner/参与人不可见（所属看板仍可见）
  4. 数据清理：无事项的板块删除；空看板一并删除

⚠️ 夹具纪律（§3.3）：
  · 夹具建在 `__acl_` 专属前缀命名空间
  · try/finally 保证无论断言成败都清理干净（删全 7 张表）
  · 断言里的数字全部来自**夹具自己造的数据**（可写死），
    绝不引用真实库的全量基线（那是别人的数据）
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
    """造夹具：1 个看板（owner + participants）、3 个板块（各有不同 ACL）、3 个账号"""
    import sqlite3
    from app.app import hash_pw
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-02 16:00:00'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,?,0,?)",
              (BID, '【ACL】测试看板', 'ws_acl', PREFIX + 'owner', PREFIX + 'part', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (BID, '核算部', 4, '日常', '启用', now))
    # 板块甲：无 ACL（任何可见该看板的人都能看到）
    # 板块乙：owner = __acl_owner
    # 板块丙：participants = __acl_part
    for cid, cname, ow, pt in ((PREFIX + 'colA', '板块甲', '', ''),
                               (PREFIX + 'colB', '板块乙', PREFIX + 'owner', ''),
                               (PREFIX + 'colC', '板块丙', '', PREFIX + 'part')):
        c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
                  "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,?,?)",
                  (BID + '::' + cname, cid, BID, cname, now, 'seed', '日常', ow, pt))
        for k in range(2):
            c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,
                          workspace_id,card_name,status,status_name,creator,created,parent_id,version,deleted)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                      ('%sc_%s_%d' % (PREFIX, cid[-4:], k), BID, '【ACL】测试看板', cid, cname,
                       'ws_acl', '【ACL】%s事项%d' % (cname, k), 'done', '已完成', 'seed', now))
    for acct in (PREFIX + 'owner', PREFIX + 'part', PREFIX + 'other'):
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
                  " VALUES (4,?,'member',0,?)", (mid, now))
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
    tok_owner = make_token(PREFIX + 'owner')
    tok_part = make_token(PREFIX + 'part')
    tok_other = make_token(PREFIX + 'other')
    tok_admin = make_token('admin')

    print('\n【用例1】看板 ACL：仅负责人 / 参与人可见该看板')
    for name, tok, expect in (('负责人', tok_owner, True),
                               ('参与人', tok_part, True),
                               ('无关账号', tok_other, False),
                               ('管理员', tok_admin, True)):
        me = http('/api/me', tok)
        ids = [b['board_id'] for b in (me.get('boards') or [])]
        ok((BID in ids) == expect,
           '%s：可见测试看板 = %s（实际 %s）' % (name, expect, BID in ids))

    print('\n【用例2】越权看板在所有入口都被过滤')
    for path, label in (('/api/boards', '看板列表'),
                        ('/api/cards?board_id=' + BID, '事项列表'),
                        ('/api/overview?board_id=' + BID, '统计')):
        r = http(path, tok_other)
        if path.startswith('/api/boards'):
            hit = [b for b in (r.get('boards') or []) if b['board_id'] == BID]
            ok(not hit, '越权账号在「%s」中看不到该看板' % label)
        else:
            ok(r.get('total') == 0, '越权账号在「%s」中取到 0 条（实际 %s）' % (label, r.get('total')))

    print('\n【用例3】板块 ACL：非 owner/参与人看不到该板块（但看板仍可见）')
    # 负责人：应看到 板块甲（无 ACL）+ 板块乙（owner 命中），看不到 板块丙
    r = http('/api/boards/%s/columns' % BID, tok_owner)
    names = sorted(c.get('column_name') for c in (r.get('columns') or []))
    ok(names == ['板块乙', '板块甲'], '负责人可见板块 = 板块甲 + 板块乙（实际 %s）' % names)
    # 参与人：应看到 板块甲 + 板块丙
    r = http('/api/boards/%s/columns' % BID, tok_part)
    names = sorted(c.get('column_name') for c in (r.get('columns') or []))
    ok(names == ['板块丙', '板块甲'], '参与人可见板块 = 板块甲 + 板块丙（实际 %s）' % names)
    # 无关账号：看板都看不到 → 板块也必然看不到
    r = http('/api/boards/%s/columns' % BID, tok_other)
    ok(not (r.get('columns') or []), '无关账号看不到任何板块')

    print('\n【用例4】ACL 生效时，事项数与统计口径一致')
    # 负责人：板块甲 2 条 + 板块乙 2 条 = 4
    for name, tok, expect in (('负责人', tok_owner, 4), ('参与人', tok_part, 4),
                               ('无关账号', tok_other, 0), ('管理员', tok_admin, 6)):
        cards = http('/api/cards?board_id=%s&size=99' % BID, tok)
        ov = http('/api/overview?board_id=%s' % BID, tok)
        ok(cards.get('total') == expect,
           '%s：可见事项 %d 条（实际 %s）' % (name, expect, cards.get('total')))
        ok(ov.get('total') == expect,
           '%s：统计数 %d 与事项数一致（实际 %s）' % (name, expect, ov.get('total')))

    print('\n【用例5】搜索结果同样遵守 ACL')
    q = urllib.parse.quote('ACL')
    for name, tok, expect in (('负责人', tok_owner, 4), ('参与人', tok_part, 4),
                               ('无关账号', tok_other, 0)):
        r = http('/api/cards?q=%s&size=99' % q, tok)
        ok(r.get('total') == expect,
           '%s：搜索命中 %d 条（实际 %s）' % (name, expect, r.get('total')))

    print('\n【用例6】ACL 可配置且可逆（管理员接口）')
    r = http('/api/boards/%s/acl' % BID, tok_admin, 'PUT',
             {'owner': PREFIX + 'part', 'participants': [PREFIX + 'owner']})
    ok(r.get('ok') is True, '管理员可设置看板 ACL')
    me = http('/api/me', tok_owner)
    ok(BID in [b['board_id'] for b in (me.get('boards') or [])],
       '改 ACL 后原负责人（转为参与人）仍可见')
    me = http('/api/me', tok_part)
    ok(BID in [b['board_id'] for b in (me.get('boards') or [])],
       '改 ACL 后新负责人可见')
    # 还原
    http('/api/boards/%s/acl' % BID, tok_admin, 'PUT',
         {'owner': PREFIX + 'owner', 'participants': [PREFIX + 'part']})
    me = http('/api/me', tok_other)
    ok(BID not in [b['board_id'] for b in (me.get('boards') or [])],
       '无关账号始终不可见（改 ACL 也不放行）')

    print('\n【用例7】未配置 ACL 的层级不额外收窄')
    # 板块甲 owner/participants 皆空 → 任何能看见该看板的人都应看到它
    r = http('/api/boards/%s/columns' % BID, tok_part)
    names = [c.get('column_name') for c in (r.get('columns') or [])]
    ok('板块甲' in names, '未配 ACL 的板块甲对所有可见该看板者可见（实际 %s）' % names)

    print('\n【用例8】数据清理：无事项的板块删除，空看板一并删除')
    import sqlite3
    from app.app import cleanup_empty_columns_and_boards
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    # 造一个空板块（无任何事项）
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
              (BID + '::空板块', PREFIX + 'colEmpty', BID, '空板块', '2026-11-02 16:00:00', 'seed', '日常'))
    # 再造一个「只有一个空板块」的看板 → 清理后应整块删除
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,'','',0,?)", (PREFIX + 'emptyboard', '【ACL】空看板', 'ws_acl',
                                            '2026-11-02 16:00:00'))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
              (PREFIX + 'emptyboard::空板块', PREFIX + 'colEmpty2', PREFIX + 'emptyboard',
               '空板块', '2026-11-02 16:00:00', 'seed', '日常'))
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

    print('\n【用例9】清理幂等：再跑一次不应重复删或报错')
    res2 = cleanup_empty_columns_and_boards()
    ok(res2['deleted_columns'] == 0 and res2['deleted_boards'] == 0,
       '二次清理无新增删除（板块 %d / 看板 %d）' % (res2['deleted_columns'], res2['deleted_boards']))


if __name__ == '__main__':
    sys.exit(main())
