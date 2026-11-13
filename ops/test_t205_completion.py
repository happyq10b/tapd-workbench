# -*- coding: utf-8 -*-
"""T-205（2026-11-13）板块「完成情况」按体系来（用户裁决：不搞特殊）：
  修复前：仅板块负责人本人（board_columns.owner 精确相等）或管理员可设置 —— 上级被 403；
  修复后：跟随板块编辑权限 = 板块负责人及以上（入口 perm_check OP_UPDATE LV_COLUMN_OWNER），
          看板负责人/架构负责人经继承放行。

断言矩阵：
  ① 板块负责人本人 → 200
  ② 看板负责人（非板块负责人）→ 200   ← 本修复核心（修复前 403）
  ③ 无任何身份的 editor → 403（门槛未放宽）
  ④ 板块参与人 → 403（参与人级不够）
  ⑤ 设「已完成」前置条件仍在：板块下有未完成事项 → 400
  ⑥ 管理员 → 200

夹具纪律：__t205_ 前缀命名空间；atexit 清理；结束跑零残留自查。
"""
import atexit
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token, hash_pw

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
PASSED = []


def ok(cond, msg):
    PASSED.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + msg, flush=True)


def api(path, method='GET', data=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


# ---------- 夹具（公共看板：不挂 board_config → 全员可见，免架构归属） ----------
conn = sqlite3.connect(DB)
conn.execute("INSERT OR IGNORE INTO boards (board_id, board_name, sort) VALUES ('__t205_B','__t205 测试看板',9300)")
for acct in ('__t205_bo', '__t205_co', '__t205_pl', '__t205_pt'):
    conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,'editor')",
                 (acct, hash_pw('Xx12345678')))
conn.commit()
conn.close()

TK_ADMIN = make_token('admin')
TK_BO = make_token('__t205_bo')   # 看板负责人（非板块负责人）
TK_CO = make_token('__t205_co')   # 板块负责人
TK_PL = make_token('__t205_pl')   # 无身份 editor
TK_PT = make_token('__t205_pt')   # 板块参与人

COL_KEY = '__t205_B::__t205板块'
CLEANED = {'col': False}


def cleanup():
    if not CLEANED['col']:
        try:
            api('/api/columns/' + COL_KEY, 'DELETE', token=TK_ADMIN)
        except Exception:
            pass
        CLEANED['col'] = True
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM column_comments WHERE col_key LIKE '%__t205板块%'")
    c.execute("DELETE FROM column_todos WHERE col_key LIKE '%__t205板块%'")
    c.execute("DELETE FROM column_actions WHERE col_key LIKE '%__t205板块%'")
    c.execute("DELETE FROM board_columns WHERE board_id='__t205_B'")
    c.execute("DELETE FROM cards WHERE board_id='__t205_B'")
    c.execute("DELETE FROM board_config WHERE board_id='__t205_B'")
    c.execute("DELETE FROM boards WHERE board_id='__t205_B'")
    c.execute("DELETE FROM messages WHERE receiver LIKE '__t205_%'")
    c.execute("DELETE FROM users WHERE username LIKE '__t205_%'")
    c.commit()
    c.close()


atexit.register(cleanup)


def residue_check():
    c = sqlite3.connect(DB)
    pairs = [
        ("boards", "board_id LIKE '__t205_%'"),
        ("board_columns", "board_id LIKE '__t205_%'"),
        ("cards", "board_id LIKE '__t205_%'"),
        ("users", "username LIKE '__t205_%'"),
        ("column_comments", "col_key LIKE '%__t205板块%'"),
        ("column_todos", "col_key LIKE '%__t205板块%'"),
        ("column_actions", "col_key LIKE '%__t205板块%'"),
    ]
    left = [(t, c.execute(f"SELECT COUNT(*) FROM {t} WHERE {w}").fetchone()[0]) for t, w in pairs]
    c.close()
    return [(t, n) for t, n in left if n]


