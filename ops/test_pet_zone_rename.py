# -*- coding: utf-8 -*-
"""T-0180 分区重命名 API 测试（2026-11-12）
重命名：图片随迁、随机范围引用随迁；校验链（空名/超长/保留名/重名/同名/不存在）。
夹具：__rn_ 前缀分区；login_pet 备份恢复（§3.3）。
"""
import json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__rn_'
ZA, ZB = P + '旧分区', P + '新分区'
PNG = ('data:image/png;base64,'
       'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
PASS = FAIL = 0
_MAX_SH_BEFORE = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'),
                                 data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def cleanup(restore_pet=None):
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM pet_images WHERE zone LIKE ?', (P + '%',))
    c.execute('DELETE FROM pet_zones WHERE name LIKE ?', (P + '%',))
    if restore_pet is not None:
        c.execute("UPDATE app_settings SET value=? WHERE key='login_pet'", (restore_pet,))
        c.execute("DELETE FROM state_history WHERE scope='login_pet' AND id>?", (_MAX_SH_BEFORE,))
    c.commit(); c.close()


def main():
    global _MAX_SH_BEFORE
    from app.app import make_token, SUPER_ADMIN
    t0 = make_token(SUPER_ADMIN)
    c = sqlite3.connect(DB)
    orig = (c.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone() or [''])[0]
    _MAX_SH_BEFORE = c.execute("SELECT COALESCE(MAX(id),0) FROM state_history WHERE scope='login_pet'").fetchone()[0]
    c.close()
    try:
        call('POST', '/api/admin/pet/zones', t0, {'name': ZA})
        call('POST', '/api/admin/pet/images', t0, {'zone': ZA, 'name': 'a.png', 'data': PNG})

        print('① 重命名成功路径（图片随迁）')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZA), t0, {'name': ZB})
        ok(s == 200 and r.get('moved_images') == 1, f'重命名 → 200 且图片随迁 1 张（实际 {s} {r}）')
        c2 = sqlite3.connect(DB)
        z = c2.execute('SELECT COUNT(*) FROM pet_zones WHERE name=?', (ZB,)).fetchone()[0]
        img = c2.execute('SELECT COUNT(*) FROM pet_images WHERE zone=?', (ZB,)).fetchone()[0]
        old = c2.execute('SELECT COUNT(*) FROM pet_zones WHERE name=?', (ZA,)).fetchone()[0]
        c2.close()
        ok(z == 1 and img == 1 and old == 0, '库内：新分区存在、图片挂新名、旧名消失')

        print('② 校验链')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': ''})
        ok(s == 400, '空名 → 400')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': 'x' * 21})
        ok(s == 400, '超过 20 字 → 400')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': '__builtin__'})
        ok(s == 400, '内置保留名 → 400')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': ZB})
        ok(s == 400, '同名 → 400')
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(P + '不存在'), t0, {'name': ZA})
        ok(s == 404, '不存在的分区 → 404')
        call('POST', '/api/admin/pet/zones', t0, {'name': ZA})
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': ZA})
        ok(s == 409, '与现有分区重名 → 409')

        print('③ 随机范围引用随迁')
        s, r = call('POST', '/api/admin/pet', t0, {'mode': 'random', 'zone': ZB})
        ok(s == 200, '随机范围指向 ZB → 200')
        ZC = P + '新分区2'
        s, r = call('PUT', '/api/admin/pet/zones/' + urllib.parse.quote(ZB), t0, {'name': ZC})
        ok(s == 200, f'重命名 ZB → ZC → 200（实际 {s} {r}）')
        s, r = call('GET', '/api/admin/pet', t0)
        ok(r.get('mode') == 'random' and r.get('zone') == ZC,
           f'login_pet 随机范围引用已随迁（实际 {r}）')
        s, r = call('GET', '/api/login/notice', None)
        ok(('/pet/up/' in (r.get('pet_url') or '')), f'登录页 pet_url 落在随迁图片（实际 {r.get("pet_url")}）')
    finally:
        cleanup(restore_pet=orig)
        print('夹具清理完成（分区/图片/login_pet 已恢复）')
    print(f'\n==== 结果: PASS={PASS} FAIL={FAIL} ====')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
