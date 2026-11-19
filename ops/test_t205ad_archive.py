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
    # 看板 B1：owner=member（看板负责人 ≠ 架构负责人），归属 D1（→ lead 可封存）；
    # B2：无负责人、**无归属部门**（→ 仅管理员可封存，fail-closed 用例）
    for bid, name, owner in ((B1, PREFIX + '看板一', MEMBER), (B2, PREFIX + '看板二', '')):
        c.execute("INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)"
                  " VALUES (?,?,?,?, '',0,?)", (bid, name, '', owner, now))
    c.execute("INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,created_at)"
              " VALUES (?,?,?,?, '启用',?)", (B1, PREFIX + 'D1', 9101, '日常', now))
    # 两个测试账号（editor；allowed_boards='*' 不额外收窄）
    for acct, role in ((LEAD, 'dept_head'), (MEMBER, 'member')):
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)", (acct, hash_pw('At159357'), now))
        c.execute("INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,'',?,?)",
                  (PREFIX + acct, acct, now))
        # lead 任命 D1 部门长（dept_head 岗位）→ 负责范围含 D1 绑定的看板 B1（可见性层
        # _org_leader_nodes 只认岗位任命，不认 org_nodes.owner 显式配置 —— 口径分裂
        # 已登记 HANDOFF §五 T-016）；member 任命普通成员 → 可见性同层，但非架构负责人
        mid = c.execute("SELECT id FROM team_members WHERE account=?", (acct,)).fetchone()[0]
        c.execute("INSERT INTO org_appointments (node_id,member_id,role_key,is_primary,created_at)"
                  " VALUES (9101,?,?,0,?)", (mid, role, now))
    c.commit()
    c.close()


def board_arch(bid):
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    r = c.execute('SELECT archived FROM boards WHERE board_id=?', (bid,)).fetchone()
    c.close()
    return (r[0] if r else None)


