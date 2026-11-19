# -*- coding: utf-8 -*-
"""数据复盘核对（只读 · D4）：六大维度 + 封存元数据专项
输出：逐项核对结果 + 缺失/异常清单。不做任何写操作。"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else 'src/app.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row


def q(sql, args=()):
    try:
        return [dict(r) for r in c.execute(sql, args)]
    except Exception as e:
        return [('__ERROR__', str(e))]


def show(title, rows, note=''):
    print('\n### ' + title)
    if note:
        print('  说明: ' + note)
    for r in rows:
        print('   ', r)


print('=' * 64)
print('数据库复盘核对：', DB)

# ── A. 看板 ──
print('\n' + '=' * 20 + ' A. 看板（boards）' + '=' * 20)
cols = [r['name'] for r in q("PRAGMA table_info(boards)") if isinstance(r, dict)]
print('A0 表结构列:', cols)
show('A1 看板总数与封存分布',
     q("SELECT COUNT(*) AS 总数, SUM(archived) AS 已封存 FROM boards"))
show('A2 【缺失】封存元数据列（archived_at / archived_by）',
     [x for x in ('archived_at', 'archived_by') if x not in cols],
     '缺列 = 封存时间/操作人无处可查（用户复盘关注点）')
show('A3 已封存看板清单（仅标志位，无时间/操作人）',
     q("SELECT board_id, board_name, archived FROM boards WHERE archived=1"))
show('A4 看板负责人为空',
     q("SELECT board_id, board_name FROM boards WHERE owner='' OR owner IS NULL"))
show('A5 board_config 覆盖率（未登记配置的看板）',
     q("""SELECT b.board_id, b.board_name FROM boards b
          WHERE NOT EXISTS (SELECT 1 FROM board_config c WHERE c.board_id=b.board_id)"""))

# ── B. 配置（board_config）──
print('\n' + '=' * 20 + ' B. 配置（board_config）' + '=' * 20)
show('B1 status 分布（启用/封存 文本标记 vs boards.archived 双轨）',
     q("SELECT status, COUNT(*) AS n FROM board_config GROUP BY status"))
show('B2 【异常】双轨不一致：config.status=封存 但 boards.archived=0',
     q("""SELECT c.board_id, c.status, b.archived FROM board_config c
          JOIN boards b ON b.board_id=c.board_id
          WHERE c.status='封存' AND (b.archived=0 OR b.archived IS NULL)"""))
show('B3 【异常】双轨不一致：boards.archived=1 但 config.status=启用',
     q("""SELECT c.board_id, c.status, b.archived FROM board_config c
          JOIN boards b ON b.board_id=c.board_id
          WHERE (b.archived=1) AND c.status='启用'"""))
show('B4 dept_node_id 为 0/空（归属未落到节点）',
     q("SELECT board_id, dept, dept_node_id FROM board_config WHERE dept_node_id=0 OR dept_node_id IS NULL"))
show('B5 dept_node_id 指向不存在的架构节点',
     q("""SELECT c.board_id, c.dept_node_id FROM board_config c
          WHERE c.dept_node_id>0 AND NOT EXISTS
          (SELECT 1 FROM org_nodes n WHERE n.id=c.dept_node_id)"""))
show('B6 attr 枚举异常（应只 日常/专项）',
     q("SELECT board_id, attr FROM board_config WHERE attr NOT IN ('日常','专项')"))
show('B7 status 枚举异常（应只 启用/封存）',
     q("SELECT board_id, status FROM board_config WHERE status NOT IN ('启用','封存')"))

# ── C. 板块（board_columns）──
print('\n' + '=' * 20 + ' C. 板块（board_columns）' + '=' * 20)
show('C1 completion（板块完成情况）分布与空值',
     q("""SELECT COALESCE(NULLIF(completion,''),'(空)') AS completion, COUNT(*) AS n
          FROM board_columns GROUP BY completion"""))
show('C2 nature 分布',
     q("""SELECT COALESCE(NULLIF(nature,''),'(空)') AS nature, COUNT(*) AS n
          FROM board_columns GROUP BY nature"""))
show('C3 year 空值（板块无归属年份）',
     q("SELECT col_key, column_name FROM board_columns WHERE year='' OR year IS NULL"))
show('C4 col_key 与 board_id/name 不自洽（格式应为 board::name）',
     q("""SELECT col_key FROM board_columns
          WHERE col_key != board_id || '::' || column_name LIMIT 10"""))
show('C5 板块指向不存在的看板（孤儿板块）',
     q("""SELECT col_key, board_id FROM board_columns
          WHERE board_id NOT IN (SELECT board_id FROM boards) LIMIT 10"""))
show('C6 重复板块名（同看板同板块名）',
     q("""SELECT board_id, column_name, COUNT(*) AS n FROM board_columns
          GROUP BY board_id, column_name HAVING n>1 LIMIT 10"""))

# ── D. 事项（cards）──
print('\n' + '=' * 20 + ' D. 事项（cards）' + '=' * 20)
show('D1 status 分布（事项状态：处理中/已完成等）',
     q("""SELECT COALESCE(NULLIF(status,''),'(空)') AS status, COUNT(*) AS n
          FROM cards WHERE deleted=0 GROUP BY status"""))
show('D2 【异常】done 但 completed（完成时间）为空',
     q("""SELECT COUNT(*) AS n FROM cards
          WHERE deleted=0 AND status='done' AND (completed IS NULL OR completed='')"""))
show('D3 【异常】非 done 但 completed 有值',
     q("""SELECT COUNT(*) AS n FROM cards
          WHERE deleted=0 AND status<>'done' AND completed IS NOT NULL AND completed<>''"""))
show('D4 begin/due 双空（无起止日期的事项）',
     q("""SELECT COUNT(*) AS n FROM cards
          WHERE deleted=0 AND parent_id='' AND (begin='' OR begin IS NULL)"""))
show('D5 孤儿事项：board_id 不在 boards',
     q("""SELECT COUNT(*) AS n FROM cards
          WHERE deleted=0 AND board_id NOT IN (SELECT board_id FROM boards)"""))
show('D6 孤儿子事项：parent_id 指向不存在/已删卡',
     q("""SELECT COUNT(*) AS n FROM cards k
          WHERE deleted=0 AND parent_id<>'' AND NOT EXISTS
          (SELECT 1 FROM cards p WHERE p.card_id=k.parent_id AND p.deleted=0)"""))
show('D7 孤儿板块引用：column_id 指向不存在板块且 column_name 也空（主卡）',
     q("""SELECT COUNT(*) AS n FROM cards
          WHERE deleted=0 AND parent_id='' AND (column_id='' OR column_id IS NULL)
          AND (column_name='' OR column_name IS NULL)"""))
show('D8 overdue_days 分布（逾期结算异常值）',
     q("""SELECT COALESCE(CAST(overdue_days AS TEXT),'(空)') AS od, COUNT(*) AS n
          FROM cards WHERE deleted=0 GROUP BY od LIMIT 12"""))

# ── E. 架构 ──
print('\n' + '=' * 20 + ' E. 架构（org_nodes / org_appointments）' + '=' * 20)
show('E1 节点类型分布',
     q("SELECT node_type, COUNT(*) AS n FROM org_nodes GROUP BY node_type"))
show('E2 节点负责人为空（owner）',
     q("""SELECT id, name, node_type FROM org_nodes
          WHERE owner='' OR owner IS NULL LIMIT 10"""))
show('E3 任命指向不存在的节点/成员（孤儿任命）',
     q("""SELECT a.id, a.node_id, a.member_id, a.role_key FROM org_appointments a
          WHERE NOT EXISTS (SELECT 1 FROM org_nodes n WHERE n.id=a.node_id)
          OR NOT EXISTS (SELECT 1 FROM team_members m WHERE m.id=a.member_id) LIMIT 10"""))
show('E4 role_key 枚举分布',
     q("SELECT role_key, COUNT(*) AS n FROM org_appointments GROUP BY role_key"))
show('E5 owner 格式抽样（姓名/账号/多人分号混存）',
     q("""SELECT id, name, owner FROM org_nodes
          WHERE owner<>'' AND (owner LIKE '%;%') LIMIT 6"""))

# ── F. 用户 ──
print('\n' + '=' * 20 + ' F. 用户（users / team_members）' + '=' * 20)
show('F1 users 有而 team_members 无绑定（账号未关联成员）',
     q("""SELECT username, role FROM users
          WHERE NOT EXISTS (SELECT 1 FROM team_members m WHERE m.account=users.username)
          LIMIT 10"""))
show('F2 team_members 有而 users 无账号（成员未开通账号）',
     q("""SELECT name, account FROM team_members
          WHERE account<>'' AND NOT EXISTS
          (SELECT 1 FROM users u WHERE u.username=team_members.account) LIMIT 10"""))
show('F3 users.role 分布',
     q("SELECT role, COUNT(*) AS n FROM users GROUP BY role"))

# ── G. 个人偏好 ──
print('\n' + '=' * 20 + ' G. 个人偏好（user_prefs）' + '=' * 20)
show('G1 key 分布与 updated_at 时间范围',
     q("SELECT key, COUNT(*) AS n FROM user_prefs GROUP BY key"))
show('G2 sort_cfg 非法 JSON（解析失败的行）',
     q("SELECT username, substr(value,1,60) AS v FROM user_prefs WHERE key='sort_cfg'"))

print('\n' + '=' * 64)
print('核对完成（只读，未做任何修改）')
