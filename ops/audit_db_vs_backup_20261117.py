# -*- coding: utf-8 -*-
"""审计：当前库 vs 误删前备份（ops/backup_db_20261117_fixture.db）逐表比对。
目的：证明 11-17 的事故恢复是「行级回补」而非「整库回滚」——
  备份有而当前库缺的行，应恰好 = 故意清理的夹具行；
  当前库有而备份没有的行，应恰好 = 回补动作本身不产生、也无其他写入。
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'src', 'app.db')
BAK = os.path.join(os.path.dirname(__file__), 'backup_db_20261117_fixture.db')

cur = sqlite3.connect(DB)
bak = sqlite3.connect(BAK)
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

print(f"{'表':<22}{'备份行数':>8}{'当前行数':>8}  差异明细")
print('-' * 78)
total_missing, total_extra = 0, 0
for t in tables:
    try:
        cols = [r[1] for r in cur.execute(f'PRAGMA table_info({t})')]
        if not cols:
            continue
        pk = cols[0]                       # 用首列做粗比对（rowid/id/card_id 等）
        bset = {r[0] for r in bak.execute(f'SELECT [{pk}] FROM [{t}]')}
        cset = {r[0] for r in cur.execute(f'SELECT [{pk}] FROM [{t}]')}
        missing = bset - cset              # 备份有、当前没有 → 疑似丢失
        extra = cset - bset                # 当前有、备份没有 → 备份后新写入
        n_b, n_c = len(bset), len(cset)
        if missing or extra or n_b != n_c:
            detail = []
            if missing:
                sample = list(missing)[:5]
                detail.append(f'备份独有{len(missing)}行(如{sample})')
            if extra:
                sample = list(extra)[:5]
                detail.append(f'当前独有{len(extra)}行(如{sample})')
            print(f'{t:<22}{n_b:>8}{n_c:>8}  ' + '; '.join(detail))
            total_missing += len(missing)
            total_extra += len(extra)
        else:
            print(f'{t:<22}{n_b:>8}{n_c:>8}  一致')
    except Exception as e:
        print(f'{t:<22}        比对异常: {e}')
print('-' * 78)
print(f'合计：备份独有 {total_missing} 行 / 当前独有 {total_extra} 行')

# 抽查关键实体：BCP 看板与板块逐行内容一致
print('\n== BCP1793717004248 行级内容核对 ==')
same = 0
for t in ('boards', 'board_columns'):
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info({t})')]
    b_rows = {r[0]: tuple(r) for r in bak.execute(
        f"SELECT {','.join(cols)} FROM {t} WHERE board_id='BCP1793717004248'")}
    c_rows = {r[0]: tuple(r) for r in cur.execute(
        f"SELECT {','.join(cols)} FROM {t} WHERE board_id='BCP1793717004248'")}
    diff = [k for k in b_rows if b_rows[k] != c_rows.get(k)]
    print(f'{t}: 备份 {len(b_rows)} 行 / 当前 {len(c_rows)} 行 / 内容不一致 {len(diff)} 行 {diff[:3]}')
    same += len(diff)
print('BCP 内容与备份完全一致' if same == 0 else '⚠️ BCP 行内容有差异！')
cur.close(); bak.close()