def board_arch_full(bid):
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
    c.row_factory = sqlite3.Row
    r = c.execute('SELECT board_id, archived, archived_at, archived_by FROM boards WHERE board_id=?', (bid,)).fetchone()
    c.close()
    return dict(r) if r else None


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

        # ⑯ 封存看板的配置编辑一并锁定（用户需求：启用后才可再编辑）
        _c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
        cfgid = _c.execute('SELECT id FROM board_config WHERE board_id=?', (B1,)).fetchone()[0]
        _c.close()
        st16, d16 = api('/api/board-config/%d' % cfgid, 'PUT',
                        {'board_id': B1, 'dept': PREFIX + 'D1', 'dept_node_id': 9101,
                         'attr': '专项', 'status': '启用', 'remark': '尝试编辑'}, token=tk_admin)
        ok(st16 == 403 and '已封存' in json.dumps(d16, ensure_ascii=False),
           '⑯-a 封存看板保存配置被拦 403（管理员同样受限）：%s'
           % json.dumps(d16, ensure_ascii=False)[:60])
        st16b, d16b = api('/api/boards/%s/acl' % urllib.parse.quote(B1, safe=''), 'PUT',
                          {'owner': MEMBER}, token=tk_admin)
        ok(st16b == 403, '⑯-b 封存看板负责人/参与人变更被拦 403')
        std2, dd2 = api('/api/boards?include_archived=1', token=tk_admin)
        r_e = next((b for b in dd2.get('boards', []) if b['board_id'] == B1), {})
        ok(r_e.get('can_edit') is False and r_e.get('can_assign_owner') is False,
           '⑯-c 封存看板 can_edit/can_assign_owner 能力位=False')
        html3 = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        ok('看板已封存：配置与负责人均不可编辑' in html3
           and 'bcSelect(bid)' in html3,
           '⑯-d 前端接线：面板锁定提示 + bcArchive 后重绘面板')

        # ⑰ 封存元数据（#205ad-bis-3）：封存写入时间与操作人、启用清空、接口下发
        row17 = board_arch_full(B1)
        ok(row17 and row17['archived'] == 1 and row17['archived_at'] and row17['archived_by'] == LEAD,
           '⑰-a 封存写入 archived_at（%s）与 archived_by（%s）'
           % (row17.get('archived_at'), row17.get('archived_by')))
        st17, d17 = api('/api/boards?include_archived=1', token=tk_lead)
        r17 = next((b for b in d17.get('boards', []) if b['board_id'] == B1), {})
        ok(st17 == 200 and r17.get('archived_at') == row17['archived_at']
           and r17.get('archived_by') == LEAD,
           '⑰-b /api/boards 下发封存元数据')
        st17b, _ = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                       {'archived': False}, token=tk_lead)
        row17b = board_arch_full(B1)
        ok(st17b == 200 and row17b['archived'] == 0 and not row17b['archived_at']
           and not row17b['archived_by'],
           '⑰-c 启用后元数据清空（历史查审计日志）')
        api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
            {'archived': True}, token=tk_lead)   # 恢复封存态供后续用例（⑥ 等）

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

        # ⑫ 范围外架构负责人被拦：B1 归属 D1（lead 负责）；再造 D2（owner=lead2，
        #    负责范围不含 D1）→ lead2 封存 B1 应 403（E_CROSS_SCOPE）
        c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
        c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
                  " VALUES (9104,?,'dept',0,0,'','',0,?)", (PREFIX + 'D2', '2026-11-19 09:00:00'))
        c.execute("UPDATE org_nodes SET owner=? WHERE id=9104", (PREFIX + 'lead2',))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)",
                  (PREFIX + 'lead2', hash_pw('At159357'), '2026-11-19 09:00:00'))
        c.commit()
        c.close()
        tk_lead2 = make_token(PREFIX + 'lead2')
        st12, d12 = api('/api/boards/%s/archive' % urllib.parse.quote(B1, safe=''), 'POST',
                        {'archived': True}, token=tk_lead2)
        ok(st12 == 403 and board_arch(B1) == 0,
           '⑫ 范围外架构负责人（D2.owner）封存归属 D1 的看板被拦 403：%s'
           % json.dumps(d12, ensure_ascii=False)[:70])

        # ⑬ 无归属部门的看板：架构负责人被拦（fail-closed），管理员可封存
        st13, d13 = api('/api/boards/%s/archive' % urllib.parse.quote(B2, safe=''), 'POST',
                        {'archived': True}, token=tk_lead)
        ok(st13 == 403 and '归属部门' in json.dumps(d13, ensure_ascii=False),
           '⑬-a 架构负责人封存无归属看板被拦（fail-closed）：%s'
           % json.dumps(d13, ensure_ascii=False)[:70])
        st13b, d13b = api('/api/boards/%s/archive' % urllib.parse.quote(B2, safe=''), 'POST',
                          {'archived': True}, token=tk_admin)
        ok(st13b == 200 and board_arch(B2) == 1, '⑬-b 管理员可封存无归属看板')
        st13c, _ = api('/api/boards/%s/archive' % urllib.parse.quote(B2, safe=''), 'POST',
                       {'archived': False}, token=tk_admin)
        ok(st13c == 200 and board_arch(B2) == 0, '⑬-c 管理员启用恢复（清理状态）')

        # ⑥-d/e can_archive 能力位（看板级，前端按钮显隐依据）
        stc2, dc2 = api('/api/boards?include_archived=1', token=tk_lead)
        r_b1 = next((b for b in dc2.get('boards', []) if b['board_id'] == B1), {})
        r_b2 = next((b for b in dc2.get('boards', []) if b['board_id'] == B2), {})
        ok(r_b1.get('can_archive') is True and r_b2.get('can_archive') is False,
           '⑥-d can_archive：归属部门负责人 True / 无归属看板 False')
        stc3, dc3 = api('/api/boards?include_archived=1', token=tk_lead2)
        r_b1x = next((b for b in dc3.get('boards', []) if b['board_id'] == B1), None)
        ok(r_b1x is None or r_b1x.get('can_archive') is False,
           '⑥-e can_archive：范围外架构负责人 False（或该看板不在其管理列表中）')

        # ⑭ 唯一归属（用户追加限制：一个看板只能归属一个部门架构）：
        #    DB 层 UNIQUE(board_id) + 应用层 409 —— 对 B1 重复登记配置应被拒
        st14, d14 = api('/api/board-config', 'POST',
                        {'board_id': B1, 'dept': PREFIX + 'D1', 'dept_node_id': 9101,
                         'attr': '专项', 'status': '启用'}, token=tk_admin)
        ok(st14 == 409, '⑭ 唯一归属：对已配置看板重复登记被拒 409（%s）'
           % json.dumps(d14, ensure_ascii=False)[:60])

        # ⑮ 新建看板口径（#205ad-cis）：组长（group_leader）无权，部门长（dept_head）有权
        c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'))
        c.execute("INSERT INTO org_nodes (id,name,node_type,parent_id,wg_id,is_anchor,function,sort,created_at)"
                  " VALUES (9105,?,'group',9101,0,'','',0,?)", (PREFIX + 'G1', '2026-11-19 09:00:00'))
        c.execute("UPDATE org_nodes SET owner=? WHERE id=9105", (PREFIX + 'gl',))
        c.execute("INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)"
                  " VALUES (?,?,'editor','*','*',?)",
                  (PREFIX + 'gl', hash_pw('At159357'), '2026-11-19 09:00:00'))
        c.commit()
        c.close()
        tk_gl = make_token(PREFIX + 'gl')
        meg = api('/api/me', token=tk_gl)[1]
        # arch_owner 对组长可能仍为 True（岗位/owner 口径），但按钮显隐已全部
        # 走看板级 can_archive / can_create_board —— 组长无任何操作入口
        ok(meg.get('can_create_board') is False,
           '⑮-a 组长 can_create_board=False（成本组林姝言同款口径：无新建看板入口）')
        st15, d15 = api('/api/boards', 'POST',
                        {'board_name': PREFIX + '组长建板', 'workspace_id': ''}, token=tk_gl)
        ok(st15 == 403 and '部门负责人及以上' in json.dumps(d15, ensure_ascii=False),
           '⑮-b 组长新建看板被拦 403（%s）' % json.dumps(d15, ensure_ascii=False)[:60])
        mel = api('/api/me', token=tk_lead)[1]
        ok(mel.get('can_create_board') is True, '⑮-c 部门长（dept_head）can_create_board=True')
        # 前端接线：两处按钮用 can_create_board
        html2 = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        ok('ME.can_create_board' in html2 and html2.count('can_create_board') >= 3,
           '⑮-d 前端两处「＋ 新建看板」显隐已接 can_create_board')

        # ⑩ 前端接线静态断言
        html = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        ok('async function bcArchive(bid,toArch)' in html
           and 'badge-archived' in html
           and "/api/boards?include_archived=1" in html
           and 'b.can_archive' in html
           and 'statusPills' not in html,
           '⑩ 前端接线：bcArchive/徽标/include_archived=1/can_archive 显隐/状态胶囊已移除')
        app_py = open(os.path.join(ROOT, 'src', 'app', 'app.py'), encoding='utf-8').read()
        ok("'arch_owner': arch_owner" in app_py and 'node_id=node_id' in app_py
           and 'board_archive' in app_py and "'can_archive'" in app_py,
           '⑩-b 后端接线：arch_owner 下发 / 归属部门收窄校验 / 审计 / can_archive 齐备')
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
