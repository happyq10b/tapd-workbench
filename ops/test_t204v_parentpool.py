# -*- coding: utf-8 -*-
"""T-204v（2026-11-17）选人层级约束「子事项 ⊆ 父事项名单」API 实测：
  ① 子事项新建：owner/cc ⊆ 父事项负责人+参与人（池外直接除名，响应 removed）
  ② 子事项编辑：原有人员放行（存量）、新增必须 ⊆ 父名单
  ③ 主事项编辑：仍按上级板块池（看板 ACL ∩ 部门池）过滤——层级不回退
    （⚠️ 用非管理员夹具账号 U1 断言：admin 触发 is_admin 豁免，测不出池过滤）
  ④ 复制子事项：副本 owner/cc ⊆ 目标主事项名单（copy 响应带 removed）
  ⑤ set_card_participants：子事项按父名单过滤 + 落库 ';' 分隔姓名
  ⑥ 行数守恒（deleted=0 口径）+ 夹具零残留（业务口径 deleted=0）
数据安全守则 §3.4：夹具前缀 __t204v，API 创建/清理（U1 token，admin 仅建看板），
try/finally 双保险 + 残留自查；除夹具行外零业务写库。
"""
import json, os, sqlite3, sys, urllib.request, urllib.error, urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
U1, U2, U3 = '__t204v_u1', '__t204v_u2', '__t204v_u3'
BS = chr(92)
PAT = '%' + BS + '_' + 't204v%'
PASSED = []
IDS = {}
CLEANED = [False]
TK_ADMIN = make_token('admin')
TK_U1 = ''          # setup 建号后签发（教训：make_token 必须在夹具建号之后）


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header('Authorization', 'Bearer ' + (token or TK_U1))
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


def get_card(cid, token=None):
    st, r = api('/api/cards?card_id=' + cid, token=token)
    return (r.get('cards') or [None])[0] if st == 200 else None


def setup():
    global TK_U1
    c = sqlite3.connect(DB)
    for u in (U1, U2, U3):
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                  (u, hash_pw('Xx12345678')))
    c.commit()
    c.close()
    TK_U1 = make_token(U1)
    # 看板（U1 无建板权 → admin 建）→ 看板 ACL：owner=u1 participants=u2（池={u1,u2}）
    st, r = api('/api/boards', 'POST', {'board_name': '__t204v 测试看板', 'dept': '核算部'}, token=TK_ADMIN)
    assert st == 200, f'夹具看板创建失败 {st} {r}'
    IDS['bid'] = r.get('board_id') or (r.get('board') or {}).get('board_id')
    # 看板 ACL 分两步：PUT /acl 只写 owner（participants 字段保留旧值，诊断实证）；
    # participants 走 PUT /participants 端点
    st, r = api('/api/boards/%s/acl' % IDS['bid'], 'PUT', {'owner': U1}, token=TK_ADMIN)
    assert st == 200, f'看板 ACL(owner) 失败 {st} {r}'
    st, r = api('/api/boards/%s/participants' % IDS['bid'], 'PUT',
                {'participants': [U2]}, token=TK_ADMIN)
    assert st == 200, f'看板 ACL(participants) 失败 {st} {r}'
    ok(not r.get('removed'), '看板 ACL 设置成功（池 = u1+u2，无剔除）')
    # 板块A：owner=u1 participants=u2
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': '__t204v板块A',
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026',
                'owner': U1, 'participants': U2})
    assert st == 200, f'夹具板块创建失败 {st} {r}'
    IDS['colKey'] = r.get('col_key') or (IDS['bid'] + '::' + '__t204v板块A')
    c = sqlite3.connect(DB)
    IDS['colId'] = c.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                             (IDS['colKey'],)).fetchone()[0]
    c.close()
    # 主事项 P：owner=u1 cc=u2（板块池内，应全保留；U1 板块负责人有指派权）
    st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': '__t204v父事项',
                'column_id': IDS['colId'],
                'fields': {'owner': U1 + ';外员X', 'cc': U2 + ';外员Y'}})
    assert st == 200, f'主事项创建失败 {st} {r}'
    IDS['pid'] = r['card_id']
    ok('外员X' in (r.get('removed') or []) and '外员Y' in (r.get('removed') or []),
       f'主事项新建：板块池外人员被剔除（removed={r.get("removed")}，#138 行为不回退）')
    p = get_card(IDS['pid'])
    ok(p and p['owner'] == U1 and p['cc'] == U2, f'主事项落库：owner={p["owner"]} cc={p["cc"]}')


