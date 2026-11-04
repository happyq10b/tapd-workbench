# -*- coding: utf-8 -*-
"""需求 3/4/5 的后端测试：板块完成情况 / 全局备份 / 事项级导出随筛选"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import hash_pw, make_token, dbq  # noqa: E402

BASE = 'http://127.0.0.1:8100'
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'app.db')
PREFIX = '__hp_'
U_ADMIN = PREFIX + 'admin'
U_OWNER = PREFIX + 'owner'      # 板块负责人
U_OTHER = PREFIX + 'other'      # 其他成员
PWD = 'At159357'
now = '2026-11-04 12:00:00'

PASS, FAIL = [], []


def ok(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  PASS ' if cond else '  ✗ ') + msg)


def http(path, method='GET', body=None, token=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    h = {'Content-Type': 'application/json'}
    if token:
        h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        txt = r.read()
        if raw:
            return r.status, txt
        return r.status, json.loads(txt.decode() if txt else '{}')
    except urllib.error.HTTPError as e:
        txt = e.read()
        if raw:
            return e.code, txt
        try:
            return e.code, json.loads(txt.decode() if txt else '{}')
        except Exception:
            return e.code, {'detail': txt.decode()[:300]}


def setup():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    for a in (U_ADMIN, U_OWNER, U_OTHER):
        c.execute('DELETE FROM users WHERE username=?', (a,))
        c.execute('DELETE FROM team_members WHERE account=?', (a,))
        c.execute('INSERT INTO team_members (name,workgroups,account,created_at) VALUES (?,?,?,?)',
                  (PREFIX + a, '', a, now))
        c.execute('INSERT INTO users (username,password_hash,role,allowed_boards,allowed_columns,created_at)'
                  ' VALUES (?,?,?,?,?,?)', (a, hash_pw(PWD), 'admin' if a == U_ADMIN else 'editor', '*', '*', now))
    stamp = str(int(time.time() * 1000))
    bid = 'HP' + stamp
    c.execute('INSERT INTO boards (board_id,board_name,workspace_id,owner,participants,sort,created_at)'
              ' VALUES (?,?,?,?,?,0,?)', (bid, PREFIX + '看板', '', U_OWNER, '', now))
    c.execute('INSERT INTO board_columns (col_key,column_id,board_id,column_name,created_at,creator,nature,year,pinned,owner,participants,completion)'
              ' VALUES (?,?,?,?,?,?,?,?,0,?,?,?)',
              (bid + '::' + PREFIX + 'A', PREFIX + 'col1', bid, PREFIX + 'A', now, U_OWNER, '日常', '2026', U_OWNER, '', 'open'))
    # 三张事项：不同状态 / 周数
    cid1, cid2 = PREFIX + 'c1', PREFIX + 'c2'
    for i, (st, wk) in enumerate((('done', '2026年第45周'), ('open', '2026年第46周'))):
        c.execute('INSERT INTO cards (card_id,board_id,board_name,column_id,column_name,card_name,status,status_name,'
                  'creator,owner,cc,begin,due,created,modified,description,week_no,deleted,parent_id,pinned,priority,label)'
                  ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,0,?,?)',
                  (cid1 if i == 0 else cid2, bid, PREFIX + '看板', PREFIX + 'col1', PREFIX + 'A',
                   PREFIX + ('事项1' if i == 0 else '事项2'), st, '已完成' if st == 'done' else '未完成',
                   U_OWNER, U_OWNER, '', '2026-08-06', '2026-08-14', now, now,
                   PREFIX + '描述' + str(i + 1), wk, '', '普通', ''))
    c.commit()
    c.close()
    return {'bid': bid, 'cid1': cid1, 'cid2': cid2,
            'col_key': bid + '::' + PREFIX + 'A'}


def cleanup(fx):
    c = sqlite3.connect(DB)
    if fx:
        for t in ('cards', 'board_columns', 'board_config'):
            c.execute('DELETE FROM %s WHERE board_id=?' % t, (fx['bid'],))
        c.execute('DELETE FROM boards WHERE board_id=?', (fx['bid'],))
    for a in (U_ADMIN, U_OWNER, U_OTHER):
        c.execute('DELETE FROM users WHERE username=?', (a,))
        c.execute('DELETE FROM team_members WHERE account=?', (a,))
    c.commit()
    c.close()


def main():
    fx = setup()
    try:
        tok = {a: make_token(a) for a in (U_ADMIN, U_OWNER, U_OTHER)}

        # ═══ 需求3：板块完成情况 ═══
        print('\n【需求3】板块完成情况字段')
        code, r = http('/api/columns', 'PUT',
                       {'col_key': fx['col_key'], 'board_id': fx['bid'],
                        'column_name': PREFIX + 'A', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'completion': 'done'},
                       token=tok[U_OWNER])
        ok(code == 200, '板块负责人设置完成情况=已完成 → 200（实际 %s）' % code)
        row = dbq('SELECT completion FROM board_columns WHERE col_key=?', (fx['col_key'],))[0]
        ok(row['completion'] == 'done', '完成情况已落库（%s）' % row['completion'])

        code, r = http('/api/columns', 'PUT',
                       {'col_key': fx['col_key'], 'board_id': fx['bid'],
                        'column_name': PREFIX + 'A', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'completion': 'progressing'},
                       token=tok[U_OTHER])
        ok(code == 403, '其他成员改完成情况 → 403（实际 %s）' % code)
        row2 = dbq('SELECT completion FROM board_columns WHERE col_key=?', (fx['col_key'],))[0]
        ok(row2['completion'] == 'done', '被拒后原值未变（%s）' % row2['completion'])

        code, r = http('/api/columns', 'PUT',
                       {'col_key': fx['col_key'], 'board_id': fx['bid'],
                        'column_name': PREFIX + 'A', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'completion': 'progressing'},
                       token=tok[U_ADMIN])
        ok(code == 200, '管理员可改完成情况 → 200（实际 %s）' % code)

        code, r = http('/api/columns', 'PUT',
                       {'col_key': fx['col_key'], 'board_id': fx['bid'],
                        'column_name': PREFIX + 'A', 'created_at': '2026-11-04',
                        'nature': '日常', 'year': '2026', 'completion': 'xyz'},
                       token=tok[U_ADMIN])
        ok(code == 400, '非法完成情况 → 400（实际 %s）' % code)

        # 目录接口带出 completion（板块元信息在 /api/cards 的 columns 里）
        code, cd = http('/api/cards?board_ids=' + fx['bid'], token=tok[U_OWNER])
        col = None
        for c in (cd.get('columns') or []):
            if c.get('column_name') == PREFIX + 'A':
                col = c
        ok(col is not None and col.get('completion') == 'progressing',
           '目录返回板块完成情况（%s）' % (col.get('completion') if col else 'NOT FOUND'))

        # ═══ 需求4：备份/恢复面向全局 ═══
        print('\n【需求4】备份/恢复面向全局')
        code, exp = http('/api/export', token=tok[U_ADMIN])
        ok(code == 200, '导出 JSON → 200（实际 %s）' % code)
        for key in ('boards', 'columns', 'cards', 'subtasks', 'team',
                    'org_nodes', 'org_appointments', 'workgroups'):
            ok(key in exp, '备份含 %s' % key)
        ok(exp.get('scope') == 'global', '备份 scope=global（%s）' % exp.get('scope'))
        all_cards = dbq('SELECT COUNT(*) n FROM cards WHERE deleted=0')[0]['n']
        ok(len(exp.get('cards') or []) == all_cards,
           '备份含**全部**事项（导出 %d / 库中 %d）' % (len(exp.get('cards') or []), all_cards))
        ok(len(exp.get('columns') or []) >= len(dbq('SELECT * FROM board_columns')),
           '备份含全部板块')

        code, r = http('/api/export', token=tok[U_OTHER])
        ok(code == 403, '非管理员备份 → 403（实际 %s）' % code)

        # ═══ 需求5：导出 xlsx = 事项级 + 随筛选 ═══
        print('\n【需求5】导出 xlsx 事项级 + 随页面筛选')
        code, blob = http('/api/export/xlsx?board_ids=' + fx['bid'], token=tok[U_ADMIN], raw=True)
        ok(code == 200, '导出 xlsx → 200（实际 %s）%s' % (code, (' ← '+str(blob)[:200]) if code != 200 else ''))
        try:
            import io as _io
            import openpyxl
            wb = openpyxl.load_workbook(_io.BytesIO(blob))
            ws = wb.active
            hdr = [c.value for c in ws[1]]
            ok('事项名称' in hdr, '表头含【事项名称】（一维表每行一个事项）')
            for need in ('所属看板', '所属板块', '负责人', '参与人', '周数', '描述'):
                ok(need in hdr, '表头含【%s】' % need)
            ok('评论' not in hdr, '表头不含【评论】（描述类信息除评论外）')
            names = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
            ok(len(names) == 2, '夹具看板导出 2 行（实际 %d）' % len(names))

            # 筛选：状态=done → 只剩 1 行
            code, blob2 = http('/api/export/xlsx?board_ids=%s&status=done' % fx['bid'], token=tok[U_ADMIN], raw=True)
            wb2 = openpyxl.load_workbook(_io.BytesIO(blob2))
            ws2 = wb2.active
            n2 = ws2.max_row - 1
            ok(n2 == 1, '筛选 status=done → 导出 1 行（实际 %d）' % n2)

            # 筛选：周数
            code, blob3 = http('/api/export/xlsx?board_ids=%s&week=%s'
                               % (fx['bid'], urllib.request.quote('2026年第46周')), token=tok[U_ADMIN], raw=True)
            wb3 = openpyxl.load_workbook(_io.BytesIO(blob3))
            n3 = wb3.active.max_row - 1
            ok(n3 == 1, '筛选 week=2026年第46周 → 导出 1 行（实际 %d）' % n3)

            # 筛选：搜索词
            code, blob4 = http('/api/export/xlsx?board_ids=%s&q=%s'
                               % (fx['bid'], urllib.request.quote('事项1')), token=tok[U_ADMIN], raw=True)
            wb4 = openpyxl.load_workbook(_io.BytesIO(blob4))
            n4 = wb4.active.max_row - 1
            ok(n4 == 1, '筛选 q=事项1 → 导出 1 行（实际 %d）' % n4)

            # 筛选：人员（锚定 owner）
            code, blob5 = http('/api/export/xlsx?board_ids=%s&person=%s'
                               % (fx['bid'], urllib.request.quote(U_OWNER)), token=tok[U_ADMIN], raw=True)
            wb5 = openpyxl.load_workbook(_io.BytesIO(blob5))
            n5 = wb5.active.max_row - 1
            ok(n5 == 2, '筛选 person=板块负责人 → 导出 2 行（实际 %d）' % n5)
        except ImportError:
            ok(False, 'openpyxl 不可用，无法解析 xlsx')

    finally:
        cleanup(fx)

    print('\n=== 结果：%d 通过 / %d 失败 ===' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：')
        for f in FAIL:
            print('  - ' + f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
