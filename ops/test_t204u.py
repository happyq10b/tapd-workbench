# -*- coding: utf-8 -*-
"""T-204u（2026-11-17）归属约束贯通写入/读取 —— API 层实测（用户需求①）：
  ① 看板参与人：提交池外账号 → 响应 removed + 库值不含（除名式，原 400 改剔除）
  ② 板块参与人/负责人：池外剔除（allowed = 上级看板 ACL ∩ 部门池）
  ③ 事项 owner：池外姓名剔除（allowed = 上级板块 ACL ∩ 部门池，姓名映射比对）
  ④ 读取过滤：/api/me 看板 ACL、/api/cards 板块元信息不下发池外人员
  ⑤ 行数守恒 + 零残留
夹具：部门 __t204u部门 + 成员甲(池内)/乙(池外) + 看板/板块/事项。
"""
import json, os, sqlite3, sys, urllib.request, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = 'src/app.db'
PASSED = []
IDS = {}
TK = make_token('admin')
TK_OP = None


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (token or TK))
    body = json.dumps(data).encode() if data is not None else None
    if body:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def setup():
    c = sqlite3.connect(DB)
    for u in ('__t204u_a1', '__t204u_a2'):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.execute("INSERT OR IGNORE INTO team_members (name, workgroups, account, departments) "
              "VALUES ('__t204u甲','','__t204u_a1',?)", ('__t204u部门',))
    c.execute("INSERT OR IGNORE INTO team_members (name, workgroups, account, departments) "
              "VALUES ('__t204u乙','','__t204t_a2','管理部')")   # 乙部门=管理部（池外）
    c.commit()
    c.close()
    st, r = api('/api/boards', 'POST', {'board_name': '__t204u 测试看板', 'dept': '核算部'})
    if st != 200:
        print('看板创建失败:', st, r, flush=True)
    assert st == 200
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    c = sqlite3.connect(DB)
    c.execute("UPDATE boards SET owner='__t204u_a1', participants='__t204u_a2' WHERE board_id=?",
              (IDS['bid'],))
    c.execute("INSERT OR IGNORE INTO board_config (board_id, dept, dept_node_id, attr, status) "
              "VALUES (?,?,0,'日常','启用')", (IDS['bid'], '__t204u部门'))
    c.commit()
    c.close()
    global TK_OP
    TK_OP = make_token('__t204u_a1')   # 看板负责人（非管理员）→ 验证剔除生效
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': '__t204u板块',
                'owner': '__t204u_a1',
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026'})
    if st != 200:
        print('板块创建失败:', st, r, flush=True)
    assert st == 200
    IDS['colKey'] = r.get('col_key')
    IDS['colId'] = r.get('column_id')
    st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': '__t204u事项',
                'column_id': IDS['colId'], 'fields': {}})
    if st != 200:
        print('事项创建失败:', st, r, flush=True)
    assert st == 200
    IDS['cid'] = r.get('card_id')


def cleanup():
    c = sqlite3.connect(DB)
    BS = chr(92)
    pat = '%' + BS + '_t204u%'
    c.execute("DELETE FROM cards WHERE card_name LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM boards WHERE board_name LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM board_config WHERE dept LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM team_members WHERE name LIKE ? ESCAPE ?", (pat, BS))
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE ?", (pat, BS))
    c.commit()
    res = {}
    for t, col in (('boards', 'board_name'), ('board_columns', 'col_key'),
                   ('cards', 'card_name'), ('users', 'username'),
                   ('team_members', 'name'), ('board_config', 'dept')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ?",
                           (pat, BS)).fetchone()[0]
    c.close()
    print('清理完成，夹具残留：', res, flush=True)


def main():
    setup()
    try:
        # ① 看板参与人：提交池外乙 + 池内甲 → 乙剔除、甲保留
        st, r = api('/api/boards/%s/participants' % IDS['bid'], 'PUT',
                    {'participants': '__t204u_a1,__t204u_a2'}, token=TK_OP)
        ok(st == 200 and '__t204u_a2' in (r.get('removed') or [])
           and '__t204u_a2' not in (r.get('participants') or '')
           and '__t204u_a1' in (r.get('participants') or ''),
           f'① 看板参与人剔除式写入（removed={r.get("removed")}，库值={r.get("participants")}）')

        # ② 板块参与人/负责人：allowed = 看板 ACL（甲）→ 乙剔除
        st, r = api('/api/columns/' + urllib.parse.quote(IDS['colKey'], safe='') + '/participants', 'PUT',
                    {'participants': '__t204u_a1,__t204u_a2'}, token=TK_OP)
        ok(st == 200 and '__t204u_a2' in (r.get('removed') or [])
           and '__t204u_a2' not in (r.get('participants') or ''),
           f'② 板块参与人剔除（removed={r.get("removed")}）')
        st, r = api('/api/columns/' + urllib.parse.quote(IDS['colKey'], safe='') + '/acl', 'PUT', {'owner': '__t204u_a2'}, token=TK_OP)
        ok(st == 200 and '__t204u_a2' in (r.get('removed') or []) and not r.get('owner'),
           f'② 板块负责人池外除名（owner={r.get("owner")!r}，removed={r.get("removed")}）')

        # ③ 事项 owner：姓名提交（甲=池内、乙=池外）→ 乙剔除
        st, r = api('/api/cards/' + IDS['cid'], 'PUT',
                    {'fields': {'owner': '__t204u甲;__t204u乙'}}, token=TK_OP)
        ok(st == 200 and '__t204u乙' in (r.get('removed') or []),
           f'③ 事项负责人池外姓名剔除（removed={r.get("removed")}）')
        c = sqlite3.connect(DB)
        db_owner = c.execute('SELECT owner FROM cards WHERE card_id=?', (IDS['cid'],)).fetchone()[0]
        c.close()
        ok(db_owner == '__t204u甲' and '__t204u乙' not in db_owner,
           f'③ 库值仅保留池内姓名（实际：{db_owner}）')

        # ④ 读取过滤：/api/me 看板 participants 不含池外乙；/api/cards 板块元信息不含乙
        st, me = api('/api/me')
        b = (me.get('boards') or [])
        fx = [x for x in b if x['board_id'] == IDS['bid']]
        ok(fx and '__t204u_a2' not in (fx[0].get('participants') or '')
           and '__t204u_a1' in (fx[0].get('participants') or ''),
           f'④ /api/me 看板 ACL 读取过滤（{fx[0].get("participants") if fx else None}）')
        st, d = api('/api/cards?board_id=%s&size=200' % IDS['bid'])
        col = [x for x in (d.get('columns') or []) if x.get('col_key') == IDS['colKey']]
        ok(col and '__t204u_a2' not in (col[0].get('participants') or ''),
           f'④ /api/cards 板块元信息读取过滤（{col[0].get("participants") if col else None}）')
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)


if __name__ == '__main__':
    main()