def cleanup():
    if CLEANED[0]:
        return
    CLEANED[0] = True
    for cid in (IDS.get('p4id'), IDS.get('p3id'), IDS.get('copyid'), IDS.get('p2id'), IDS.get('sid2'), IDS.get('sid'), IDS.get('pid')):
        if cid:
            api('/api/cards/' + cid, 'DELETE', token=TK_ADMIN)
    if IDS.get('colKeyEmpty'):
        import urllib.parse
        api('/api/columns/' + urllib.parse.quote(IDS['colKeyEmpty'], safe=''), 'DELETE', token=TK_ADMIN)
    if IDS.get('colKey'):
        api('/api/columns/' + urllib.parse.quote(IDS['colKey'], safe=''), 'DELETE', token=TK_ADMIN)
    if IDS.get('bid'):
        api('/api/boards/' + IDS['bid'], 'DELETE', token=TK_ADMIN)
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM users WHERE username LIKE ? ESCAPE ?", (PAT, BS))
    c.commit()
    res = {}
    for t, col, cond in (('cards', 'card_name', 'AND deleted=0'),
                         ('boards', 'board_name', ''),
                         ('board_columns', 'col_key', ''),
                         ('users', 'username', ''),
                         ('messages', 'content', '')):
        res[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE ? {cond}",
                           (PAT, BS)).fetchone()[0]
    c.close()
    print('残留自查（业务口径）：', res, flush=True)


def base_counts():
    c = sqlite3.connect(DB)
    out = {}
    for t, col in (('cards', 'card_name'), ('boards', 'board_name'),
                   ('board_columns', 'col_key'), ('users', 'username')):
        extra = 'AND deleted=0' if t == 'cards' else ''
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} NOT LIKE ? ESCAPE ? {extra}",
                           (PAT, BS)).fetchone()[0]
    c.close()
    return out


