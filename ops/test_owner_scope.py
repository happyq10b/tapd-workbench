#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""专项测试：看板 / 板块负责人语义（2026-11-02 修订）+ 空板块/空看板清理

⚠️ **语义与旧版不同**（用户 2026-11-02 拍板）：
  · 负责人 = **管理权**（有权修改该看板 / 板块的基本信息），**不再收窄可见性**
  · **谁能看见看板** → 统一由【架构管理】的看板绑定决定
  · **参与人（participants）机制整体下线**

本测试覆盖：
  1. 看板负责人：可改该看板基本信息（归属部门 / 属性 / 状态 / 备注）
  2. 非负责人非管理员：改不了（403）
  3. 板块负责人：可改该板块基本信息
  4. 负责人**不影响可见性** —— 配了 owner 的看板，架构绑定者照样看得见
  5. 负责人可改的看板，必须**同时**在架构授权范围内（fail-closed：管理权不放大可见性）
  6. 数据清理：无事项的板块删除；空看板一并删除

⚠️ 夹具纪律（§3.3）：
  · 夹具建在 `__own_` 专属前缀命名空间
  · try/finally 保证无论断言成败都清理干净（删全相关表）
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
PREFIX = '__own_'
BID = PREFIX + 'board'
DEPT_NODE = 4          # 核算部（真实存在的部门节点，夹具看板挂在它下面）
ADMIN = 'admin'

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
    """造夹具：1 个看板（负责人 = __own_mgr）、1 个板块（负责人 = __own_mgr）、3 个账号。

    账号：
      __own_mgr   —— 看板 + 板块的负责人，任命在核算部（架构授权范围内）
      __own_peer  —— 同在核算部，但**不是**负责人
      __own_out   —— 不在核算部（无架构授权）
    """
    import sqlite3
    from app.app import hash_pw
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-02 22:00:00'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,'',0,?)",
              (BID, '【负责人】测试看板', 'ws_own', PREFIX + 'mgr', now))
    # 归属核算部 → 核算部成员在架构授权范围内
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)"
              " VALUES (?,?,?,?,?,'',?)", (BID, '核算部', DEPT_NODE, '日常', '启用', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants)"
              " VALUES (?,?,?,?,?,?,?,2026,0,?,'')",
              (BID + '::甲板块', PREFIX + 'col', BID, '甲板块', now, 'seed', '日常', PREFIX + 'mgr'))
    for k in range(2):
        c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,
                      workspace_id,card_name,status,status_name,creator,created,parent_id,version,deleted)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                  ('%sc_%d' % (PREFIX, k), BID, '【负责人】测试看板', PREFIX + 'col', '甲板块',
                   'ws_own', '【负责人】事项%d' % k, 'done', '已完成', 'seed', now))
    for acct in (PREFIX + 'mgr', PREFIX + 'peer', PREFIX + 'out'):
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        # mgr / peer 任命在核算部（架构授权范围内）；out 不任命（无架构授权）
        if acct != PREFIX + 'out':
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
    tok_mgr = make_token(PREFIX + 'mgr')
    tok_peer = make_token(PREFIX + 'peer')
    tok_out = make_token(PREFIX + 'out')
    tok_admin = make_token(ADMIN)

    print('\n【用例1】看板负责人：可改该看板基本信息')
    # 夹具已带 board_config 行（用例3 依赖它）→ 这里测「不存在配置时由负责人新建」：
    # 先临时删掉配置行，再由负责人新建。
    import sqlite3
    _c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    _c.execute('DELETE FROM board_config WHERE board_id=?', (BID,))
    _c.commit(); _c.close()
    r = http('/api/board-config', tok_mgr, 'POST',
             {'board_id': BID, 'dept': '核算部', 'dept_node_id': DEPT_NODE,
              'attr': '专项', 'status': '启用', 'remark': '负责人改的'})
    ok(r.get('ok') is True, '负责人可新建看板配置（实际 %s）' % r.get('__err', 'ok'))

    print('\n【用例2】非负责人非管理员：改不了看板基本信息（403）')
    r = http('/api/board-config', tok_peer, 'POST',
             {'board_id': BID, 'dept': '核算部', 'dept_node_id': DEPT_NODE,
              'attr': '日常', 'status': '启用', 'remark': ''})
    ok(r.get('__err') == 403, '非负责人被拒（实际 %s）' % r.get('__err'))

    print('\n【用例3】负责人：可改已存在配置的看板')
    cid = None
    for b in http('/api/boards', tok_admin).get('boards', []):
        if b['board_id'] == BID:
            cid = b.get('config_id')
    ok(cid is not None, '夹具看板已有配置行（config_id=%s）' % cid)
    r = http('/api/board-config/%s' % cid, tok_mgr, 'PUT',
             {'board_id': BID, 'dept': '核算部', 'dept_node_id': DEPT_NODE,
              'attr': '日常', 'status': '封存', 'remark': '负责人改的属性'})
    ok(r.get('ok') is True, '负责人可更新看板配置（实际 %s）' % r.get('__err', 'ok'))
    b = [x for x in http('/api/boards', tok_admin).get('boards', []) if x['board_id'] == BID]
    ok(b and b[0]['status'] == '封存', '修改已生效（status=%s）' % (b[0]['status'] if b else '?'))

    print('\n【用例4】负责人不影响可见性 —— 架构绑定者照样看得见')
    for name, tok, expect in (('负责人', tok_mgr, True),
                               ('同部门非负责人', tok_peer, True),
                               ('管理员', tok_admin, True),
                               ('无架构授权账号', tok_out, False)):
        ids = [x['board_id'] for x in (http('/api/me', tok).get('boards') or [])]
        ok((BID in ids) == expect,
           '%s：可见该看板 = %s（实际 %s）' % (name, expect, BID in ids))

    print('\n【用例5】管理权不放大可见性 —— 无架构授权者即便被指定也不可见')
    r = http('/api/boards/%s/acl' % BID, tok_admin, 'PUT', {'owner': PREFIX + 'out'})
    ok(r.get('ok') is True, '管理员可把负责人设为无架构授权账号')
    ids = [x['board_id'] for x in (http('/api/me', tok_out).get('boards') or [])]
    ok(BID not in ids, '被指定为负责人但无架构授权 → 仍看不到该看板（fail-closed）')
    # 换回负责人
    http('/api/boards/%s/acl' % BID, tok_admin, 'PUT', {'owner': PREFIX + 'mgr'})

    print('\n【用例6】板块负责人：可改该板块基本信息')
    colkey = BID + '::甲板块'
    r = http('/api/columns', tok_mgr, 'PUT',
             {'col_key': colkey, 'board_id': BID, 'column_name': '甲板块',
              'created_at': '2026-11-02', 'nature': '日常', 'year': '2026'})
    ok(r.get('ok') is True, '板块负责人可编辑板块（实际 %s）' % r.get('__err', 'ok'))
    r = http('/api/columns', tok_peer, 'PUT',
             {'col_key': colkey, 'board_id': BID, 'column_name': '甲板块',
              'created_at': '2026-11-02', 'nature': '日常', 'year': '2026'})
    ok(r.get('__err') == 403, '非负责人改板块被拒（实际 %s）' % r.get('__err'))

    print('\n【用例7】板块负责人不改变板块可见性')
    r = http('/api/boards/%s/columns' % BID, tok_peer)
    names = [c.get('column_name') for c in (r.get('columns') or [])]
    ok('甲板块' in names, '同部门非负责人仍能看到该板块（实际 %s）' % names)

    print('\n【用例8】只有管理员能指定负责人')
    r = http('/api/boards/%s/acl' % BID, tok_mgr, 'PUT', {'owner': PREFIX + 'peer'})
    ok(r.get('__err') == 403, '负责人自己不能改负责人（实际 %s）' % r.get('__err'))
    r = http('/api/columns/%s/acl' % urllib.parse.quote(colkey, safe=''), tok_mgr, 'PUT',
             {'owner': PREFIX + 'peer'})
    ok(r.get('__err') == 403, '负责人自己不能改板块负责人（实际 %s）' % r.get('__err'))

    print('\n【用例9】参与人机制已下线：传入 participants 会被忽略并清空')
    r = http('/api/boards/%s/acl' % BID, tok_admin, 'PUT',
             {'owner': PREFIX + 'mgr', 'participants': [PREFIX + 'peer']})
    ok(r.get('ok') is True, '管理员设置负责人成功')
    ok(r.get('participants') == '', '响应中参与人已被清空（实际 %r）' % r.get('participants'))
    ids = [x['board_id'] for x in (http('/api/me', tok_peer).get('boards') or [])]
    ok(BID in ids, '参与人字段不影响可见性（peer 仍因架构绑定而可见）')

    print('\n【用例10】数据清理：无事项的板块删除，空看板一并删除')
    import sqlite3
    from app.app import cleanup_empty_columns_and_boards
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,'','')",
              (BID + '::空板块', PREFIX + 'colEmpty', BID, '空板块', '2026-11-02 22:00:00', 'seed', '日常'))
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,'','',0,?)", (PREFIX + 'emptyboard', '【负责人】空看板', 'ws_own',
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
    c.close()

    print('\n【用例11】清理幂等：再跑一次不应重复删或报错')
    res2 = cleanup_empty_columns_and_boards()
    ok(res2['deleted_columns'] == 0 and res2['deleted_boards'] == 0,
       '二次清理无新增删除（板块 %d / 看板 %d）' % (res2['deleted_columns'], res2['deleted_boards']))


if __name__ == '__main__':
    sys.exit(main())
