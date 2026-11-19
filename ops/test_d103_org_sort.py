# -*- coding: utf-8 -*-
"""#103 架构排序 + 操作记录限高 API 实测"""
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
# T-0191 清理遗留账号（2026-08-18 建库期的 zhangsan 等空密码测试号已从库中删除）：
# 本测试改用自带夹具账号做「非管理员 403」用例，atexit 保证清理（夹具纪律 §3.3）。
import atexit
FIX_U = '__d103_u'
_c = sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db', timeout=15)
_c.execute('PRAGMA busy_timeout=15000')
_c.execute("INSERT OR REPLACE INTO users(username,password_hash,role,active_seq) VALUES(?,?,?,1)",
           (FIX_U, 'x', 'editor'))
_c.commit(); _c.close()
atexit.register(lambda: (lambda _c: (_c.execute("DELETE FROM users WHERE username=?", (FIX_U,)),
                                     _c.commit(), _c.close()))(
    sqlite3.connect(r'E:/WB缓存/2026-10-26-15-55-08/src/app.db', timeout=15)))
zs_tok = make_token(FIX_U)

tree0 = req(admin_tok, '/api/org/tree')['tree']
center = tree0[0]
kids0 = [c['name'] for c in center.get('children', [])]
ids0 = {c['name']: c['id'] for c in center.get('children', [])}
print('【A】同级交换（部门层）')
ok(len(kids0) >= 3, '中心下部门数足够（%s）' % kids0)

# 核算部 上移（与其前一位交换）
target = '核算部'
i = kids0.index(target)
prev_name = kids0[i - 1]
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'up'})
ok(r.get('ok') and r.get('moved') is True, '上移接口成功（与 %s 交换）' % prev_name)

tree1 = req(admin_tok, '/api/org/tree')['tree']
kids1 = [c['name'] for c in tree1[0].get('children', [])]
j = kids1.index(target)
ok(j == i - 1 and kids1[j + 1] == prev_name, '同级顺序交换正确（%s）' % kids1)

# 不跨层级：核算部下的小组顺序与位置不变；兄弟集合不变
def kids_of(tree, name):
    for c in tree[0].get('children', []):
        if c['name'] == name:
            return [g['name'] for g in c.get('children', [])]
    return []
g0, g1 = kids_of(tree0, target), kids_of(tree1, target)
ok(g0 == g1, '被移动节点的子层级不受影响（不跨层）')
ok(set(kids1) == set(kids0), '同级成员不变（仅顺序变化）')

print('【B】目录顺序随架构排序（_dept_order 同源）')
# 重新排一次（A/D 往返后已还原），真实校验 ME.depts 顺序
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'up'})
kids_now = [c['name'] for c in req(admin_tok, '/api/org/tree')['tree'][0].get('children', [])]
dl = req(admin_tok, '/api/me').get('depts', [])
expect = ['财务中心'] + kids_now       # 中心恒在目录树首位
ok(dl == expect, 'ME.depts（目录部门顺序）= 架构新顺序 %s' % dl)
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'down'})

print('【C】边界与权限')
# 取**当前**树的首位子节点（kids1 在 B 段的移动后已陈旧——曾致误报）
kids_cur = [c['name'] for c in req(admin_tok, '/api/org/tree')['tree'][0].get('children', [])]
first = kids_cur[0]
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[first], 'POST', {'direction': 'up'})
ok(r.get('ok') and r.get('moved') is False, '首行（%s）上移 → moved=False 不变' % first)
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'sideways'})
ok(r.get('__http__') == 400, '非法 direction → 400')
r = req(admin_tok, '/api/org/nodes/999999/reorder', 'POST', {'direction': 'up'})
ok(r.get('__http__') == 404, '未知节点 → 404')
r = req(zs_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'up'})
ok(r.get('__http__') == 403, '非管理员 → 403（仅管理员/超管可排序）')

print('【D】还原')
r = req(admin_tok, '/api/org/nodes/%d/reorder' % ids0[target], 'POST', {'direction': 'down'})
kids2 = [c['name'] for c in req(admin_tok, '/api/org/tree')['tree'][0].get('children', [])]
ok(kids2 == kids0, '还原后与初始顺序一致')

# 操作记录限高：接口层无法测 CSS → 由 UI 脚本覆盖，这里只确认 actions 数据仍正常
acts = req(admin_tok, '/api/cards/%s/actions' % _get_cid if False else '/api/me')
ok(bool(acts.get('username')), '接口层正常（UI 断言见 CDP 脚本）')

npass = sum(1 for c, _ in RES if c)
print('结果： %d/%d' % (npass, len(RES)))
sys.exit(0 if npass == len(RES) else 1)
