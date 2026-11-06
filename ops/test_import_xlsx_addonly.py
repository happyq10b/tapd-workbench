# -*- coding: utf-8 -*-
"""#86 xlsx 导入「仅新增」改造测试：

① 模板下载：表头无 ID/编码类列（事项ID/看板ID/板块ID/工作空间ID）
② 新文件（无 ID 列）导入 → 全部新增；同名看板按名复用（不新建看板）
③ 同文件再导一次 → 再次新增（条数累加），不覆盖
④ 旧式文件带 card_id 列（填已有卡的 ID）→ 该列被忽略：原卡内容不被覆盖，
   且照常新增一条
⑤ 文件带 board_id 列（伪造 ID）→ 被忽略：按看板名新建，board_id 系统生成

夹具（__xa_ 前缀，自清理）：__xa_看板 + __xa_旧卡（owner=张三）。
"""
import io, json, os, sys, time, urllib.request, urllib.error
from openpyxl import Workbook, load_workbook

sys.path.insert(0, 'src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PREFIX = '__xa_'

PASS, FAIL = [], []
def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)

def http(path, method='GET', body=None, token=None, raw=False, multipart=None):
    import urllib.request as ur
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    data = None
    if multipart is not None:
        boundary = 'xa-boundary'
        fn, content = multipart
        data = (('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
                 'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'
                 % (boundary, fn)).encode() + content + ('\r\n--%s--\r\n' % boundary).encode())
        headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
    elif body is not None:
        data = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
    req = ur.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=20)
        b = r.read()
        return (r.status, b if raw else json.loads(b.decode() or '{}'))
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or '{}')
        except Exception: return e.code, {}

def make_xlsx(rows, with_id_cols=False, fake_board_id=None):
    """rows: [(card_name, owner)]；表头用中文标签。with_id_cols=True 时附带旧式 ID 列。"""
    from app.app import XLSX_COL_LABELS
    cols = ['card_name', 'board_name', 'owner']
    if with_id_cols:
        cols = ['card_id', 'board_id'] + cols
    wb = Workbook(); ws = wb.active
    ws.append([XLSX_COL_LABELS[c] for c in cols])
    bid = fake_board_id or ''
    for cn, ow in rows:
        vals = {'card_name': cn, 'board_name': PREFIX + '看板', 'owner': ow,
                'card_id': '__xa_existing__', 'board_id': bid}
        ws.append([vals.get(c, '') for c in cols])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

def cleanup():
    import sqlite3
    c = sqlite3.connect('src/app.db')
    like = PREFIX + '%'
    c.execute("DELETE FROM cards WHERE card_id LIKE ? OR board_name LIKE ? OR card_name LIKE ?", (like, like, like))
    c.execute("DELETE FROM board_columns WHERE col_key LIKE ? OR board_id LIKE ?", (like, like))
    c.execute("DELETE FROM board_config WHERE board_id LIKE ?", (like,))
    c.execute("DELETE FROM boards WHERE board_id LIKE ? OR board_name LIKE ?", (like, like))
    c.commit(); c.close()

