# -*- coding: utf-8 -*-
"""#101 看板拖拽排序（个人级）API 实测"""
import json, os, sys, urllib.request, urllib.error, sqlite3

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token

BASE = 'http://127.0.0.1:8100'
RES = []


def ok(cond, name):
    RES.append((bool(cond), name))
    print(('  PASS ' if cond else '  ✗ FAIL ') + name)


def req(tok, path, method='GET', body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + tok})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=15).read() or '{}')
    except urllib.error.HTTPError as e:
        return {'__http__': e.code, 'detail': (e.read().decode() or '')[:120]}


admin_tok = make_token('admin')
zs_tok = make_token('dsy')   # admin 角色但非超管账号 → 走个人布局分支

# ---------- A：默认布局（超管拖拽 = boards.sort） ----------
a0 = [b['board_id'] for b in req(admin_tok, '/api/boards')['boards']]
a0_names = [b['board_name'] for b in req(admin_tok, '/api/boards')['boards']]
print('【A】超管拖拽 → 默认布局')
ok(len(a0) >= 3, '看板数足够（%d 个）' % len(a0))

# 把第 1 个移到最后
new_order = a0[1:] + [a0[0]]
r = req(admin_tok, '/api/boards/reorder', 'POST', {'order': new_order})
ok(r.get('ok') and r.get('scope') == 'default', '超管上报全量顺序 → scope=default')
a1 = [b['board_id'] for b in req(admin_tok, '/api/boards')['boards']]
ok(a1 == new_order, '默认布局已持久化（首板移至末位）')

# boards.sort 落库验证
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
sorts = {r[0]: r[1] for r in con.execute('SELECT board_id, sort FROM boards')}
con.close()
ok(sorts[a0[0]] == max(sorts[b] for b in a0), 'boards.sort 落库正确（超管=默认布局载体）')

# ---------- B：个人布局固化（dsy） ----------
zs_before = [b['board_id'] for b in req(zs_tok, '/api/boards')['boards']]
print('【B】普通用户拖拽 → 个人布局（dsy，可见 %d 个看板）' % len(zs_before))
if len(zs_before) >= 2:
    zs_new = list(reversed(zs_before))
    r = req(zs_tok, '/api/boards/reorder', 'POST', {'order': zs_new})
    ok(r.get('ok') and r.get('scope') == 'personal', '普通用户上报 → scope=personal')
    zs_after = [b['board_id'] for b in req(zs_tok, '/api/boards')['boards']]
    ok(zs_after == zs_new, 'dsy 看板管理列表 = 个人布局')
    me_boards = [b['board_id'] for b in req(zs_tok, '/api/me')['boards']]
    me_in_zs = [b for b in me_boards if b in set(zs_new)]
    ok(me_in_zs == [b for b in zs_new if b in set(me_boards)],
       'dsy /api/me 顺序 = 个人布局（顶部目录带/外部目录随之生效）')
    a2 = [b['board_id'] for b in req(admin_tok, '/api/boards')['boards']]
    ok(a2 == new_order, '个人布局不影响其他用户（admin 仍=默认布局）')
else:
    ok(False, 'dsy 可见看板不足 2 个，个人布局用例无法执行')

# ---------- C：新看板追加（个人布局缺新板 → 尾部可见不丢） ----------
print('【C】布局外看板追加')
if len(zs_before) >= 2:
    partial = zs_new[:-1]          # 个人布局少报一个
    r = req(zs_tok, '/api/boards/reorder', 'POST', {'order': partial})
    ok(r.get('ok'), '少报一个看板的顺序保存成功')
    zs_after2 = [b['board_id'] for b in req(zs_tok, '/api/boards')['boards']]
    omitted = zs_new[-1]           # reversed 后少报的 = zs_before[0]
    ok(set(zs_after2) == set(zs_before) and zs_after2[-1] == omitted,
       '布局外看板（%s）按默认序追加尾部，不丢失' % omitted[:10])

# ---------- D：非法输入 ----------
print('【D】非法输入')
r = req(admin_tok, '/api/boards/reorder', 'POST', {'order': []})
ok(r.get('__http__') == 400, '空 order → 400')
r = req(admin_tok, '/api/boards/reorder', 'POST', {'order': [a0[0], a0[0]]})
ok(r.get('__http__') == 400, '重复 board_id → 400')
r = req(admin_tok, '/api/boards/reorder', 'POST', {'order': ['__no_such__']})
ok(r.get('__http__') == 404, '未知看板 → 404')

# ---------- E：还原现场 ----------
print('【E】还原')
r = req(admin_tok, '/api/boards/reorder', 'POST', {'order': a0})
ok(r.get('ok'), '超管默认布局还原')
a3 = [b['board_id'] for b in req(admin_tok, '/api/boards')['boards']]
ok(a3 == a0, '还原后与初始顺序一致')
con = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db')
n = con.execute("DELETE FROM user_board_sorts WHERE username='dsy'").rowcount
con.commit(); con.close()
print('  （清理 dsy 个人布局 %d 行）' % n)

npass = sum(1 for c, _ in RES if c)
print('结果： %d/%d' % (npass, len(RES)))
sys.exit(0 if npass == len(RES) else 1)
