# -*- coding: utf-8 -*-
"""T-191j 结算功能 API 测试：
① 事项转「已完成」→ cards.overdue_days 结算（逾期=正 / 提前=负 / 当天=0 / 无截止=NULL）
② done 状态下改截止日期 → 重算
③ 板块 completion 转「已完成」→ board_columns.overdue_days 结算（含 T-191i 完成门槛联动）
④ 离开 done 再回 done → 按新截止日重算
夹具：__t191j_ 前缀 + finally 清理 + 残留自查（纪律③）。
"""
import json, urllib.request, urllib.error, sys, os, sqlite3, datetime, atexit

BASE = 'http://127.0.0.1:8100'
P = '__t191j_'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
from app.app import make_token  # noqa: E402

N = []


def ok(cond, msg):
    N.append((bool(cond), msg))
    print(('  PASS ' if cond else '  x FAIL ') + msg, flush=True)


T0 = make_token('admin')
BID, CID = P + 'bid', P + 'cid'


def call(method, path, token=None, body=None):
    h = {'Authorization': 'Bearer ' + (token or T0)}
    data = None
    if body is not None:
        h['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def cleanup():
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'), timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    esc = chr(92)
    pat = '%' + P.replace('_', esc + '_') + '%'
    for t, col in (('cards', 'card_id'), ('cards', 'board_id'), ('board_columns', 'col_key'),
                   ('boards', 'board_id'), ('column_todos', 'col_key'), ('column_comments', 'col_key')):
        c.execute(f"DELETE FROM {t} WHERE {col} LIKE ? ESCAPE '{esc}'", (pat,))
    c.commit()
    left = 0
    for t, col in (('cards', 'card_id'), ('boards', 'board_id'), ('board_columns', 'col_key')):
        left += c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} LIKE ? ESCAPE '{esc}'", (pat,)).fetchone()[0]
    c.close()
    return left


atexit.register(lambda: print('残留自查: %d（应为 0）' % cleanup(), flush=True))


