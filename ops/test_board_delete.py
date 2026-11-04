# -*- coding: utf- -*-
"""看板管理页脚改造（2026-11-04）的后端测试。

需求：
  1) 去掉「应用到已选 N 个看板」→ POST /api/board-config/bulk 下线
  2) 「删除看板配置」→「删除看板本身」→ DELETE /api/boards/{id}
     + POST /api/boards/bulk-delete（连同板块/事项/子事项/配置一起清掉）
  3) 「保存负责人」+「保存配置」合并 → 前端单按钮，后端能力位不变

覆盖：
  A. 批量应用接口已下线（404）
  B. 删除看板 → 板块/事项/配置/绑定全部清除；事项为软删（可经备份找回）
  C. 权限：看板负责人可删自己的看板；只读账号 → 403
  D. 批量删除 → 多看板一起清掉
  E. can_delete 能力位与删除接口口径一致

⚠️ 夹具纪律（2026-11-02 立规）：
  · 专属前缀 __bd_ 命名空间；try/finally 保证清理（删全所有相关表）
  · 断言不得硬编码全局基线数字 —— 一律取基线后比对相对差
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw, make_token  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'app.db')
PREFIX = '__bd_'
U_ADMIN = PREFIX + 'admin'
U_OWNER = PREFIX + 'owner'      # 看板负责人
U_VIEWER = PREFIX + 'viewer'    # 只读
PWD = 'At159357'
now = '2026-11-04 22:00:00'

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  X ') + msg)


def http(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {'Content-Type': 'application/json'}
    if token:
        h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        txt = r.read()
        return r.status, json.loads(txt.decode() if txt else '{}')
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt.decode() if txt else '{}')
        except Exception:
            return e.code, {'detail': txt.decode()[:300]}


def q(sql, params=()):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


def ex(sql, params=()):
    c = sqlite3.connect(DB)
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.rowcount
    finally:
        c.close()


BIDS = []          # 本轮创建的看板 id
CARDS = []         # 本轮创建的事项 id


def setup():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    for a in (U_ADMIN, U_OWNER, U_VIEWER):
        c.execute('DELETE FROM users WHERE username=?', (a,))
        c.execute('DELETE FROM team_members WHERE account=?', (a,))
        c.execute('INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,?,?,?)',
                  (PREFIX + a, '', a, now))
        c.execute('INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)'
                  ' VALUES (?,?,?,?,?,?)',
                  (a, hash_pw(PWD), 'admin' if a == U_ADMIN else ('viewer' if a == U_VIEWER else 'editor'),
                   '*', '*', now))
    stamp = str(int(time.time() * 1000))
    # 两个夹具看板：b1（owner 负责）、b2（也挂 owner，便于批量删除）
    for i in (1, 2):
        bid = PREFIX + 'b%d_%s' % (i, stamp[-6:])
        BIDS.append(bid)
        c.execute('INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)'
                  ' VALUES (?,?,?,?,?,?,?)', (bid, PREFIX + '看板%d' % i, '', U_OWNER, '', 0, now))
        c.execute('INSERT INTO board_config (board_id,dept,dept_node_id,attr,status,remark,created_at)'
                  ' VALUES (?,?,?,?,?,?,?)', (bid, '核算部', 0, '日常', '启用', PREFIX + '备注', now))
        c.execute('INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,'
                  'nature,year,pinned,owner,participants,completion)'
                  ' VALUES (?,?,?,?,?,?,?,?,0,?,?,?)',
                  (bid + '::' + PREFIX + 'A', PREFIX + 'col%d' % i, bid, PREFIX + 'A',
                   now, U_OWNER, '日常', '2026', U_OWNER, '', 'open'))
        cid = PREFIX + 'c%d_%s' % (i, stamp[-6:])
        CARDS.append(cid)
        c.execute('INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,'
                  'status_name,creator,owner,cc,begin,due,created,modified,description,week_no,deleted,parent_id)'
                  ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)',
                  (cid, bid, PREFIX + '看板%d' % i, PREFIX + 'col%d' % i, PREFIX + 'A',
                   PREFIX + '事项%d' % i, 'open', '未完成', U_OWNER, U_OWNER, '', '2026-08-06', '2026-08-14',
                   now, now, PREFIX + '描述', '2026年第45周', ''))
        c.execute('INSERT INTO card_subtasks (card_id,title,done,sort,created_by,parent_id,created_at)'
                  ' VALUES (?,?,0,0,?,0,?)', (cid, PREFIX + '子项', U_OWNER, now))
    c.commit()
    c.close()


def cleanup():
    for bid in BIDS:
        for sql in ('DELETE FROM card_subtasks WHERE card_id IN (SELECT card_id FROM cards WHERE board_id=?)',
                    'DELETE FROM cards WHERE board_id=?',
                    'DELETE FROM board_columns WHERE board_id=?',
                    'DELETE FROM board_config WHERE board_id=?',
                    'DELETE FROM boards WHERE board_id=?'):
            ex(sql, (bid,))
    for a in (U_ADMIN, U_OWNER, U_VIEWER):
        ex('DELETE FROM users WHERE username=?', (a,))
        ex('DELETE FROM team_members WHERE account=?', (a,))
    ex("DELETE FROM audit_logs WHERE target LIKE ?", (PREFIX + '%',))


def main():
    setup()
    tk_admin = make_token(U_ADMIN)
    tk_owner = make_token(U_OWNER)
    tk_viewer = make_token(U_VIEWER)
    try:
        # ── A. 批量应用接口已下线 ──
        print('\n【A】「应用到已选 N 个看板」接口下线')
        # 注意：路径 /api/board-config/bulk 仍会被 /api/board-config/{cid} 的路由匹配到
        #   → POST 返回 405（方法不允许），而非 404。两种都算「接口已下线」。
        code, _ = http('/api/board-config/bulk', 'POST',
                       {'board_ids': BIDS, 'dept': '核算部', 'attr': '日常', 'status': '启用'},
                       token=tk_admin)
        ok(code in (404, 405),
           'POST /api/board-config/bulk 已下线（实际 %s）' % code)
        code, _ = http('/api/board-config/bulk-delete', 'POST', {'board_ids': BIDS}, token=tk_admin)
        ok(code in (404, 405),
           'POST /api/board-config/bulk-delete 已下线（实际 %s）' % code)
        # 关键：批量应用**没有生效** —— 夹具看板的归属部门未被批量改写
        rows = q('SELECT dept FROM board_config WHERE board_id=?', (BIDS[0],))
        ok(len(rows) == 1 and rows[0]['dept'] == '核算部',
           '批量应用未生效：夹具看板归属部门未被改写')

        # ── E. 能力位口径 ──
        print('\n【E】can_delete 能力位与删除接口同口径')
        code, r = http('/api/boards', token=tk_owner)
        mine = [b for b in r.get('boards', []) if b['board_id'] in BIDS]
        ok(len(mine) == 2, 'owner 能在 /api/boards 看到自己的 2 个夹具看板（实际 %d）' % len(mine))
        ok(all(b['can_delete'] for b in mine),
           '看板负责人 can_delete=true（可删看板本身）')
        code, r = http('/api/boards', token=tk_viewer)
        vmine = [b for b in r.get('boards', []) if b['board_id'] in BIDS]
        ok(all((not b['can_delete']) for b in vmine),
           '只读账号 can_delete=false')

        # ── C. 越权拦截（放在删除前，先验证权限门禁）──
        print('\n【C】只读账号删除看板 → 403')
        code, r = http('/api/boards/%s' % BIDS[0], 'DELETE', token=tk_viewer)
        ok(code == 403, '只读账号 DELETE /api/boards/{id} → 403（实际 %s）' % code)
        ok('PERMISSION_DENIED' in json.dumps(r, ensure_ascii=False),
           '返回统一越权错误体（PermError）')
        ok(q('SELECT COUNT(*) n FROM boards WHERE board_id=?', (BIDS[0],))[0]['n'] == 1,
           '越权删除未生效：看板仍在')

        # ── B. 删除看板本身 ──
        print('\n【B】删除看板本身 → 板块/事项/子事项/配置全清')
        b1 = BIDS[0]
        code, r = http('/api/boards/%s' % b1, 'DELETE', token=tk_owner)
        ok(code == 200, 'owner 删除自己的看板 → 200（实际 %s）' % code)
        ok(r.get('deleted_cards') == 1 and r.get('deleted_columns') == 1,
           '回显删了 1 个板块 / 1 条事项（实际 %s / %s）'
           % (r.get('deleted_columns'), r.get('deleted_cards')))
        ok(q('SELECT COUNT(*) n FROM boards WHERE board_id=?', (b1,))[0]['n'] == 0,
           'boards 表中该看板已删除')
        ok(q('SELECT COUNT(*) n FROM board_config WHERE board_id=?', (b1,))[0]['n'] == 0,
           'board_config 配置已删除')
        ok(q('SELECT COUNT(*) n FROM board_columns WHERE board_id=?', (b1,))[0]['n'] == 0,
           'board_columns 板块已删除')
        # 事项为**软删**（deleted=1）—— 可经全局备份恢复找回
        c1 = q('SELECT deleted FROM cards WHERE card_id=?', (CARDS[0],))
        ok(len(c1) == 1 and c1[0]['deleted'] == 1,
           '事项被软删（deleted=1，备份可找回）')
        ok(q('SELECT COUNT(*) n FROM card_subtasks WHERE card_id=?', (CARDS[0],))[0]['n'] == 0,
           '子事项清单已随事项清除')
        # 列表口径：不再出现
        code, r = http('/api/boards', token=tk_owner)
        ok(not any(b['board_id'] == b1 for b in r.get('boards', [])),
           '删除后该看板不再出现在 /api/boards 列表')
        code, r = http('/api/cards?board_id=%s' % b1, token=tk_owner)
        ok(not r.get('cards'), '删除后该看板的事项接口返回空')

        # ── D. 批量删除 ──
        print('\n【D】批量删除看板（管理员）')
        b2 = BIDS[1]
        code, r = http('/api/boards/bulk-delete', 'POST', {'board_ids': [b2]}, token=tk_admin)
        ok(code == 200, 'POST /api/boards/bulk-delete → 200（实际 %s）' % code)
        ok(r.get('deleted') == 1, '回显删除 1 个看板（实际 %s）' % r.get('deleted'))
        ok(q('SELECT COUNT(*) n FROM boards WHERE board_id=?', (b2,))[0]['n'] == 0,
           '批量删除后 boards 表中该看板已删除')
        ok(q('SELECT COUNT(*) n FROM board_config WHERE board_id=?', (b2,))[0]['n'] == 0,
           '批量删除后配置已清除')
        # 批量接口仅管理员
        code, _ = http('/api/boards/bulk-delete', 'POST', {'board_ids': [b2]}, token=tk_owner)
        ok(code == 403, '非管理员调批量删除 → 403（实际 %s）' % code)
    finally:
        cleanup()

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('  FAILED: ' + f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
