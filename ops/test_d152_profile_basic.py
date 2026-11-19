# -*- coding: utf-8 -*-
"""#152 个人界面基本信息字段：/api/me 回显 + /api/profile 保存/校验（API 层）"""
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, r'E:/WB缓存/2026-10-26-15-55-08/src')
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
BASE = 'http://127.0.0.1:8100'

PASS, FAIL = [], []
def ok(c, m):
    (PASS if c else FAIL).append(m)
    print(('  PASS ' if c else '  FAIL ') + m)

from app.app import make_token
tk = make_token('admin')

def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

def main():
    print('【① /api/me 返回新字段与 member_id】')
    st, me = api('GET', '/api/me')
    ok(st == 200, 'me 200')
    for k in ('member_id', 'gender', 'hire_date', 'birth_date', 'native_province', 'native_city', 'phone', 'political_status'):
        ok(k in me, 'me 含字段 %s（当前=%r）' % (k, me.get(k)))
    mid = me.get('member_id')

    print('【② 保存完整基本信息 → 回读】')
    body = {'avatar': '', 'photo': '', 'status_text': '',
            'gender': '男', 'hire_date': '2020-07-01', 'birth_date': '1995-03-15',
            'native_province': '浙江', 'native_city': '杭州', 'phone': '13800001111',
            'political_status': '中共党员'}
    st, d = api('POST', '/api/profile', body)
    ok(st == 200, '保存 200')
    ok(d.get('gender') == '男' and d.get('phone') == '13800001111', '响应回显字段')
    st, me2 = api('GET', '/api/me')
    ok(me2.get('hire_date') == '2020-07-01' and me2.get('birth_date') == '1995-03-15', 'me 读回日期')
    ok(me2.get('native_province') == '浙江' and me2.get('political_status') == '中共党员', 'me 读回籍贯/政治面貌')
    ok(me2.get('member_id') == mid, 'member_id 稳定（%r）' % me2.get('member_id'))

    print('【③ 校验：非法手机号 / 非法日期 / 超长】')
    st, d = api('POST', '/api/profile', dict(body, phone='12345'))
    ok(st == 400, '手机号 5 位 → 400：%s' % (d.get('detail') or ''))
    st, d = api('POST', '/api/profile', dict(body, hire_date='2020/07/01'))
    ok(st == 400, '入司时间斜杠格式 → 400')
    st, d = api('POST', '/api/profile', dict(body, birth_date='1995-02-30'))
    ok(st == 400, '出生日期 2月30日 → 400')
    st, d = api('POST', '/api/profile', dict(body, gender='未知'))
    ok(st == 200 and d.get('gender') == '', '性别非法值归空（不报错）')

    print('【④ 清空保存 → 全部归空】')
    empty = {'avatar': '', 'photo': '', 'status_text': '', 'gender': '', 'hire_date': '',
             'birth_date': '', 'native_province': '', 'native_city': '', 'phone': '', 'political_status': ''}
    st, d = api('POST', '/api/profile', empty)
    ok(st == 200, '清空保存 200')
    st, me3 = api('GET', '/api/me')
    ok(all(not me3.get(k) for k in ('gender', 'hire_date', 'birth_date', 'native_province', 'native_city', 'phone', 'political_status')),
       '全部字段归空')

    print('\n结果：PASS=%d FAIL=%d' % (len(PASS), len(FAIL)))

main()
