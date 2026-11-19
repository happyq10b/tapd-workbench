# -*- coding: utf-8 -*-
"""T-0181 小精灵 SVG 格式支持 API 测试（2026-11-12）
SVG 上传（净化后入库）/ 公开直出（image/svg+xml + CSP 沙箱头）/ 危险内容拒绝 /
其它图片入口不开放 SVG。夹具：__svg_ 前缀分区，try/finally 清理。
"""
import base64, json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
DB = os.path.join(ROOT, 'src', 'app.db')
P = '__svg_'
ZONE = P + '分区'
PASS = FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe='/:.%~_&=?'),
                                 data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body_bytes = r.read()
            if raw:
                return r.status, dict((k.lower(), v) for k, v in r.headers.items()), body_bytes
            return r.status, json.loads(body_bytes.decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def svg_data_url(text):
    return 'data:image/svg+xml;base64,' + base64.b64encode(text.encode('utf-8')).decode('ascii')


def cleanup():
    c = sqlite3.connect(DB)
    c.execute('DELETE FROM pet_images WHERE zone LIKE ?', (P + '%',))
    c.execute('DELETE FROM pet_zones WHERE name LIKE ?', (P + '%',))
    c.commit(); c.close()


def main():
    from app.app import make_token, SUPER_ADMIN
    t0 = make_token(SUPER_ADMIN)
    cleanup()
    s, r = call('POST', '/api/admin/pet/zones', t0, {'name': ZONE})
    ok(s == 200, '前置：测试分区已创建')
    try:
        print('① 干净 SVG 上传 → 净化入库 → 公开直出')
        clean_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
                     '<rect width="32" height="32" fill="#4a90d9"/></svg>')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'icon.svg', 'data': svg_data_url(clean_svg)})
        ok(s == 200 and r.get('id'), f'干净 SVG 上传 → 200（实际 {s} {r}）')
        iid = r['id']
        s, h, raw = call('GET', f'/pet/up/{iid}', None, raw=True)
        ok(s == 200 and 'image/svg+xml' in h.get('content-type', ''),
           f'公开直出 image/svg+xml（实际 {s} {h.get("content-type")}）')
        ok("sandbox" in h.get('content-security-policy', ''),
           'SVG 响应带 CSP 沙箱头（封死脚本执行面）')
        ok(b'rect' in raw and b'script' not in raw.lower(), 'SVG 内容完好返回')

        print('② 危险内容处置')
        evil_script = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                       '<script>alert(1)</script><rect width="10" height="10"/></svg>')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'evil.svg', 'data': svg_data_url(evil_script)})
        ok(s == 400, f'含 <script> 的 SVG → 400 拒绝（实际 {s}）')
        onload_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                      'onload="alert(1)"><rect width="10" height="10"/></svg>')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'on.svg', 'data': svg_data_url(onload_svg)})
        ok(s == 200, f'含 onload 属性 → 200（属性级净化，实际 {s}）')
        s2, h2, raw2 = call('GET', f"/pet/up/{r.get('id')}", None, raw=True)
        ok(b'onload' not in raw2, '入库前 onload 属性已被剥离')
        ext_svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                   'width="10" height="10"><a xlink:href="http://evil.example"><rect width="10" height="10"/></a></svg>')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'ext.svg', 'data': svg_data_url(ext_svg)})
        ok(s == 200, f'含外链引用 → 200（引用级净化，实际 {s}）')
        s2, h2, raw2 = call('GET', f"/pet/up/{r.get('id')}", None, raw=True)
        ok(b'evil.example' not in raw2, '外链引用已被剥离')

        print('③ 非法 SVG 拒绝')
        doctype_svg = '<!DOCTYPE svg [<!ENTITY x "x">]><svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>'
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'd.svg', 'data': svg_data_url(doctype_svg)})
        ok(s == 400, 'DOCTYPE/ENTITY（XML 实体炸弹）→ 400')
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'bad.svg', 'data': svg_data_url('<svg><rect></svg>')})
        ok(s == 400, '非法 XML → 400')
        big = 'data:image/svg+xml;base64,' + base64.b64encode(
            ('<svg xmlns="http://www.w3.org/2000/svg"><!-- ' + 'A' * (3 * 1024 * 1024) + ' --></svg>').encode()
        ).decode()
        s, r = call('POST', '/api/admin/pet/images', t0, {'zone': ZONE, 'name': 'big.svg', 'data': big})
        ok(s == 400, '超过 2MB → 400')
        # 非 base64 形式拒绝
        s, r = call('POST', '/api/admin/pet/images', t0,
                    {'zone': ZONE, 'name': 'u.svg',
                     'data': 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"/>'})
        ok(s == 400, '非 base64 的 SVG data URL → 400')

        print('④ 其它图片入口不开放 SVG')
        from app.app import _check_image_data_url
        from fastapi import HTTPException
        try:
            _check_image_data_url(svg_data_url(clean_svg))
            ok(False, '头像等入口默认拒绝 SVG')
        except HTTPException:
            ok(True, '头像等入口默认拒绝 SVG（allow_svg=False）')
        s, r = call('GET', '/api/admin/pet/zones', t0)
        z = [x for x in r['zones'] if x['name'] == ZONE][0]
        ok(z['count'] == 3, f'分区计数=3（实际 {z["count"]}）')
    finally:
        cleanup()
        print('夹具清理完成')
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM pet_images WHERE zone LIKE ?", (P + '%',)).fetchone()[0] \
        + c.execute("SELECT COUNT(*) FROM pet_zones WHERE name LIKE ?", (P + '%',)).fetchone()[0]
    c.close()
    ok(n == 0, f'零残留（实际 {n}）')
    print(f'\n==== 结果: PASS={PASS} FAIL={FAIL} ====')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