def main():
    from app.app import make_token
    tok = make_token('admin')
    cleanup()
    try:
        print('\n【1】模板：无 ID 类列')
        code, body = http('/api/import/template', token=tok, raw=True)
        wbt = load_workbook(io.BytesIO(body))
        ws = wbt['导入数据']
        hdrs = [c.value for c in ws[1]]
        ok(code == 200, '模板下载 200')
        bad = [h for h in hdrs if h and ('ID' in h)]
        ok(bad == [], '表头无 ID/编码类列（实际 %s）' % hdrs)
        ok('事项名称 *' in hdrs and '所属看板名称 *' in hdrs, '必填列仍在')
        ws3 = wbt['使用说明']
        txt = '\n'.join(str(r[0].value or '') for r in ws3.iter_rows())
        ok('仅新增' in txt and '不会覆盖' in txt, '使用说明已改为「仅新增」口径')

        print('\n【2】夹具 + 新文件导入（无 ID 列）')
        import sqlite3
        c = sqlite3.connect('src/app.db'); c.row_factory = sqlite3.Row
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        bid = PREFIX + 'B1'
        c.execute("INSERT INTO boards (board_id,board_name,owner,created_at) VALUES (?,?,?,?)",
                  (bid, PREFIX + '看板', 'admin', now))
        c.execute("INSERT INTO cards (card_id,board_id,board_name,card_name,owner,created,deleted) VALUES (?,?,?,?,?,?,0)",
                  (PREFIX + 'old1', bid, PREFIX + '看板', PREFIX + '旧卡', '张三', now))
        c.commit(); c.close()

        code, r = http('/api/import/xlsx', 'POST', token=tok,
                       multipart=('new.xlsx', make_xlsx([(PREFIX + '新卡1', '李四')])))
        ok(code == 200 and r.get('created') == 1 and r.get('updated') == 0,
           '新文件导入 → 新增 1、更新 0（实际 %s）' % r)
        c = sqlite3.connect('src/app.db'); c.row_factory = sqlite3.Row
        old = c.execute("SELECT owner FROM cards WHERE card_id=?", (PREFIX + 'old1',)).fetchone()
        ok(old and old['owner'] == '张三', '已有记录未被覆盖（owner 仍张三）')
        newcard = c.execute("SELECT card_id,board_id FROM cards WHERE card_name=? AND card_id LIKE 'C%'",
                            (PREFIX + '新卡1',)).fetchone()
        ok(newcard is not None and newcard['card_id'].startswith('C'), '新事项编号系统生成（C 前缀）')
        ok(newcard and newcard['board_id'] == bid, '同名看板按名复用（未新建看板）')
        nb = c.execute("SELECT COUNT(*) n FROM boards WHERE board_name=?", (PREFIX + '看板',)).fetchone()['n']
        ok(nb == 1, '未重复登记同名看板')
        c.close()

        print('\n【3】同文件再导一次 → 仅新增')
        code, r = http('/api/import/xlsx', 'POST', token=tok,
                       multipart=('new2.xlsx', make_xlsx([(PREFIX + '新卡2', '王五')])))
        ok(code == 200 and r.get('created') == 1, '再次导入 → 新增 1')
        c = sqlite3.connect('src/app.db')
        n = c.execute("SELECT COUNT(*) FROM cards WHERE card_name LIKE ? AND deleted=0", (PREFIX + '%',)).fetchone()[0]
        ok(n == 3, '条数累加不覆盖（旧卡+两条新卡 = 3，实际 %d）' % n)
        c.close()

        print('\n【4】旧式文件带 card_id 列（填已有卡 ID）→ 忽略、不覆盖')
        code, r = http('/api/import/xlsx', 'POST', token=tok,
                       multipart=('old.xlsx', make_xlsx([(PREFIX + '旧卡', '李四')], with_id_cols=True)))
        ok(code == 200 and r.get('created') == 1, '旧式文件导入 → 照常新增（实际 %s）' % r)
        c = sqlite3.connect('src/app.db'); c.row_factory = sqlite3.Row
        old = c.execute("SELECT owner FROM cards WHERE card_id=?", (PREFIX + 'old1',)).fetchone()
        ok(old and old['owner'] == '张三', '文件中的已有 ID 未触发覆盖（原卡 owner 仍张三）')
        n = c.execute("SELECT COUNT(*) FROM cards WHERE card_name=? AND deleted=0", (PREFIX + '旧卡',)).fetchone()[0]
        ok(n == 2, '同名事项按新增处理（2 条并存）')
        c.close()

        print('\n【5】文件带伪造 board_id 列 → 忽略、按名新建')
        code, r = http('/api/import/xlsx', 'POST', token=tok,
                       multipart=('fake.xlsx', make_xlsx([(PREFIX + '看板2卡', '赵六')], with_id_cols=True, fake_board_id='B_FAKE123')))
        ok(code == 200, '导入 200（实际 %s）' % code)
        c = sqlite3.connect('src/app.db'); c.row_factory = sqlite3.Row
        b2 = c.execute("SELECT board_id FROM boards WHERE board_name=?", (PREFIX + '看板',)).fetchone()
        ok(b2 and not b2['board_id'].startswith('B_FAKE'), '伪造 board_id 未被采用')
        c.close()
    finally:
        cleanup()
        print('夹具已清理')
    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)

if __name__ == '__main__':
    main()
