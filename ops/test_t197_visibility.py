# -*- coding: utf-8 -*-
"""T-197 列表展示过滤（#113 严格口径）测试。

身份规则（用户确认：严格执行、不放宽、无特例）：
  事项可见 = 事项负责人 ∨ 事项参与人 ∨ 上级板块负责人 ∨ 上级看板负责人 ∨ 架构负责人
  板块可见 = 板块负责人 ∨ 板块参与人 ∨ 上级看板负责人 ∨ 架构负责人
  递归生效：板块被过滤 → 其下事项整体不展示（不因事项负责人/参与人身份放行 ——
          「板块无负责人/参与人但事项有」属数据问题，由数据修正解决，代码不兼容）。

夹具（__t197_ 前缀）——看板层：看板 B 归属部门 D7（board_config）+ 绑定工作组 G1
（workgroups.boards=B）；u_own1/u_cown/u_cpart/u_bown 任命为 G1 组员（看板壳可见，
2026-11-05 规则：部门成员不自动继承部门看板）；u_arch = D7 部门长（架构负责人，
负责范围覆盖 B）；u_none 无任何任命（对照：全不可见）。
板块与事项：
  C1 owner=u_cown        c1a owner=u_own1 / c1b owner=张三 cc=u_own1 / c1c 张三·李四
  C2 participants=u_cpart  c2a 张三（无身份） / c2b 张三·cc=u_cpart / c2c owner=u_cpart
  C3 无负责人/参与人       c3a owner=u_own1（数据问题样本：严格隐藏）
  C4 owner=u_cown        c4a owner=u_own1
预期：
  u_own1  板块 0 + 事项 0（C1/C4 对其隐藏——事项身份不能捞出隐藏板块下的事项）
  u_cown  板块 {C1,C4} + 其下全部 4 事项（板块负责人=事项的上级板块负责人）
  u_cpart 板块 {C2} + 事项 {c2b,c2c}（板块参与人仅见自己负责/参与的事项）
  u_bown  板块全部 + 事项全部 8（上级看板负责人）
  u_arch  板块全部 + 事项全部 8（架构负责人）
  admin   全部 8（豁免）
"""
import json, os, sqlite3, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'src', 'app.db')
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
P = '__t197_'
BID = P + 'bid'
C1, C2, C3, C4 = BID + '::' + P + '板块一', BID + '::' + P + '板块二', BID + '::' + P + '板块三', BID + '::' + P + '板块四'
NOW = '2026-11-13 10:00:00'
N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


def q(sql, args=()):
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    r = c.execute(sql, args).fetchall()
    c.close()
    return r


def cleanup():
    e = chr(92)
    pat = '%' + P.replace('_', e + '_') + '%'
    import time as _t
    c = None
    for attempt in range(6):
        try:
            c = sqlite3.connect(DB, timeout=20)
            c.execute('PRAGMA busy_timeout=20000')
            break
        except sqlite3.OperationalError:
            _t.sleep(2)
    if c is None:
        print('cleanup: 数据库持续锁定', flush=True)
        return -1
    # 架构夹具
    c.execute("DELETE FROM org_appointments WHERE node_id IN (960001, 960002)")
    c.execute("DELETE FROM org_nodes WHERE id IN (960001, 960002)")
    c.execute("DELETE FROM workgroups WHERE id = 960101")
    c.execute("DELETE FROM team_members WHERE account LIKE ? ESCAPE '{}'".format(e), (P + '%',))
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('users', 'username'),
                   ('board_config', 'board_id')):   # 2026-11-17 补：漏清 board_config → __t197_bid 残留三天（界面多出一个部门）
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'", (pat,))
    c.commit()
    n = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key'),
                   ('users', 'username'), ('board_config', 'board_id')):
        n += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{e}'",
                       (pat,)).fetchone()[0]
    n += c.execute("SELECT COUNT(*) FROM org_nodes WHERE id IN (960001, 960002)").fetchone()[0]
    n += c.execute("SELECT COUNT(*) FROM workgroups WHERE id = 960101").fetchone()[0]
    c.close()
    print('夹具残留自查: %d' % n, flush=True)
    return n


def setup():
    cleanup()
    c = None
    try:
        _setup_body()
    finally:
        if c is not None:
            c.close()


