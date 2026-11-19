# -*- coding: utf-8 -*-
"""#205ad 看板封存/启用（2026-11-19 用户需求）API 实测

需求：封存与启用仅允许架构负责人角色执行；封存后的看板不对外展示，
仅「看板管理」页可见；无权限操作要有提示与拦截。

覆盖：
① 架构负责人封存成功（boards.archived=1）② 架构负责人启用成功
③ 普通成员封存被拦 403（报错文案含「架构负责人」）
④ 看板负责人（非架构负责人）封存被拦 403 —— 证明「看板负责人 ≠ 架构负责人」
⑤ 封存后 /api/me（普通视图 tabs）不再下发该看板（管理员与普通成员均如此）
⑥ /api/boards 默认不含封存看板；?include_archived=1 含且 archived=1
⑦ /api/cards 不再下发封存看板的事项（普通视图数据源）
⑧ 重复封存幂等（noop=true，不写库）
⑨ 不存在的看板 404
⑩ 前端接线静态断言（bcArchive / badge-archived / include_archived=1 / arch_owner）

夹具（__t205ad_ 前缀，finally 自清理 + 零残留自查）：
- 架构节点 D1（org_nodes.owner = 架构负责人账号 —— 来源 A 显式配置）
- users：lead（架构负责人）/ member（普通成员，同时是 B1 的看板负责人）
- 看板 B1、B2（不登记 board_config → 公共看板 → 两个账号都可见，便于对比可见性变化）
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')

from app.app import make_token, hash_pw   # noqa: E402

BASE = 'http://127.0.0.1:8100'
PREFIX = '__t205ad_'
B1 = PREFIX + '看板一'
B2 = PREFIX + '看板二'
LEAD = PREFIX + 'lead'
MEMBER = PREFIX + 'member'
_n = {'ok': 0, 'fail': 0}


def ok(cond, msg):
    if cond:
        _n['ok'] += 1
        print('  PASS ' + msg)
    else:
        _n['fail'] += 1
        print('  FAIL ' + msg)


def api(path, method='GET', body=None, token=''):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + token)
    data = json.dumps(body).encode() if body is not None else None
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def cleanup():
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    c.execute("DELETE FROM org_appointments WHERE node_id IN (SELECT id FROM org_nodes WHERE name LIKE ?)", (PREFIX + '%',))
    c.execute("DELETE FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM team_members WHERE account LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?", (PREFIX + '%',))
    c.execute("DELETE FROM boards WHERE board_id LIKE ?", (PREFIX + '%',))
    c.commit()
    c.close()


def build():
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    now = '2026-11-19 09:00:00'
    # 架构节点 D1：owner 直接写架构负责人账号（perm.py 来源 A 显式配置，账号直比）
    c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
              " VALUES (9101,?,'dept',0,0,'','',0,?)", (PREFIX + 'D1', now))
    c.execute("UPDATE org_nodes SET owner=? WHERE id=9101", (LEAD,))
    # 看板 B1：owner=member（看板负责人 ≠ 架构负责人）；B2：无负责人
    for bid, name, owner in ((B1, PREFIX + '看板一', MEMBER), (B2, PREFIX + '看板二', '')):
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
                  " VALUES (?,?,?,?, '',0,?)", (bid, name, '', owner, now))
    # 两个测试账号（editor；allowed_boards='*' 不额外收窄）
    for acct in (LEAD, MEMBER):
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
    c.commit()
    c.close()


def board_arch(bid):
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    r = c.execute('SELECT archived FROM boards WHERE board_id=?', (bid,)).fetchone()
    c.close()
    return (r[0] if r else None)


def me_board_ids(token):
    st, d = api('/api/me', token=token)
    return st, {b['board_id'] for b in (d.get('boards') or [])}


def main():
    cleanup()
    build()
    tk_admin = make_token('admin')
    tk_lead = make_token(LEAD)
    tk_member = make_token(MEMBER)
    try:
        # ⓪ 前置：两账号初始都能看到夹具看板（公共看板 + 白名单不收窄）
        st, ids = me_board_ids(tk_lead)
        ok(st == 200 and B1 in ids and B2 in ids,
           '⓪ 前置：架构负责人账号初始可见夹具看板')
        st, ids = me_board_ids(tk_member)
        ok(st == 200 and B1 in ids, '⓪ 前置：普通成员账号初始可见夹具看板')
        me_admin = api('/api/me', token=tk_admin)[1]
        ok(me_admin.get('arch_owner') is True, '⓪ 前置：管理员 arch_owner=True')

        # ③ 普通成员封存被拦 403（文案含「架构负责人」）
        st3, d3 = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                      {'archived': True}, token=tk_member)
        ok(st3 == 403 and '架构负责人' in json.dumps(d3, ensure_ascii=False),
           '③ 普通成员封存被拦 403（文案：%s）' % json.dumps(d3, ensure_ascii=False)[:60])

        # ④ 看板负责人（member 同时是 B1 的 owner）封存被拦 —— 看板负责人 ≠ 架构负责人
        ok(st3 == 403 and board_arch(B1) == 0,
           '④ 看板负责人（B1.owner=member）封存被拦且状态未变')

        # ① 架构负责人封存成功
        st1, d1 = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                      {'archived': True}, token=tk_lead)
        ok(st1 == 200 and d1.get('ok') and d1.get('archived') == 1 and board_arch(B1) == 1,
           '① 架构负责人封存成功（boards.archived=1）')

        # ⑧ 重复封存幂等
        st8, d8 = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                      {'archived': True}, token=tk_lead)
        ok(st8 == 200 and d8.get('noop') is True and board_arch(B1) == 1,
           '⑧ 重复封存幂等（noop=true，状态不变）')

        # ⑤ 封存后 /api/me 不下发（普通成员 + 管理员均如此）
        st, ids = me_board_ids(tk_member)
        ok(st == 200 and B1 not in ids and B2 in ids,
           '⑤-a 封存后普通成员 /api/me 不含封存看板（B2 仍可见）')
        st, ids = me_board_ids(tk_admin)
        ok(st == 200 and B1 not in ids,
           '⑤-b 封存后管理员普通视图 /api/me 也不含封存看板')

        # ⑦ /api/cards 不再下发封存看板的事项（先给 B1 放一张卡）
        stc, dc = api('/api/cards', 'POST', {'board_id': B1, 'card_name': PREFIX + '卡',
                                            'fields': {}}, token=tk_admin)
        cid = (dc or {}).get('card_id')
        stl, dl = api('/api/cards?board_id=' + urllib.parse.quote(B1, safe=''), token=tk_lead)
        ok(stl == 200 and not (dl.get('cards') or []) and not (dl.get('columns') or []),
           '⑦ 封存看板的卡片/板块不再下发（列表接口为空）')
        # 全局列表（不带 board_id）也不含该卡的板块名
        stg, dg = api('/api/cards?size=2000', token=tk_lead)
        names = {(c.get('card_name') or '') for c in (dg.get('cards') or [])}
        ok((PREFIX + '卡') not in names, '⑦-b 全局事项列表不含封存看板的事项')
        if cid:
            api('/api/cards/' + cid, 'DELETE', token=tk_admin)

        # ⑥ 看板管理视图：默认不含；include_archived=1 含且 archived=1
        std, dd = api('/api/boards', token=tk_admin)
        ok(std == 200 and B1 not in {b['board_id'] for b in dd.get('boards', [])},
           '⑥-a /api/boards 默认不含封存看板')
        sti, di = api('/api/boards?include_archived=1', token=tk_admin)
        row = next((b for b in di.get('boards', []) if b['board_id'] == B1), None)
        ok(sti == 200 and row and row.get('archived') == 1,
           '⑥-b /api/boards?include_archived=1 含封存看板且 archived=1')
        # 普通成员的看板管理视图也含（可见，但无权操作 —— 按钮由 arch_owner 显隐）
        sti2, di2 = api('/api/boards?include_archived=1', token=tk_member)
        row2 = next((b for b in di2.get('boards', []) if b['board_id'] == B1), None)
        ok(sti2 == 200 and row2 and row2.get('archived') == 1,
           '⑥-c 普通成员在看板管理视图可见封存看板（但无操作权）')

        # ⑨ 不存在的看板 404
        st9, _ = api('/api/boards/%s/archive' % urllib.parse.quote(PREFIX + '不存在', safe=''),
                     'POST', {'archived': True}, token=tk_lead)
        ok(st9 == 404, '⑨ 不存在的看板 404')

        # ② 架构负责人启用成功 → 可见性恢复
        st2, d2 = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                      {'archived': False}, token=tk_lead)
        ok(st2 == 200 and d2.get('archived') == 0 and board_arch(B1) == 0,
           '② 架构负责人启用成功（archived=0）')
        st, ids = me_board_ids(tk_member)
        ok(B1 in ids, '②-b 启用后普通成员 /api/me 恢复可见')

        # ⑩ 前端接线静态断言
        html = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        ok('async function bcArchive(bid,toArch)' in html
           and 'badge-archived' in html
           and "/api/boards?include_archived=1" in html
           and "'arch_owner': arch_owner" not in html   # 该串属后端，前端不应出现
           and 'ME.arch_owner' in html,
           '⑩ 前端接线：bcArchive/徽标/include_archived=1/arch_owner 显隐齐备')
        app_py = open(os.path.join(ROOT, 'src', 'app', 'app.py'), encoding='utf-8').read()
        ok("'arch_owner': arch_owner" in app_py and 'perm_check_arch_scope(username, OP_UPDATE'
           in app_py and 'board_archive' in app_py,
           '⑩-b 后端接线：arch_owner 下发 / 架构负责人校验 / 审计齐备')
    finally:
        cleanup()
        # 零残留自查（D5）
        c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
        n1 = c.execute("SELECT COUNT(*) FROM boards WHERE board_id LIKE ?", (PREFIX + '%',)).fetchone()[0]
        n2 = c.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (PREFIX + '%',)).fetchone()[0]
        n3 = c.execute("SELECT COUNT(*) FROM org_nodes WHERE name LIKE ?", (PREFIX + '%',)).fetchone()[0]
        c.close()
        ok(n1 == 0 and n2 == 0 and n3 == 0, '⑪ 夹具零残留（boards/users/org_nodes）')
    print('\n结果：通过 %d / 失败 %d' % (_n['ok'], _n['fail']))
    sys.exit(1 if _n['fail'] else 0)


if __name__ == '__main__':
    main()
