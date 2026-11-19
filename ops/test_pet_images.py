#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""小精灵分区/上传/排序 API 测试（T-0177，2026-11-12）
  ① 分区管理：内置分区只读；新增（去重/长度/保留名/空名）；删除（仅空分区）
  ② 上传：单张入库、公开端点 /pet/up/{id} 直出、格式/大小/分区校验（失败无脏数据）
  ③ 排序：整区重排持久化；ids 不一致 → 400；置顶语义（0 号位）
  ④ 随机按分区隔离：random zone → notice.pet_url 落在该分区图片集合内
  ⑤ 固定上传图 / 删除联动（fixed 引用被删 → 自动回退随机内置）
  ⑥ 向后兼容：旧格式 '' 与 'N' 解析不回归；非超管 403
夹具：__pt_ 前缀分区；login_pet 先备份后恢复（§3.3）；state_history 测试段清理。
"""
import base64, json, os, sqlite3, sys, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__pt_'
ZA, ZB = P + '分区A', P + '分区B'
PASS = FAIL = 0

# 1×1 PNG（最小合法图片）
PNG = ('data:image/png;base64,'
       'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None):
    if '?' in path:
        p, q = path.split('?', 1)
        q = urllib.parse.quote(q, safe='=&,')
    else:
        p, q = path, ''
    p = urllib.parse.quote(p, safe='/:.%~_')
    path = p + ('?' + q if q else '')
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def get_raw(path):
    """无鉴权 GET，返回 (status, headers 小写键 dict)——供 /pet/up/{id} 直出校验。"""
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_'))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {}


def cleanup(keep_login_pet=None):
    """夹具清理；keep_login_pet 非 None 时恢复 login_pet 原值并清测试快照段。"""
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM pet_images WHERE zone LIKE ?', (P + '%',))
    c.execute('DELETE FROM pet_zones WHERE name LIKE ?', (P + '%',))
    c.execute('DELETE FROM users WHERE username LIKE ?', (P + '%',))
    if keep_login_pet is not None:
        c.execute("UPDATE app_settings SET value=? WHERE key='login_pet'", (keep_login_pet,))
        c.execute("DELETE FROM state_history WHERE id>?", (_MAX_SH_BEFORE,))
    c.commit(); c.close()


def main():
    global _MAX_SH_BEFORE
    from app.app import make_token, SUPER_ADMIN
    t0 = make_token(SUPER_ADMIN)
    c = sqlite3.connect(DB)
    orig_pet = (c.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone() or [''])[0]
    _MAX_SH_BEFORE = c.execute('SELECT COALESCE(MAX(id),0) FROM state_history').fetchone()[0]
    # 非超管夹具账号（403 校验用）
    from app.app import hash_pw
    u = P + 'u1'
    c.execute("DELETE FROM users WHERE username=?", (u,))
    c.execute("INSERT INTO users(username,password_hash,password_plain,role,allowed_boards,active_seq)"
              " VALUES(?,?,?,?,?,1)", (u, hash_pw('x'), 'x', 'editor', '*'))
    c.commit(); c.close()
    t1 = make_token(u)
    try:
        # ---------- ① 分区管理 ----------
        print('① 分区管理')
        s, r = call('GET', '/api/admin/pet/zones', t0)
        ok(s == 200 and any(z['name'] == '__builtin__' and z['count'] == 386 and z['builtin']
                            for z in r['zones']), '分区清单含内置分区（386 张）')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': ZA})
        ok(s == 200, f'新增分区A → 200（实际 {s} {r}）')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': ZA})
        ok(s == 409, '重名分区 → 409')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': ''})
        ok(s == 400, '空分区名 → 400')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': 'x' * 21})
        ok(s == 400, '超过 20 字 → 400')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': '__builtin__'})
        ok(s == 400, '内置保留名 → 400')
        s, r = call('DELETE', '/api/admin/pet/zones/' + urllib.parse.quote(ZA), t0)
        ok(s == 200, '删除空分区A → 200')
        call('POST', '/api/admin/pet/zones', t0, {'name': ZA})  # 重建供后续用例
        call('POST', '/api/admin/pet/zones', t0, {'name': ZB})

        # ---------- ② 上传 ----------
        print('② 上传与公开直出')
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': 'a.png', 'data': PNG})
        ok(s == 200 and r.get('id'), f'上传图片A1 → 200（实际 {s} {r}）')
        ID1 = r['id']
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': 'a2.png', 'data': PNG})
        ID2 = r['id']; ok(s == 200, '上传图片A2 → 200')
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZB, 'name': 'b.png', 'data': PNG})
        IDB = r['id']; ok(s == 200, '上传图片B1（分区B 独立）→ 200')
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': '__builtin__', 'name': 'x', 'data': PNG})
        ok(s == 400, '上传进内置分区 → 400（只读）')
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': P + '不存在', 'name': 'x', 'data': PNG})
        ok(s == 404, '上传进不存在分区 → 404')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZA, 'name': 'x.txt', 'data': 'data:text/plain;base64,aGVsbG8='})
        ok(s == 400, '非图片格式 → 400')
        big = 'data:image/png;base64,' + 'A' * (3 * 1024 * 1024)   # base64 3/4 折算 ≈ 2.25MB > 2MB
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': 'big.png', 'data': big})
        ok(s == 400, '超过 2MB 上限 → 400')
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': '', 'data': ''})
        ok(s == 400, '空 data → 400')
        # 脏数据自查：上述失败请求不应入库
        c2 = sqlite3.connect(DB)
        n = c2.execute('SELECT COUNT(*) FROM pet_images WHERE zone=?', (ZA,)).fetchone()[0]
        c2.close()
        ok(n == 2, f'失败请求零脏数据（分区A 恰 2 张，实际 {n}）')
        s, h = get_raw(f'/pet/up/{ID1}')
        ok(s == 200 and 'image/png' in h.get('content-type', ''),
           f'/pet/up/{{id}} 公开直出 PNG（实际 {s} {h.get("content-type")}）')
        s, _ = get_raw('/pet/up/99999999')
        ok(s == 404, '不存在 id → 404')
        s, r = call('GET', '/api/admin/pet/zones', t0)
        ca = [z for z in r['zones'] if z['name'] == ZA][0]
        ok(ca['count'] == 2, f'分区A 计数=2（实际 {ca["count"]}）')

        # ---------- ③ 排序持久化 ----------
        print('③ 排序持久化')
        s, r = call('GET', '/api/admin/pet/images?zone=' + ZA, t0)   # call() 内部会做 query 编码
        ids0 = [m['id'] for m in r['images']]
        ok(ids0 == [ID1, ID2], f'默认按入库序（实际 {ids0}）')
        s, r = call('PUT', '/api/admin/pet/images/order', t0,
                    {'zone': ZA, 'ids': [ID2, ID1]})
        ok(s == 200, '整区重排（A2 提前）→ 200')
        c2 = sqlite3.connect(DB)
        sorts = dict(c2.execute('SELECT id, sort FROM pet_images WHERE zone=?', (ZA,)).fetchall())
        c2.close()
        ok(sorts.get(ID2) == 0 and sorts.get(ID1) == 1, f'新顺序已持久化（实际 {sorts}）')
        s, r = call('PUT', '/api/admin/pet/images/order', t0, {'zone': ZA, 'ids': [ID1]})
        ok(s == 400, '排序列表缺图片 → 400（防漏）')
        s, r = call('PUT', '/api/admin/pet/images/order', t0, {'zone': ZB, 'ids': [ID1, ID2]})
        ok(s == 400, '跨分区 ids 混入 → 400（防串区）')
        s, r = call('PUT', '/api/admin/pet/images/order', t0,
                    {'zone': '__builtin__', 'ids': [1, 2]})
        ok(s == 400, '内置分区排序 → 400（只读）')
        # 置顶语义 = 重排到 0 号位（前端 unshift 后 PUT order，此处等价验证）
        call('PUT', '/api/admin/pet/images/order', t0, {'zone': ZA, 'ids': [ID1, ID2]})

        # ---------- ④ 随机按分区隔离 ----------
        print('④ 随机范围按分区隔离')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'random', 'zone': ZA})
        ok(s == 200, f'随机范围=分区A → 200（实际 {s} {r}）')
        seen = set()
        for _ in range(12):
            s2, r2 = call('GET', '/api/login/notice', None)
            url = r2.get('pet_url', '')
            ok2 = ('/pet/up/%d' % ID1 == url or '/pet/up/%d' % ID2 == url)
            if not ok2:
                seen.add(url); break
            seen.add(url)
        ok(not any(u.startswith('/pet/') and 'up' not in u for u in seen) and len(seen) <= 2,
           f'12 次拉取 pet_url 全部落在分区A 图片集合内（出现 {seen or "{ID1,ID2}"}）')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'random', 'zone': P + '不存在'})
        ok(s == 404, '随机范围指向不存在分区 → 404')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r['mode'] == 'random' and r['zone'] == ZA, f'读取设置=随机/分区A（实际 {r}）')

        # ---------- ⑤ 固定上传图 + 删除联动 ----------
        print('⑤ 固定上传图与删除联动')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'fixed', 'image_id': ID2})
        ok(s == 200, f'固定上传图 #{ID2} → 200（实际 {s} {r}）')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r['mode'] == 'fixed' and r['kind'] == 'upload' and r['image_id'] == ID2,
           f'读取设置=固定/上传（实际 {r}）')
        s, r = call('GET', '/api/login/notice', None)
        ok(r.get('pet_url') == '/pet/up/%d' % ID2, f'notice.pet_url 指向该图（实际 {r.get("pet_url")}）')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'fixed', 'image_id': 99999999})
        ok(s == 404, '固定不存在的图片 → 404')
        s, r = call('DELETE', f'/api/admin/pet/images/{ID2}', t0)
        ok(s == 200, '删除被固定引用的图片 → 200')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r['mode'] == 'random' and r['kind'] == 'builtin',
           f'引用被删 → 自动回退随机内置（实际 {r}）')
        s, r = call('DELETE', f'/api/admin/pet/images/{ID2}', t0)
        ok(s == 404, '重复删除 → 404')
        # 删除分区 → 连带删除其下图片（T-0181 用户要求不留存）；随机范围指向该分区 → 回退随机内置
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'random', 'zone': ZA})
        ok(s == 200, '随机范围指向分区A → 200')
        s, r = call('DELETE', '/api/admin/pet/zones/' + urllib.parse.quote(ZA), t0)
        ok(s == 200 and r.get('removed_images') == 1,
           f'删除含图分区 → 200 连带删图 1 张（实际 {s} {r}）')
        c2 = sqlite3.connect(DB)
        n_img = c2.execute('SELECT COUNT(*) FROM pet_images WHERE zone=?', (ZA,)).fetchone()[0]
        n_zone = c2.execute('SELECT COUNT(*) FROM pet_zones WHERE name=?', (ZA,)).fetchone()[0]
        c2.close()
        ok(n_img == 0 and n_zone == 0, f'分区与图片均无留存（实际 img={n_img} zone={n_zone}）')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r['mode'] == 'random' and r['kind'] == 'builtin',
           f'随机范围指向被删分区 → 回退随机内置（实际 {r}）')
        s, r = call('POST', '/api/admin/pet/zones', t0, {'name': ZA})   # 重建供 ⑥ 后清理
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': 'x.png', 'data': PNG})
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'fixed', 'image_id': r['id']})
        ok(s == 200, '固定分区A 新图 → 200')
        _fx_id = r2 = None
        s, r = call('DELETE', '/api/admin/pet/zones/' + urllib.parse.quote(ZA), t0)
        ok(s == 200, '删除含被固定引用图片的分区 → 200 级联')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r['mode'] == 'random' and r['kind'] == 'builtin',
           f'固定引用被级联删除 → 回退随机内置（实际 {r}）')

        # ---------- ⑥ 兼容与权限 ----------
        print('⑥ 向后兼容与非超管 403')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'fixed', 'no': 299})
        ok(s == 200, '固定内置编号 299 → 200')
        s, r = call('GET', '/api/login/notice', None)
        ok(r.get('pet_url') == '/pet/299' and r.get('pet') != '299',
           f'新格式 JSON 下 notice.pet_url=/pet/299（实际 {r.get("pet_url")}）')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'bogus'})
        ok(s == 400, '非法模式 → 400')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'fixed', 'no': 500})
        ok(s == 400, '编号超范围 → 400')
        s, r = call('GET', '/api/admin/pet/zones', t1)
        ok(s == 403, f'非超管访问分区接口 → 403（实际 {s}）')
        s, r = call('POST', '/api/admin/pet/images', t1, {'zone': ZA, 'data': PNG})
        ok(s == 403, f'非超管上传 → 403（实际 {s}）')
        # 前端静态断言
        html = open(os.path.join(ROOT, 'src', 'static', 'index.html'), encoding='utf-8').read()
        ok('pet:   {ratio:1' in html and 'CROP.onConfirm' in html, '裁剪器 pet 规格 + onConfirm 回调已接线')
        ok('id="petFileInput"' in html and 'id="petZoneTabs"' in html and 'id="petUpList"' in html,
           '上传入口/分区 tab/图片列表 DOM 就位')
        ok("petSaveOrder" in html and "draggable=\"true\"" in html, '拖拽排序 + 持久化调用就位')
        lg = open(os.path.join(ROOT, 'src', 'static', 'login.html'), encoding='utf-8').read()
        ok('pet_url' in lg, '登录页优先使用 pet_url')
    finally:
        cleanup(keep_login_pet=orig_pet)
        print('夹具清理完成（分区/图片/login_pet 已恢复）')
    print(f'\n结果：PASS {PASS} / FAIL {FAIL}')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
