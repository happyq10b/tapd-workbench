# -*- coding: utf-8 -*-
"""#80 导出模板测试（2026-11-06 用户需求）：

① 创建：POST /api/export/templates（名称 + 按序字段）→ 200
② 列表：GET → fields 保序、titles 已解析、含 fmt='xlsx' 版式信息
③ 同名（同用户）→ 409；未知字段 → 400；空字段/空名 → 400
④ 更新：PUT 改名+改字段 → 200 且列表反映
⑤ 属主隔离：他人（非属主）PUT/DELETE → 404
⑥ 删除：DELETE → 200；再删 → 404
⑦ 与导出兼容：按模板 fields 顺序调 /api/export/xlsx → 列序 = 模板序

测试用 admin 账号创建（__tpl_ 前缀命名，finally 经 API 全清）。
"""
import io, json, os, sys, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http(path, method='GET', body=None, token=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        if raw:
            return r.status, r.read()
        return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}

def cleanup():
    from app.app import make_token
    tok = make_token('admin')
    code, r = http('/api/export/templates', token=tok)
    for t in (r.get('templates') or []):
        http('/api/export/templates/%d' % t['id'], 'DELETE', token=tok)

def main():
    from app.app import make_token
    tok = make_token('admin')
    tok_other = make_token('wwn')   # 生产既有账号，用于属主隔离验证
    NAME = '__tpl_季报字段'
    cleanup()
    try:
        print('\n【1】创建')
        code, r = http('/api/export/templates', 'POST',
                       {'name': NAME, 'fields': ['week_no', 'owner', 'card_name']}, token=tok)
        ok(code == 200 and r.get('id'), '创建 → 200（实际 %s %s）' % (code, r.get('detail', '')))
        tid = r.get('id')

        print('\n【2】列表')
        code, r = http('/api/export/templates', token=tok)
        tpls = r.get('templates') or []
        t = next((x for x in tpls if x['id'] == tid), None)
        ok(t is not None, '列表包含新模板')
        ok(t and t['fields'] == ['week_no', 'owner', 'card_name'],
           'fields 保序（实际 %s）' % (t and t['fields']))
        ok(t and t['titles'] == ['周数', '负责人', '事项名称'],
           'titles 已解析为中文（实际 %s）' % (t and t['titles']))
        ok(t and t.get('fmt') == 'xlsx', '版式信息 fmt=xlsx（实际 %s）' % (t and t.get('fmt')))

        print('\n【3】校验')
        code, r = http('/api/export/templates', 'POST',
                       {'name': NAME, 'fields': ['owner']}, token=tok)
        ok(code == 409, '同名模板 → 409（实际 %s）' % code)
        code, r = http('/api/export/templates', 'POST',
                       {'name': '__tpl_bad', 'fields': ['bogus']}, token=tok)
        ok(code == 400, '未知字段 → 400（实际 %s）' % code)
        code, r = http('/api/export/templates', 'POST',
                       {'name': '__tpl_bad', 'fields': []}, token=tok)
        ok(code == 400, '空字段列表 → 400（实际 %s）' % code)
        code, r = http('/api/export/templates', 'POST',
                       {'name': '  ', 'fields': ['owner']}, token=tok)
        ok(code == 400, '空名称 → 400（实际 %s）' % code)

        print('\n【4】更新')
        code, r = http('/api/export/templates/%d' % tid, 'PUT',
                       {'name': '__tpl_季报字段v2', 'fields': ['card_name', 'owner']}, token=tok)
        ok(code == 200, '更新 → 200（实际 %s）' % code)
        code, r = http('/api/export/templates', token=tok)
        t = next((x for x in (r.get('templates') or []) if x['id'] == tid), None)
        ok(t and t['name'] == '__tpl_季报字段v2' and t['fields'] == ['card_name', 'owner'],
           '更新后列表反映新名称与字段序（实际 %s %s）' % (t and t['name'], t and t['fields']))

        print('\n【5】属主隔离')
        code, r = http('/api/export/templates/%d' % tid, 'PUT',
                       {'name': 'x', 'fields': ['owner']}, token=tok_other)
        ok(code == 404, '他人更新他人模板 → 404（实际 %s）' % code)
        code, r = http('/api/export/templates/%d' % tid, 'DELETE', token=tok_other)
        ok(code == 404, '他人删除他人模板 → 404（实际 %s）' % code)

        print('\n【6】删除')
        code, r = http('/api/export/templates/%d' % tid, 'DELETE', token=tok)
        ok(code == 200, '删除 → 200（实际 %s）' % code)
        code, r = http('/api/export/templates/%d' % tid, 'DELETE', token=tok)
        ok(code == 404, '再删 → 404（实际 %s）' % code)

        print('\n【7】与导出兼容（模板序 = 导出列序）')
        code, data = http('/api/export/xlsx?fields=owner,card_name', token=tok, raw=True)
        from openpyxl import load_workbook
        hdr = [c.value for c in load_workbook(io.BytesIO(data)).active[1]] if code == 200 else []
        ok(code == 200 and hdr == ['负责人', '事项名称'],
           '模板字段序应用到导出 → 列序一致（实际 %s）' % hdr)
    finally:
        cleanup()
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

if __name__ == '__main__':
    main()
