import json, urllib.request, ssl

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
BASE = 'https://123.207.252.195'

NAMES = {
    'hly': '何兰英', 'hqx': '何巧娴', 'lzq': '刘自琴', 'wtt': '吴婷婷',
    'wcm': '吴春梅', 'whx': '吴海霞', 'zqq': '周青青', 'txh': '唐晓慧',
    'ssn': '孙姗娜', 'zwt': '庄文婷', 'zym': '曾玉梅', 'lmz': '李梦子',
    'lbm': '林冰妹', 'lyy': '林园园', 'lsy': '林姝言', 'llq': '柳丽琴',
    'wwn': '王伟娜', 'tyl': '谭亚利', 'zcf': '郑超芳', 'clh': '陈莉红',
    'chf': '陈辉凤', 'hym': '黄玉梅', 'yh': '余河',
}


def api(path, token=None, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body)
    if body:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {'__err__': str(e)}


print(f"{'账号':6} {'姓名':6} {'角色':8} {'可见看板数':6} 看板")
print('-' * 78)
rows = []
for u, cn in NAMES.items():
    r = api('/api/login', data={'username': u, 'password': '600179'})
    if 'token' not in r:
        print(f'{u:6} {cn:6} 登录失败 {r}')
        continue
    tok = r['token']
    me = api('/api/me', token=tok)
    boards = me.get('boards') or []
    names = [b.get('board_name', '').replace('工作事项（2026年度）', '') for b in boards]
    print(f"{u:6} {cn:6} {str(r.get('role')):8} {len(boards):<8} {', '.join(names) or '（无）'}")
    rows.append((u, cn, r.get('role'), len(boards), names))

print()
print('=== 汇总 ===')
zero = [x for x in rows if x[3] == 0]
print('可见看板数为 0 的账号:', [(x[0], x[1]) for x in zero] or '无')
print('可见看板数分布:', {n: sum(1 for x in rows if x[3] == n) for n in sorted({x[3] for x in rows})})
can_edit = 0
for u, cn, role, nb, names in rows:
    tok = api('/api/login', data={'username': u, 'password': '600179'})['token']
    me = api('/api/me', token=tok)
    boards = me.get('boards') or []
    if any(b.get('can_edit') for b in boards):
        can_edit += 1
print('有可编辑看板的账号数:', can_edit, '/', len(rows))