def main():
    setup()
    base0 = base_counts()
    # ① 子事项新建：池内保留、池外除名（U1 = 父事项负责人，有指派权）
    st, r = api('/api/cards', 'POST', {'parent_id': IDS['pid'], 'board_id': '',
                'card_name': '__t204v子事项ok',
                'fields': {'owner': U1 + ';' + U2, 'cc': U2}})
    ok(st == 200 and not (r.get('removed') or []), f'① 子事项新建：父名单内人员全保留（removed={r.get("removed")}）')
    IDS['sid'] = r['card_id']
    s = get_card(IDS['sid'])
    ok(s and s['owner'] == U1 + ';' + U2 and s['cc'] == U2, f'① 子事项落库：owner={s["owner"]} cc={s["cc"]}')

    st, r = api('/api/cards', 'POST', {'parent_id': IDS['pid'], 'board_id': '',
                'card_name': '__t204v子事项bad',
                'fields': {'owner': U1 + ';外员P', 'cc': U2 + ';外员Q'}})
    IDS['sid2'] = r.get('card_id', '')
    ok(st == 200 and '外员P' in (r.get('removed') or []) and '外员Q' in (r.get('removed') or []),
       f'① 子事项新建：父名单外人员被剔除（removed={r.get("removed")}）')
    s2 = get_card(IDS['sid2']) if IDS['sid2'] else None
    ok(s2 and s2['owner'] == U1 and s2['cc'] == U2, f'① 子事项落库：owner={s2["owner"]} cc={s2["cc"]}')

    # ② 子事项编辑：存量放行 + 新增必须 ⊆ 父名单
    st, r = api('/api/cards/' + IDS['sid'], 'PUT',
                {'fields': {'owner': U1 + ';外员W', 'cc': U2}})
    ok(st == 200 and '外员W' in (r.get('removed') or []), f'② 编辑剔除池外新增（removed={r.get("removed")}）')
    s = get_card(IDS['sid'])
    ok(s and s['owner'] == U1 and s['cc'] == U2, f'② 存量 u1 放行、新增外员W 除名：owner={s["owner"]}')
    st, r = api('/api/cards/' + IDS['sid'], 'PUT',
                {'fields': {'owner': U1 + ';' + U2, 'cc': U2}})
    ok(st == 200 and not (r.get('removed') or []), f'② 新增 u2（父名单内）保留（removed={r.get("removed")}）')
    s = get_card(IDS['sid'])
    ok(s and s['owner'] == U1 + ';' + U2, f'② 落库：owner={s["owner"]}')

    # ③ 主事项仍按板块池（不回退）：独立卡 owner=U3（看板池={u1,u2} 外）→ 剔除
    st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': '__t204v池外卡',
                'column_id': IDS['colId'], 'fields': {'owner': U3}})
    IDS['p2id'] = r.get('card_id', '')
    ok(st == 200 and U3 in (r.get('removed') or []), f'③ 主事项按板块池剔除 {U3}（removed={r.get("removed")}）')
    p2 = get_card(IDS['p2id']) if IDS['p2id'] else None
    ok(p2 is not None and (p2['owner'] or '') == '', f'③ 池外卡落库 owner=空（实际：{p2["owner"] if p2 else None}）')

    # ③b 板块空名单 = 完全限制（#140 用户报告场景）：空板块下建主事项 owner=U1 → 剔除
    st, r = api('/api/columns', 'POST', {'board_id': IDS['bid'], 'column_name': '__t204v空板块',
                'created_at': '2026-11-17', 'nature': '日常', 'year': '2026'})
    IDS['colKeyEmpty'] = r.get('col_key') or (IDS['bid'] + '::' + '__t204v空板块')
    c = sqlite3.connect(DB)
    IDS['colIdEmpty'] = c.execute('SELECT column_id FROM board_columns WHERE col_key=?',
                                  (IDS['colKeyEmpty'],)).fetchone()[0]
    c.close()
    st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': '__t204v空板块卡',
                'column_id': IDS['colIdEmpty'], 'fields': {'owner': U1}})
    IDS['p3id'] = r.get('card_id', '')
    ok(st == 200 and U1 in (r.get('removed') or []),
       f'③b 空板块建卡 owner 被剔除（removed={r.get("removed")}——板块名单空=完全限制，不回退看板池）')
    p3 = get_card(IDS['p3id']) if IDS['p3id'] else None
    ok(p3 is not None and (p3['owner'] or '') == '', f'③b 空板块卡落库 owner=空（实际：{p3["owner"] if p3 else None}）')
    # ③c column_name 兜底：不带 column_id、只带板块名 → 同样按空板块池限制
    st, r = api('/api/cards', 'POST', {'board_id': IDS['bid'], 'card_name': '__t204v按名兜底卡',
                'column_id': '', 'fields': {'owner': U1, 'column_name': '__t204v空板块'}})
    IDS['p4id'] = r.get('card_id', '')
    ok(st == 200 and U1 in (r.get('removed') or []),
       f'③c 仅传板块名（无 column_id）同样受板块池限制（removed={r.get("removed")}）')

    # ④ 复制子事项：SQL 造存量池外 owner（夹具行内），再复制 → 副本被父名单过滤
    c = sqlite3.connect(DB)
    c.execute("UPDATE cards SET owner=? WHERE card_id=?", (U1 + ';外员C', IDS['sid']))
    c.commit()
    c.close()
    st, r = api('/api/cards/copy', 'POST', {'card_id': IDS['sid'], 'board_id': IDS['bid'],
                'column_id': IDS['colId'], 'parent_id': IDS['pid'], 'card_name': '__t204v子事项副本'})
    ok(st == 200 and '外员C' in (r.get('removed') or []), f'④ 复制子事项：副本剔除父名单外人员（removed={r.get("removed")}）')
    IDS['copyid'] = r.get('card_id', '')
    cp = get_card(IDS['copyid']) if IDS['copyid'] else None
    ok(cp and cp['owner'] == U1, f'④ 副本落库：owner={cp["owner"] if cp else None}')

    # ⑤ set_card_participants：子事项按父名单过滤 + 落库 ';' 分隔姓名
    st, r = api('/api/cards/%s/participants' % IDS['sid'], 'PUT',
                {'participants': '外员D,' + U2})
    ok(st == 200 and '外员D' in (r.get('removed') or []),
       f'⑤ 参与人端点（st={st}，resp={json.dumps(r, ensure_ascii=False)[:200]}）剔除池外')
    s = get_card(IDS['sid'])
    ok(s and s['cc'] == U2, f'⑤ 落库 cc={s["cc"] if s else None}（; 分隔姓名）')

    # ⑥ 行数守恒（deleted=0 口径）
    base1 = base_counts()
    ok(base0 == base1, f'⑥ 行数守恒（非夹具活卡行）：{base0} → {base1}')


if __name__ == '__main__':
    try:
        main()
    finally:
        cleanup()
    print(f'\n=== {sum(PASSED)}/{len(PASSED)} passed ===', flush=True)
    sys.exit(0 if all(PASSED) else 1)