def _setup_body():
    global c
    c = sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    # 用户：u_bown(看板负责人) u_cown(板块负责人) u_cpart(板块参与人)
    #       u_own1(事项负责人/参与人) u_arch(架构负责人) u_none(无任何身份)
    for a in ('u_bown', 'u_cown', 'u_cpart', 'u_own1', 'u_arch', 'u_none'):
        c.execute("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq,allowed_boards,allowed_columns) "
                  "VALUES(?,?,?,?,?,?)", (P + a, hash_pw('At159357'), 'editor', 1, '*', '*'))
    # 成员（姓名=账号后缀样式，供 cc/owner 名单比对走姓名通道验证）
    for a, nm in (('u_bown', P + '王板长'), ('u_cown', P + '刘块长'), ('u_cpart', P + '陈块参'),
                  ('u_own1', P + '赵事项'), ('u_arch', P + '孙架构'), ('u_none', P + '钱围观')):
        c.execute("INSERT OR REPLACE INTO team_members(name,account,departments,created_at) VALUES(?,?,?,?)",
                  (nm, P + a, P + '部门D7', NOW))
    # 看板（owner=u_bown）
    c.execute("INSERT OR REPLACE INTO boards(board_id,board_name,owner,participants,created_at) VALUES(?,?,?,?,?)",
              (BID, P + '看板', P + 'u_bown', '', NOW))
    # 板块：C1 owner=u_cown；C2 participants=u_cpart；C3 无身份；C4 owner=u_cown
    for ck, cid, nm, owner, parts in (
            (C1, P + 'cid1', P + '板块一', P + 'u_cown', ''),
            (C2, P + 'cid2', P + '板块二', '', P + 'u_cpart'),
            (C3, P + 'cid3', P + '板块三', '', ''),
            (C4, P + 'cid4', P + '板块四', P + 'u_cown', '')):
        c.execute("INSERT OR REPLACE INTO board_columns(col_key,column_id,board_id,column_name,"
                  "created_at,creator,nature,year,completion,owner,participants) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (ck, cid, BID, nm, NOW, 'admin', '日常', '2026', 'open', owner, parts))
    # 事项
    # (card_id, column_id, column_name, card_name, owner, cc)
    cards = [
        (P + 'c1a', P + 'cid1', P + '板块一', P + '事项甲', P + 'u_own1', ''),
        (P + 'c1b', P + 'cid1', P + '板块一', P + '事项乙', '张三', P + 'u_own1'),
        (P + 'c1c', P + 'cid1', P + '板块一', P + '事项丙', '张三', '李四'),
        (P + 'c2a', P + 'cid2', P + '板块二', P + '事项丁', '张三', ''),
        (P + 'c2b', P + 'cid2', P + '板块二', P + '事项戊', '张三', P + 'u_cpart'),
        (P + 'c2c', P + 'cid2', P + '板块二', P + '事项己', P + 'u_cpart', ''),
        (P + 'c3a', P + 'cid3', P + '板块三', P + '事项庚', P + 'u_own1', ''),
        (P + 'c4a', P + 'cid4', P + '板块四', P + '事项辛', P + 'u_own1', ''),
    ]
    for cid, colid, cnm, name, owner, cc in cards:
        c.execute("INSERT OR REPLACE INTO cards(card_id,board_id,board_name,column_id,column_name,"
                  "card_name,status,owner,cc,created,deleted,parent_id) "
                  "VALUES(?,?,?,?,?,?,'open',?,?,?,0,'')",
                  (cid, BID, P + '看板', colid, cnm, name, owner, cc, NOW))
    # 架构：部门 D7（看板 B 归属）+ 工作组 G1（绑定看板 B，测试用户任命为组员）
    c.execute("INSERT OR REPLACE INTO org_nodes(id,name,node_type,parent_id,created_at) "
              "VALUES(960001,?,'dept',0,?)", (P + '部门D7', NOW))
    c.execute("INSERT OR REPLACE INTO workgroups(id,name,parent_id,leader,boards,created_at) "
              "VALUES(960101,?,960001,'',?,?)", (P + '组G1', BID, NOW))
    c.execute("INSERT OR REPLACE INTO org_nodes(id,name,node_type,parent_id,wg_id,created_at) "
              "VALUES(960002,?,'group',960001,960101,?)", (P + '组G1', NOW))
    c.execute("INSERT OR REPLACE INTO board_config(board_id,dept,dept_node_id,attr,status,created_at) "
              "VALUES(?,?,?,?,?,?)", (BID, P + '部门D7', 960001, '日常', '启用', NOW))
    # u_arch → 部门长（架构负责人身份）；其余测试用户 → G1 组员（看板壳可见）
    mid_arch = c.execute("SELECT id FROM team_members WHERE account=?", (P + 'u_arch',)).fetchone()[0]
    c.execute("INSERT OR REPLACE INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) "
              "VALUES(960001,?,'dept_head',0,?)", (mid_arch, NOW))
    for a in ('u_own1', 'u_cown', 'u_cpart', 'u_bown'):
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (P + a,)).fetchone()[0]
        c.execute("INSERT OR REPLACE INTO org_appointments(node_id,member_id,role_key,is_primary,created_at) "
                  "VALUES(960002,?,'member',0,?)", (mid, NOW))
    c.commit()
    c.close()


