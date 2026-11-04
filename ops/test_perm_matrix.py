#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分级权限模型专项测试（2026-11-02）

层级：架构 > 看板 > 板块 > 事项
角色：架构负责人 > 看板负责人 > 板块负责人 > 事项负责人 > 参与人
      （管理员超脱体系；仅超管可配置管理员权限）

覆盖：
  用例1  角色等级判定：各层负责人/参与人命中正确等级
  用例2  继承：上级角色拥有下级角色的全部权限
  用例3  操作矩阵：谁能做什么（新增/修改/删除/指派）
  用例4  参与人权限边界：可改内容、无增删与指派权
  用例5  越权统一返回形式：HTTP 403 + 固定错误体
  用例6  边界情形：跨架构越权 / 负责人同时是参与人 / 移除负责人后权限即时失效
  用例7  管理员特权：超脱体系；但不能配置管理员权限（仅超管可以）

⚠️ 夹具纪律（§3.3）：
  · 夹具建在 `__perm_` 专属前缀命名空间
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
PREFIX = '__perm_'
BID = PREFIX + 'board'
CID = PREFIX + 'col'
CARD = PREFIX + 'card'
NODE = 4                      # 核算部（真实部门节点）
OTHER_NODE = 2                # 管理部（另一个部门 → 跨架构用）
ADMIN = 'admin'

# 夹具账号
A_ARCH = PREFIX + 'arch'      # 架构负责人（部门长）
A_BOARD = PREFIX + 'board'    # 看板负责人
A_COL = PREFIX + 'col'        # 板块负责人
A_CARD = PREFIX + 'card'      # 事项负责人
A_PART = PREFIX + 'part'      # 事项参与人
A_OUT = PREFIX + 'out'        # 架构外的人（无任命）
A_BOTH = PREFIX + 'both'      # 既是负责人又是参与人
A_ADMIN = PREFIX + 'admin'    # role=admin 的管理员（不是超管）

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
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'__err': str(e)}


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
    # ⚠️ 2026-11-04 修：用例4 通过 POST /api/boards 新建的看板，其 id 由后端自动生成
    #    （形如 B<时间戳>，**不带 __perm_ 前缀**）→ 原 cleanup 删不到 → 每跑一次漏一个，
    #    残留看板会污染 test_perm_scope 的可见性断言（多出一个 B1… 看板）。
    #    按本测试专用的「看板名 + 工作空间」标记精确清理。
    c.execute("DELETE FROM cards WHERE board_id IN "
              "(SELECT board_id FROM boards WHERE board_name=? AND workspace_id=?)",
              ('【分级权限】新看板', 'ws_pm'))
    c.execute("DELETE FROM board_columns WHERE board_id IN "
              "(SELECT board_id FROM boards WHERE board_name=? AND workspace_id=?)",
              ('【分级权限】新看板', 'ws_pm'))
    c.execute("DELETE FROM board_config WHERE board_id IN "
              "(SELECT board_id FROM boards WHERE board_name=? AND workspace_id=?)",
              ('【分级权限】新看板', 'ws_pm'))
    c.execute("DELETE FROM boards WHERE board_name=? AND workspace_id=?",
              ('【分级权限】新看板', 'ws_pm'))
    c.commit()
    c.close()