def main():
    # 建板块（admin）
    st, r = api('/api/columns', 'PUT', {'col_key': '', 'board_id': '__t205_B',
                'column_name': '__t205板块', 'created_at': '2026-11-13',
                'year': '2026', 'nature': '日常'}, TK_ADMIN)
    ok(st == 200, f'夹具板块创建 → {st}')
    # 配置身份：板块负责人 = co；板块参与人 = pt（走 API，与真实路径一致）
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'owner': '__t205_co',
                'participants': '__t205_pt'}, TK_ADMIN)
    ok(st == 200, f'配置板块负责人/参与人 → {st}')
    # 看板负责人 = bo（走 API：min_level=LV_ARCH_OWNER，管理员放行）
    st, _ = api('/api/boards/__t205_B/acl', 'PUT', {'owner': '__t205_bo', 'participants': ''}, TK_ADMIN)
    ok(st == 200, f'配置看板负责人 → {st}')
    # 夹具事项（供⑤的 done 前置条件）：挂到板块真实 column_id 下，保持未完成
    _col = sqlite3.connect(DB).execute(
        "SELECT column_id FROM board_columns WHERE col_key=?", (COL_KEY,)).fetchone()
    _col_id = _col[0] if _col else ''
    st, _ = api('/api/cards', 'POST', {'board_id': '__t205_B', 'column_id': _col_id,
                'card_name': '__t205 未完成事项', 'fields': {}}, TK_ADMIN)
    ok(st == 200, f'夹具未完成事项 → {st}')

    print('【① 板块负责人本人】', flush=True)
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'progressing'}, TK_CO)
    ok(st == 200, f'① 板块负责人设 completion → {st}（预期 200）')

    print('【② 看板负责人（非板块负责人）—— 本修复核心】', flush=True)
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'open'}, TK_BO)
    ok(st == 200, f'② 看板负责人设 completion → {st}（修复前 403，预期 200）')

    print('【③ 无身份 editor】', flush=True)
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'progressing'}, TK_PL)
    ok(st == 403, f'③ 无身份 editor 设 completion → {st}（预期 403，门槛未放宽）')

    print('【④ 板块参与人】', flush=True)
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'open'}, TK_PT)
    ok(st == 403, f'④ 板块参与人设 completion → {st}（预期 403，参与人级不够）')

    print('【⑤ done 前置条件仍在】', flush=True)
    st, r = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'done'}, TK_CO)
    ok(st == 400, f'⑤ 板块下有未完成事项时设「已完成」→ {st}（预期 400：{ (r or {}).get("detail","")[:40] }）')
    # 造完成事项后再设 done → 200
    st, r = api('/api/cards?board_id=__t205_B&size=50', 'GET', token=TK_ADMIN)
    cid = next((c['card_id'] for c in (r.get('cards') or []) if c.get('card_name') == '__t205 未完成事项'), None)
    ok(cid is not None, '定位夹具事项 card_id')
    if cid:
        st, _ = api('/api/cards/' + cid, 'PUT', {'fields': {'status': 'done'}}, TK_ADMIN)
        ok(st == 200, f'夹具事项置完成 → {st}')
        st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'done'}, TK_CO)
        ok(st == 200, f'⑤ 全部完成后设「已完成」→ {st}（预期 200）')

    print('【⑥ 管理员】', flush=True)
    st, _ = api('/api/columns', 'PUT', {'col_key': COL_KEY, 'completion': 'open'}, TK_ADMIN)
    ok(st == 200, f'⑥ 管理员设 completion → {st}（预期 200）')

    print(flush=True)
    print(f'=== 结果：{sum(PASSED)}/{len(PASSED)} 通过 ===', flush=True)
    return 0 if all(PASSED) else 1


if __name__ == '__main__':
    try:
        rc = main()
    finally:
        cleanup()
        print('finally 清理完成，残留：', residue_check() or '无', flush=True)
    sys.exit(rc)