def setup():
    c = sqlite3.connect(os.path.join(ROOT, 'src', 'app.db'), timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    now = '2026-11-13 10:00:00'
    c.execute("INSERT INTO boards(board_id,board_name,owner,created_at) VALUES(?,?,?,?)",
              (BID, P + '看板', 'admin', now))
    c.execute("INSERT INTO board_columns(col_key,column_id,board_id,column_name,created_at,creator,year,completion,due_date)"
              " VALUES(?,?,?,?,?,?,?,?,?)",
              (BID + '::' + P + '板块', P + 'colid', BID, P + '板块', now, 'admin', '2026', 'open', ''))
    # 逾期 5 天（截止 5 天前）、提前 3 天（截止 3 天后）、当天（截止今天）、无截止
    today = datetime.date.today()
    mk = lambda off: (today + datetime.timedelta(days=off)).isoformat()
    for cid, due in ((P + 'c1', mk(-5)), (P + 'c2', mk(3)), (P + 'c3', mk(0)), (P + 'c4', '')):
        c.execute("INSERT INTO cards(card_id,board_id,board_name,column_id,column_name,card_name,status,created,deleted,version)"
                  " VALUES(?,?,?,?,?,?, 'open', ?, 0, 1)",
                  (cid, BID, P + '看板', P + 'colid', P + '板块', P + cid[-2:], now))
        if due:
            c.execute("UPDATE cards SET due=? WHERE card_id=?", (due, cid))
    c.commit()
    c.close()


def get_card(cid):
    s, r = call('GET', '/api/cards?card_id=' + cid)
    assert s == 200, (s, r)
    return r['cards'][0]


def get_col_meta():
    s, r = call('GET', '/api/cards?board_ids=' + BID + '&size=1')
    assert s == 200
    for c in r['columns']:
        if c['col_key'] == BID + '::' + P + '板块':
            return c
    return {}


def main():
    setup()
    today = datetime.date.today()
    mk = lambda off: (today + datetime.timedelta(days=off)).isoformat()

    print('① 事项转「已完成」结算', flush=True)
    s, r = call('PUT', '/api/cards/' + P + 'c1', T0, {'fields': {'status': 'done', 'status_name': '已完成'}})
    ok(s == 200, '逾期 5 天事项 → 设完成 200')
    ok(get_card(P + 'c1').get('overdue_days') == 5, '逾期完成 → +5（实际 %s）' % get_card(P + 'c1').get('overdue_days'))
    call('PUT', '/api/cards/' + P + 'c2', T0, {'fields': {'status': 'done', 'status_name': '已完成'}})
    ok(get_card(P + 'c2').get('overdue_days') == -3, '提前 3 天完成 → -3（实际 %s）' % get_card(P + 'c2').get('overdue_days'))
    call('PUT', '/api/cards/' + P + 'c3', T0, {'fields': {'status': 'done', 'status_name': '已完成'}})
    ok(get_card(P + 'c3').get('overdue_days') == 0, '当天完成 → 0（实际 %s）' % get_card(P + 'c3').get('overdue_days'))
    call('PUT', '/api/cards/' + P + 'c4', T0, {'fields': {'status': 'done', 'status_name': '已完成'}})
    ok(get_card(P + 'c4').get('overdue_days') is None, '无截止日期 → NULL（未结算）')
    ok(get_card(P + 'c1').get('status') == 'done', 'API 返回体自带 overdue_days（SELECT * 透传）')

    print('② done 状态下改截止日期 → 重算', flush=True)
    call('PUT', '/api/cards/' + P + 'c1', T0, {'fields': {'due': mk(-2)}})
    ok(get_card(P + 'c1').get('overdue_days') == 2, '截止改为 2 天前 → 重算 +2（实际 %s）' % get_card(P + 'c1').get('overdue_days'))

    print('③ 板块 completion 转「已完成」结算（含 T-191i 完成门槛）', flush=True)
    ck = BID + '::' + P + '板块'
    # 先把 c4 回退为未完成 → 完成门槛应拦截
    call('PUT', '/api/cards/' + P + 'c4', T0, {'fields': {'status': 'open', 'status_name': '未完成'}})
    s, r = call('PUT', '/api/columns', T0, {'col_key': ck, 'completion': 'done'})
    ok(s == 400, '板块下尚有未完成事项 → 完成门槛 400（实际 %s）' % s)
    call('PUT', '/api/cards/' + P + 'c4', T0, {'fields': {'status': 'done', 'status_name': '已完成'}})
    s, r = call('PUT', '/api/columns', T0, {'col_key': ck, 'completion': 'done'})
    ok(s == 200, '全部事项完成后 → 板块完成 200')
    ok(get_col_meta().get('overdue_days') is None, '板块无截止日期 → NULL（未结算，实际 %s）' % get_col_meta().get('overdue_days'))
    call('PUT', '/api/columns', T0, {'col_key': ck, 'due_date': mk(-7)})
    ok(get_col_meta().get('overdue_days') == 7, 'done 状态下板块设截止（7 天前）→ 重算 +7（实际 %s）' % get_col_meta().get('overdue_days'))
    call('PUT', '/api/columns', T0, {'col_key': ck, 'due_date': mk(4)})
    ok(get_col_meta().get('overdue_days') == -4, '板块截止改为 4 天后 → 重算 -4（实际 %s）' % get_col_meta().get('overdue_days'))
    s, r = call('PUT', '/api/columns', T0, {'col_key': ck, 'completion': 'open'})
    ok(s == 200 and get_col_meta().get('completion') == 'open', '板块回退「未完成」→ 200')
    ok(get_col_meta().get('overdue_days') == -4, '离开 done 旧结算值留档（不清空）')

    print('④ 回退后再完成 → 按当前截止日重算', flush=True)
    call('PUT', '/api/columns', T0, {'col_key': ck, 'due_date': mk(0)})
    ok(get_col_meta().get('overdue_days') == -4, '未完成态改截止 → 不结算（旧结算值 -4 留档不变，实际 %s）' % get_col_meta().get('overdue_days'))
    s, r = call('PUT', '/api/columns', T0, {'col_key': ck, 'completion': 'done'})
    ok(s == 200 and get_col_meta().get('overdue_days') == 0, '再转完成 → 当天结算 0（实际 %s）' % get_col_meta().get('overdue_days'))

    print('⑤ 结算不开放给前端字段写入口', flush=True)
    s, r = call('PUT', '/api/cards/' + P + 'c1', T0, {'fields': {'overdue_days': 999}})
    ok(s == 400, 'overdue_days 不可通过 fields 直写（不在 CARD_FIELDS → 400，实际 %s）' % s)

    fails = [m for c2, m in N if not c2]
    print('结果: PASS=%d FAIL=%d' % (len(N) - len(fails), len(fails)), flush=True)
    if fails:
        sys.exit(1)


if __name__ == '__main__':
    main()