def build_fixture():
    """造夹具：1 看板 / 1 板块 / 1 事项，归属核算部。

    身份布局：
      __perm_arch   —— 架构负责人（org_nodes.owner = 核算部）
      __perm_board  —— 看板负责人（boards.owner）
      __perm_col    —— 板块负责人（board_columns.owner）
      __perm_card   —— 事项负责人（cards.owner）
      __perm_part   —— 事项参与人（cards.cc）
      __perm_both   —— 板块负责人 + 板块参与人（双重身份）
      __perm_out    —— 无任何身份
    """
    import sqlite3
    from app.app import hash_pw
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-02 23:00:00'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,'',0,?)", (BID, '【分级权限】看板', 'ws_pm', A_BOARD, now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (BID, '核算部', NODE, '日常', '启用', now))
    # 板块负责人 = A_COL（正常）；另建一个板块给 A_BOTH —— 它**同时**是负责人与参与人
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,?,?)",
              (BID + '::甲板块', CID, BID, '甲板块', now, 'seed', '日常', A_COL, ''))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,"
              "creator,nature,year,pinned,owner,participants) VALUES (?,?,?,?,?,?,?,2026,0,?,?)",
              (BID + '::乙板块', PREFIX + 'col2', BID, '乙板块', now, 'seed', '日常', A_BOTH, A_BOTH))
    c.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,
                  workspace_id,card_name,status,status_name,creator,owner,cc,created,parent_id,version,deleted)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
              (CARD, BID, '【分级权限】看板', CID, '甲板块', 'ws_pm', '【分级权限】事项',
               'open', '未开始', 'seed', A_CARD, A_PART, now))
    # 另一个架构（管理部）下的看板 —— 供跨架构比对
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
              " VALUES (?,?,?,?,'',0,?)", (PREFIX + 'otherboard', '【分级权限】他架构看板',
                                           'ws_pm', A_BOARD, now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?,?,?)", (PREFIX + 'otherboard', '管理部', OTHER_NODE, '日常', '启用', now))
    # 账号与成员
    for acct in (A_ARCH, A_BOARD, A_COL, A_CARD, A_PART, A_OUT, A_BOTH):
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (acct, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
    # 一个 role=admin 的管理员（**不是**内置超管）—— 用于验证「管理员不可配置管理员权限」
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
              (A_ADMIN, A_ADMIN, now))
    c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
              " VALUES (?,?,'admin','*','*',?)", (A_ADMIN, hash_pw('At159357'), now))
    # 全部任命到核算部（架构授权范围内），A_OUT 例外
    for acct in (A_ARCH, A_BOARD, A_COL, A_CARD, A_PART, A_BOTH):
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
                  " VALUES (?,?,'member',0,?)", (NODE, mid, now))
    # 架构负责人：核算部节点的 owner
    c.execute("UPDATE org_nodes SET owner=? WHERE id=?", (A_ARCH, NODE))
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
    tk = {k: make_token(v) for k, v in (
        ('arch', A_ARCH), ('board', A_BOARD), ('col', A_COL), ('card', A_CARD),
        ('part', A_PART), ('out', A_OUT), ('both', A_BOTH))}
    tk['admin'] = make_token(A_ADMIN)     # role=admin 的普通管理员（**不是**超管）
    tk['super'] = make_token(ADMIN)      # 内置超管 username=admin

    # ---------- 用例1：角色等级判定 ----------
    print('\n【用例1】角色等级判定')
    sys.path.insert(0, os.path.join(ROOT, 'src'))
    from app.perm import (effective_level, resource_chain, LV_NONE, LV_PARTICIPANT,
                           LV_CARD_OWNER, LV_COLUMN_OWNER, LV_BOARD_OWNER, LV_ARCH_OWNER)
    from app.app import dbq
    chain = resource_chain(dbq, card_id=CARD)
    ok(effective_level(dbq, A_CARD, chain) == LV_CARD_OWNER,
       '事项负责人 → 事项负责人级（实际 %d）' % effective_level(dbq, A_CARD, chain))
    ok(effective_level(dbq, A_PART, chain) == LV_PARTICIPANT,
       '事项参与人 → 参与人级（实际 %d）' % effective_level(dbq, A_PART, chain))
    ok(effective_level(dbq, A_COL, chain) == LV_COLUMN_OWNER,
       '板块负责人 → 板块负责人级（实际 %d）' % effective_level(dbq, A_COL, chain))
    ok(effective_level(dbq, A_BOARD, chain) == LV_BOARD_OWNER,
       '看板负责人 → 看板负责人级（实际 %d）' % effective_level(dbq, A_BOARD, chain))
    ok(effective_level(dbq, A_ARCH, chain) == LV_ARCH_OWNER,
       '架构负责人 → 架构负责人级（实际 %d）' % effective_level(dbq, A_ARCH, chain))
    ok(effective_level(dbq, A_OUT, chain) == LV_NONE,
       '无身份者 → 无权限级（实际 %d）' % effective_level(dbq, A_OUT, chain))
    # 双重身份：既是板块负责人又是板块参与人 → 取**高者**（乙板块）
    chain2 = resource_chain(dbq, board_id=BID, column_id=PREFIX + 'col2')
    ok(effective_level(dbq, A_BOTH, chain2) == LV_COLUMN_OWNER,
       '负责人同时是参与人 → 取负责人级（实际 %d）' % effective_level(dbq, A_BOTH, chain2))

    # ---------- 用例2：继承 ----------
    print('\n【用例2】继承：上级角色拥有下级角色的全部权限')
    # 看板负责人应能改其下的板块（板块负责人才能做的事）
    code, r = http('/api/columns', tk['board'], 'PUT', {
        'col_key': BID + '::甲板块', 'board_id': BID, 'column_name': '甲板块',
        'created_at': '2026-11-02', 'nature': '日常', 'year': '2026'})
    ok(code == 200, '看板负责人可改其下板块（继承板块负责人权限，实际 %s）' % code)
    # 板块负责人应能改其下事项（事项负责人才能做的事）
    code, r = http('/api/cards/%s' % CARD, tk['col'], 'PUT', {'fields': {'status': 'progressing'}})
    ok(code == 200, '板块负责人可改其下事项（继承事项负责人权限，实际 %s）' % code)
    # 架构负责人应能改该架构下的看板配置（看板负责人才能做的事）
    code, r = http('/api/board-config', tk['arch'], 'POST', {
        'board_id': BID, 'dept': '核算部', 'dept_node_id': NODE,
        'attr': '专项', 'status': '启用', 'remark': '架构负责人改的'})
    ok(code in (200, 409), '架构负责人可改该架构下看板（继承看板负责人权限，实际 %s）' % code)

    # ---------- 用例3：操作矩阵 ----------
    print('\n【用例3】操作矩阵：谁能做什么')
    # 事项负责人：可改可删；不可改他人事项
    code, r = http('/api/cards/%s' % CARD, tk['card'], 'PUT', {'fields': {'status': 'done'}})
    ok(code == 200, '事项负责人可改本事项（实际 %s）' % code)
    # 参与人：可改内容（可见内容），但无增删权
    code, r = http('/api/cards/%s' % CARD, tk['part'], 'PUT', {'fields': {'description': '参与人补充'}})
    ok(code == 200, '参与人可修改参与事项的内容（实际 %s）' % code)
    code, r = http('/api/cards/%s' % CARD, tk['part'], 'DELETE')
    ok(code == 403, '参与人**不可删除**事项（实际 %s）' % code)
    # 参与人不可指派
    code, r = http('/api/cards/%s' % CARD, tk['part'], 'PUT', {'fields': {'cc': A_OUT}})
    ok(code == 403, '参与人**不可指派**参与人（实际 %s）' % code)
    # 板块负责人可指派事项负责人
    code, r = http('/api/cards/%s' % CARD, tk['col'], 'PUT', {'fields': {'owner': A_PART}})
    ok(code == 200, '板块负责人可指派事项负责人（实际 %s）' % code)
    # 看板负责人可指派板块负责人
    code, r = http('/api/columns/%s/acl' % urllib.parse.quote(BID + '::甲板块', safe=''),
                   tk['board'], 'PUT', {'owner': A_CARD})
    ok(code == 200, '看板负责人可指派板块负责人（实际 %s）' % code)
    # 恢复
    http('/api/columns/%s/acl' % urllib.parse.quote(BID + '::甲板块', safe=''),
         tk['admin'], 'PUT', {'owner': A_COL})
    http('/api/cards/%s' % CARD, tk['col'], 'PUT', {'fields': {'owner': A_CARD}})

    # ---------- 用例4：新增权限的层级 ----------
    print('\n【用例4】新增（create）的层级约束')
    # 新增事项 = 板块负责人及以上
    code, r = http('/api/cards', tk['card'], 'POST', {
        'board_id': BID, 'column_id': CID, 'column_name': '甲板块',
        'card_name': '【分级权限】事项2'})
    ok(code == 403, '事项负责人**不可新增**事项（应板块负责人及以上，实际 %s）' % code)
    code, r = http('/api/cards', tk['col'], 'POST', {
        'board_id': BID, 'column_id': CID, 'column_name': '甲板块',
        'card_name': '【分级权限】事项2'})
    ok(code == 200, '板块负责人可新增事项（实际 %s）' % code)
    # 新增板块 = 看板负责人及以上
    code, r = http('/api/columns', tk['col'], 'POST', {
        'board_id': BID, 'column_name': '丁板块', 'created_at': '2026-11-02',
        'nature': '日常', 'year': '2026'})
    ok(code == 403, '板块负责人**不可新增**板块（应看板负责人及以上，实际 %s）' % code)
    code, r = http('/api/columns', tk['board'], 'POST', {
        'board_id': BID, 'column_name': '丙板块', 'created_at': '2026-11-02',
        'nature': '日常', 'year': '2026'})
    ok(code == 200, '看板负责人可新增板块（实际 %s）' % code)
    # 新增看板 = 架构负责人及以上
    code, r = http('/api/boards', tk['board'], 'POST', {
        'board_name': '【分级权限】新看板', 'workspace_id': 'ws_pm'})
    ok(code == 403, '看板负责人**不可新增**看板（应架构负责人及以上，实际 %s）' % code)
    code, r = http('/api/boards', tk['arch'], 'POST', {
        'board_name': '【分级权限】新看板', 'workspace_id': 'ws_pm'})
    ok(code == 200, '架构负责人可新增看板（实际 %s）' % code)

    # ---------- 用例5：越权统一返回形式 ----------
    print('\n【用例5】越权统一返回形式（HTTP 403 + 固定错误体）')
    code, r = http('/api/cards/%s' % CARD, tk['out'], 'PUT', {'fields': {'status': 'done'}})
    ok(code == 403, '无权限者修改 → HTTP 403（实际 %s）' % code)
    ok(r.get('error') == 'PERMISSION_DENIED',
       '错误体含 error=PERMISSION_DENIED（实际 %r）' % r.get('error'))
    ok(bool(r.get('code')), '错误体含细分 code（实际 %r）' % r.get('code'))
    ok(bool(r.get('message')), '错误体含可读 message（实际 %r）' % r.get('message'))
    ok('need_role' in r and 'have_role' in r,
       '错误体含 need_role / have_role（实际 %r / %r）' % (r.get('need_role'), r.get('have_role')))
    ok(r.get('op') in ('update', 'edit_content'),
       '错误体含操作码 op（实际 %r）' % r.get('op'))
    ok(bool(r.get('resource')), '错误体含资源标识（实际 %r）' % r.get('resource'))

    # ---------- 用例6：边界情形 ----------
    print('\n【用例6】边界情形')
    # ① 跨架构越权：管理部账号对核算部看板
    import sqlite3
    db = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    db.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
               (PREFIX + 'xarch', PREFIX + 'xarch', '2026-11-02 23:00:00'))
    mid = db.execute("SELECT id FROM team_members WHERE account=?", (PREFIX + 'xarch',)).fetchone()[0]
    db.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
               " VALUES (?,?,'member',0,?)", (OTHER_NODE, mid, '2026-11-02 23:00:00'))
    db.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
               " VALUES (?,'','editor','*','*',?)", (PREFIX + 'xarch', '2026-11-02 23:00:00'))
    db.execute("UPDATE org_nodes SET owner=? WHERE id=?", (PREFIX + 'xarch', OTHER_NODE))
    db.commit()
    db.close()
    tk['xarch'] = make_token(PREFIX + 'xarch')
    code, r = http('/api/columns', tk['xarch'], 'POST', {
        'board_id': BID, 'column_name': '戊板块', 'created_at': '2026-11-02',
        'nature': '日常', 'year': '2026'})
    ok(code == 403, '另一架构的负责人对跨界看板 → 403（实际 %s）' % code)
    ok(r.get('error') == 'PERMISSION_DENIED',
       '跨界操作返回统一的 PERMISSION_DENIED 错误体（实际 %r）' % r.get('error'))
    # CROSS_SCOPE_DENIED 是「同一资源但跨架构移动」这类操作的专用码，
    # 单独验证内核的 assert_same_arch 语义
    from app.perm import assert_same_arch, PermError
    chain_x = resource_chain(dbq, board_id=BID)
    chain_y = resource_chain(dbq, board_id=PREFIX + 'otherboard')
    raised = False
    try:
        assert_same_arch(dbq, chain_x, chain_y)
    except PermError as pe:
        raised = (pe.code == 'CROSS_SCOPE_DENIED')
    ok(raised, '跨架构资源比对 → 抛 CROSS_SCOPE_DENIED')

    # ② 负责人同时是参与人 → 取高者（已在上方用例1 验证，这里验证实际权限）
    #    乙板块下造一个事项，负责人与参与人都是 A_BOTH
    import sqlite3
    _db = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    _db.execute("""INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,
                     workspace_id,card_name,status,status_name,creator,owner,cc,created,parent_id,version,deleted)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'',1,0)""",
                  (PREFIX + 'card2', BID, '【分级权限】看板', PREFIX + 'col2', '乙板块', 'ws_pm',
                   '【分级权限】事项乙', 'open', '未开始', 'seed', A_BOTH, A_BOTH, '2026-11-02 23:00:00'))
    _db.commit()
    _db.close()
    code, r = http('/api/cards/%s' % (PREFIX + 'card2'), tk['both'],
                   'PUT', {'fields': {'status': 'progressing'}})
    ok(code == 200, '既是负责人又是参与人 → 按负责人权限放行（实际 %s）' % code)
    # 参与者（仅参与人身份）不可删除
    code, r = http('/api/cards/%s' % (PREFIX + 'card2'), tk['part'], 'DELETE')
    ok(code == 403, '仅参与人不可删除事项（实际 %s）' % code)

    # ③ 被移除负责人后权限**立即失效**
    code, r = http('/api/cards/%s' % CARD, tk['card'], 'PUT', {'fields': {'status': 'done'}})
    ok(code == 200, '移除前：事项负责人可改（实际 %s）' % code)
    # 把负责人换成别人
    http('/api/cards/%s' % CARD, tk['col'], 'PUT', {'fields': {'owner': A_PART}})
    code, r = http('/api/cards/%s' % CARD, tk['card'], 'PUT', {'fields': {'status': 'open'}})
    ok(code == 403, '被移除负责人后 → 权限**立即失效**（实际 %s）' % code)
    # 恢复
    http('/api/cards/%s' % CARD, tk['col'], 'PUT', {'fields': {'owner': A_CARD}})

    # ---------- 用例7：管理员特权 ----------
    print('\n【用例7】管理员特权与超管边界')
    # 管理员超脱体系：可以做所有事
    code, r = http('/api/cards/%s' % CARD, tk['admin'], 'PUT', {'fields': {'status': 'done'}})
    ok(code == 200, '管理员可修改任何事项（超脱体系，实际 %s）' % code)
    code, r = http('/api/boards/%s/acl' % BID, tk['admin'], 'PUT', {'owner': A_BOARD})
    ok(code == 200, '管理员可指定看板负责人（实际 %s）' % code)
    # 但管理员**不能配置管理员权限**（仅超管可）
    code, r = http('/api/admin/users', tk['admin'], 'POST', {
        'username': PREFIX + 'newadmin', 'password': 'At159357', 'role': 'admin'})
    ok(code == 403, '管理员**不可**授予他人管理员权限（实际 %s）' % code)
    ok(r.get('code') == 'ADMIN_ONLY',
       '该拒绝的 code=ADMIN_ONLY（实际 %r）' % r.get('code'))
    # 超管可以
    code, r = http('/api/admin/users', tk['super'], 'POST', {
        'username': PREFIX + 'newadmin', 'password': 'At159357', 'role': 'admin'})
    ok(code == 200, '超级管理员可授予管理员权限（实际 %s）' % code)
    # 清理新建的账号
    import sqlite3
    db = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    db.execute("DELETE FROM users WHERE username=?", (PREFIX + 'newadmin',))
    db.commit()
    db.close()


if __name__ == '__main__':
    sys.exit(main())
