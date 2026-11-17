# -*- coding: utf-8 -*-
"""#79 导出字段选择测试（2026-11-06 用户需求）：

① GET /api/export/fields 返回字段清单（单一数据源 = XLSX_COLUMNS）
② GET /api/export/xlsx?fields=... 仅导出勾选字段，**列顺序 = 参数顺序（勾选顺序）**
③ fields 缺省 → 全量默认顺序（旧入口兼容）
④ 未知字段 → 400（fail-fast，防拼错字段名静默少列）
⑤ fields 只有空白/逗号 → 400「请至少勾选一个导出字段」

不需要夹具数据：表头与列数即可验证全部语义（行内容不参与断言）。
"""
import io, json, os, sys, urllib.request, urllib.error

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http_raw(path, token):
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + token})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, b''

def xlsx_headers(data):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    return [c.value for c in ws[1]]

def main():
    from app.app import make_token
    tok = make_token('admin')

    print('\n【1】字段清单接口')
    code, r = http_raw('/api/export/fields', tok)
    d = json.loads(r.decode()) if code == 200 else {}
    fields = d.get('fields') or []
    keys = [f['key'] for f in fields]
    ok(code == 200 and len(fields) == 23, '字段清单 23 项（#143：26-5+2，实际 %s）' % (len(fields) if code == 200 else code))
    ok('card_name' in keys and '_parent_name' in keys, '含基础列与派生列')

    print('\n【2】按勾选顺序导出')
    # 故意乱序：owner 在 card_name 前 —— 列顺序必须 = 参数顺序
    code, data = http_raw('/api/export/xlsx?fields=owner,card_name,week_no', tok)
    ok(code == 200, '导出 → 200（实际 %s）' % code)
    hdr = xlsx_headers(data) if code == 200 else []
    ok(hdr == ['负责人', '事项名称', '周数'],
       '列顺序 = 参数顺序（实际 %s）' % hdr)

    print('\n【3】缺省 = 全量默认顺序（旧入口兼容）')
    code, data = http_raw('/api/export/xlsx', tok)
    ok(code == 200, '无 fields 导出 → 200（实际 %s）' % code)
    hdr = xlsx_headers(data) if code == 200 else []
    ok(hdr and hdr[0] == '事项名称' and len(hdr) == 23,
       '缺省导出 23 列、首列事项名称（实际 %d 列）' % len(hdr))

    print('\n【4】异常兜底')
    code, r = http_raw('/api/export/xlsx?fields=bogus', tok)
    ok(code == 400, '未知字段 → 400（实际 %s）' % code)
    code, r = http_raw('/api/export/xlsx?fields=,%20,', tok)
    ok(code == 400, '只有空白/逗号 → 400 请至少勾选（实际 %s）' % code)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

if __name__ == '__main__':
    main()
