# -*- coding: utf-8 -*-
"""#77 评论 @ 候选池权限过滤测试（2026-11-06 用户需求 + 补充确认）：

① GET /api/cards/{id}/mention_pool 只返回**对该卡片所属看板有架构内可见路径**的成员姓名
   （user_allowed(arch_only=True) 唯一权威实现加开关；看板负责人可见 / 无关者不可见）
② **管理员的超管可见性不计入**（用户补充确认：管理员权限独立于架构外，
   「不能因为是管理员就谁都能 @ 到」——管理员只有同时具备架构内身份才进候选池）
③ 无可见权限者请求候选池 → 403（check_card_access 越权读兜底）
④ 没有登录账号的成员天然不在池中（无法登录、收不到提及消息）
⑤ 公开看板（未归属）对任何账号可见 → 管理员账号也进池（架构口径的公共层，非超管捷径）

夹具（__mp_ 前缀，自清理）：
  __mp_admin  admin   —— 请求者；无架构身份 → 不进私有看板候选池（②验证）
  __mp_vis    editor  —— 看板 __mp_B1 的负责人（可见）
  __mp_hid    editor  —— 无任何架构归属（不可见）
  __mp_noacc  无账号成员 —— 天然不可见（无 users 行）
  __mp_D      部门节点（B1 归属其下 → 非公共看板）
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PREFIX = '__mp_'
PWD = 'At159357'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http(path, method='GET', body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}

def setup():
    from app.app import hash_pw, make_token  # noqa
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    now = '2026-11-06 08:00:00'
    cleanup_db(c)
    # 成员 + 账号
    for k, role in (('admin', 'admin'), ('vis', 'editor'), ('hid', 'editor')):
        acct = PREFIX + k
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + k, acct, now))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,?,?,?,?)", (acct, hash_pw(PWD), role, '*', '*', now))
    # 无账号成员（验证 ③）
    c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'','',?)",
              (PREFIX + 'noacc', now))
    # 归属部门节点（B1 挂其下 → 非公共看板）
    wg = c.execute("INSERT INTO workgroups (name,parent_id,leader,function,boards) VALUES (?,0,'','', '')",
                   (PREFIX + 'D',)).lastrowid
    c.execute("INSERT INTO org_nodes (name,node_type,parent_id,wg_id) VALUES (?,?,0,?)",
              (PREFIX + 'D', 'dept', wg))
    nD = c.execute("SELECT id FROM org_nodes WHERE name=?", (PREFIX + 'D',)).fetchone()[0]
    # 看板 B1：负责人 = __mp_vis（可见性来源），归属 __mp_D（非公共）
    bid = PREFIX + 'B1'
    c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,sort,created_at) VALUES (?,?,?,?,'',?)",
              (bid, PREFIX + 'B1', '', PREFIX + 'vis', now))
    c.execute("INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants)"
              " VALUES (?,?,?,?,?,'x','日常','2026',0,'','')",
              (bid + '::C1', PREFIX + 'col1', bid, 'C1', now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at) VALUES (?,?,?,?,?,'',?)",
              (bid, PREFIX + 'D', nD, '日常', '启用', now))
    # 卡片
    cid = PREFIX + 'C1'
    c.execute("INSERT INTO cards (card_id,board_id,card_name,creator,deleted,created) VALUES (?,?,?,?,0,?)",
              (cid, bid, PREFIX + 'C1', PREFIX + 'vis', now))
    c.commit(); c.close()
    tk = {k: make_token(PREFIX + k) for k in ('admin', 'vis', 'hid')}
    return {'cid': cid, 'bid': bid, 'tk': tk}

def cleanup_db(c):
    for t, col in (('cards', 'card_id'), ('board_columns', 'board_id'),
                   ('board_config', 'board_id'), ('boards', 'board_id')):
        c.execute("DELETE FROM %s WHERE %s LIKE ?" % (t, col), (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE name LIKE ? OR account LIKE ?", (PREFIX + '%', PREFIX + '%'))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM workgroups WHERE name LIKE ?", (PREFIX + '%',))

def main():
    fx = setup()
    tk = fx['tk']
    try:
        print('\n【1】管理员拉候选池（私有看板）')
        code, r = http('/api/cards/%s/mention_pool' % fx['cid'], token=tk['admin'])
        ok(code == 200, '请求候选池 → 200（实际 %s）' % code)
        names = r.get('names') or []
        # 生产环境中「中心负责人/总经理」按架构口径管理层全范围可见（如余河），
        # 会合法出现在池中 —— 断言用成员条件而非精确相等（不硬编码全局基线，§3.3）
        ok(PREFIX + 'vis' in names, '看板负责人 __mp_vis 在池中')
        ok(PREFIX + 'hid' not in names, '无可见权限的 __mp_hid 被过滤')
        ok(PREFIX + 'noacc' not in names, '无登录账号的 __mp_noacc 天然不在池中')
        ok(PREFIX + 'admin' not in names,
           '管理员 __mp_admin（无架构身份）不进池——超管可见性不计入 @ 候选（用户 2026-11-06 确认）')

        print('\n【2】越权读兜底')
        code, _ = http('/api/cards/%s/mention_pool' % fx['cid'], token=tk['hid'])
        ok(code == 403, '无看板可见权限者请求候选池 → 403（实际 %s）' % code)
        code, _ = http('/api/cards/%s/mention_pool' % fx['cid'], token=tk['vis'])
        ok(code == 200, '看板负责人自己请求 → 200（实际 %s）' % code)

        print('\n【3】公开看板对照（未归属 → 架构口径全员可见）')
        # 把 B1 的归属配置删掉 → 变公共看板 → 任何账号（含管理员）都应进入候选池
        # （这是公共层语义，不是超管捷径）
        c = sqlite3.connect(DB)
        c.execute("DELETE FROM board_config WHERE board_id=?", (fx['bid'],))
        c.commit(); c.close()
        code, r = http('/api/cards/%s/mention_pool' % fx['cid'], token=tk['admin'])
        names = (r.get('names') or [])
        ok(code == 200 and PREFIX + 'hid' in names and PREFIX + 'vis' in names
           and PREFIX + 'admin' in names,
           '公共看板候选池含 vis + hid + admin（实际 %d 人）' % len(names))
    finally:
        c = sqlite3.connect(DB)
        cleanup_db(c)
        c.commit(); c.close()
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

if __name__ == '__main__':
    main()
