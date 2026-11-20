#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#124 API 测试：看板改名接口 PUT /api/boards/{bid}/rename

验证：
  ① 正常改名 → boards.board_name 更新 + cards 冗余 board_name 同步
  ② 空名 → 400；超长（>100 字）→ 400；不存在 → 404
  ③ 同名重复提交 → ok 且 changed=False（不重复写审计）
夹具：__rn_ 前缀看板 + 1 张卡（API 建，finally 删板清干净，§3.3）
"""
import json, os, sys, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'
PASS, FAIL = 0, 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print('  PASS', m)
    else:
        FAIL += 1; print('  FAIL', m)


def call(method, path, token, body=None):
    safe = path.split('?')[0]
    query = urllib.parse.quote(path.split('?', 1)[1], safe='=&,') if '?' in path else ''
    path = safe + ('?' + query if query else '')
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    from app.app import make_token
    tk = make_token('admin')
    bid = None
    try:
        # 建夹具看板 + 一张卡
        st, r = call('POST', '/api/boards', tk, {'board_name': '__rn_改名测试看板', 'dept': '核算部'})
        ok(st == 200, '夹具看板创建')
        bid = r['board_id']
        st, r = call('POST', '/api/cards', tk, {'board_id': bid, 'card_name': '__rn_卡片',
                                                'fields': {}})
        ok(st == 200, '夹具事项创建')

        print('== ① 正常改名 ==')
        st, r = call('PUT', '/api/boards/%s/rename' % bid, tk, {'board_name': '__rn_新名字A'})
        ok(st == 200 and r.get('changed'), '接口返回 changed=True：%s' % r)
        st, d = call('GET', '/api/boards', tk)
        nb = [b for b in d['boards'] if b['board_id'] == bid]
        ok(nb and nb[0]['board_name'] == '__rn_新名字A', 'boards 表名称已更新：%s' % (nb[0]['board_name'] if nb else '?'))
        st, d = call('GET', '/api/cards?size=50&board_ids=' + bid, tk)
        ok(d['cards'] and d['cards'][0]['board_name'] == '__rn_新名字A',
           'cards 冗余 board_name 已同步：%s' % (d['cards'][0]['board_name'] if d['cards'] else '?'))

        print('== ② 非法输入 ==')
        st, r = call('PUT', '/api/boards/%s/rename' % bid, tk, {'board_name': '   '})
        ok(st == 400, '空名 → 400（%s）' % r.get('detail', ''))
        st, r = call('PUT', '/api/boards/%s/rename' % bid, tk, {'board_name': '长' * 101})
        ok(st == 400, '超长 → 400（%s）' % r.get('detail', ''))
        st, r = call('PUT', '/api/boards/__rn_not_exist__/rename', tk, {'board_name': 'x'})
        ok(st == 404, '看板不存在 → 404')

        print('== ③ 同名重复提交 ==')
        st, r = call('PUT', '/api/boards/%s/rename' % bid, tk, {'board_name': '__rn_新名字A'})
        ok(st == 200 and r.get('changed') is False, '同名 → ok 且 changed=False')

        print('\n结果：PASS=%d FAIL=%d' % (PASS, FAIL))
    finally:
        if bid:
            call('DELETE', '/api/boards/' + bid, tk)
        # 残留自查
        st, d = call('GET', '/api/boards', tk)
        left = [b['board_name'] for b in d['boards'] if b['board_name'].startswith('__rn_')]
        print('残留自查：%s（应为空）' % (left or '空'))
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