def call(method, path, token, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def tok(u):
    return make_token(P + u)


def names_of(username):
    """以某账号视角拉 /api/cards → (可见事项 id 集, 可见板块名集)"""
    s, d = call('GET', '/api/cards?board_ids=' + BID + '&size=100', tok(username))
    assert s == 200, 'cards %s → %s' % (username, s)
    ids = {x['card_id'] for x in d['cards']}
    cols = {x['column_name'] for x in d['columns']}
    return ids, cols


def main():
    total = 8
    print('== ① 无任何身份的末级用户（u_none）==', flush=True)
    ids, cols = names_of('u_none')
    ok(ids == set(), '无身份用户：0 事项（实际 %s）' % ids)
    ok(cols == set(), '无身份用户：0 板块（实际 %s）' % cols)

    print('== ② 递归生效：事项负责人捞不出隐藏板块下的事项（u_own1）==', flush=True)
    ids, cols = names_of('u_own1')
    ok(ids == set(), 'u_own1：0 事项 —— 其名下 c1a(板块一)/c3a(板块三)/c4a(板块四) 所在板块对其隐藏，'
                     '事项身份不放行（数据问题由数据修正解决）')
    ok(cols == set(), 'u_own1：0 板块（非板块负责人/参与人，C1/C4 亦隐藏）')

    print('== ③ 板块负责人（u_cown）==', flush=True)
    ids, cols = names_of('u_cown')
    ok(cols == {P + '板块一', P + '板块四'}, '板块负责人 → 板块一/四可见，板块二/三不可见（实际 %s）' % cols)
    ok(ids == {P + 'c1a', P + 'c1b', P + 'c1c', P + 'c4a'},
       '板块负责人 = 事项的上级板块负责人 → 板块内全部事项可见（实际 %s）' % ids)

    print('== ④ 板块参与人（u_cpart）==', flush=True)
    ids, cols = names_of('u_cpart')
    ok(cols == {P + '板块二'}, '板块参与人 → 仅板块二可见（实际 %s）' % cols)
    ok(ids == {P + 'c2b', P + 'c2c'},
       '板块参与人 → 仅自己参与(c2b)/负责(c2c)的事项；c2a 不可见（板块参与人不在事项身份清单）')

    print('== ⑤ 上级看板负责人（u_bown）==', flush=True)
    ids, cols = names_of('u_bown')
    ok(len(cols) == 4, '看板负责人 → 全部板块可见（实际 %s）' % cols)
    ok(len(ids) == total, '看板负责人 → 全部事项可见（实际 %d）' % len(ids))

    print('== ⑥ 架构负责人（u_arch，部门D7 部门长，看板B 归属该部门）==', flush=True)
    ids, cols = names_of('u_arch')
    ok(len(cols) == 4, '架构负责人 → 全部板块可见（实际 %s）' % cols)
    ok(len(ids) == total, '架构负责人 → 全部事项可见（实际 %d）' % len(ids))

    print('== ⑦ 管理员豁免 ==', flush=True)
    s, d = call('GET', '/api/cards?board_ids=' + BID + '&size=100', make_token('admin'))
    ok(s == 200 and len(d['cards']) == total, '管理员 → 全部可见（%d 事项）' % total)


if __name__ == '__main__':
    try:
        setup()
        main()
    finally:
        left = cleanup()
        fails = [m for c, m in N if not c]
        print('结果: PASS=%d FAIL=%d 残留=%d' % (len(N) - len(fails), len(fails), left), flush=True)
        for m in fails:
            print('  FAIL:', m)
        if fails or left:
            sys.exit(1)
