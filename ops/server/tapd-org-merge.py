#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tapd-org-merge —— 按架构部门的选择性回滚合并（服务器端执行）

用法: tapd-org-merge.py <prod|dev> <snapshot_db> <board_id,board_id,...>

逻辑（单事务完成，范围外数据零接触）：
  1. 范围 = 指定 board_id 集合（由本地按快照库的 部门→看板绑定 计算后传入）
  2. 快照中该范围的卡 → INSERT OR REPLACE（恢复快照版本，列取两库交集）
  3. 当前库该范围有、快照中没有的活跃卡 → 软删除（deleted=1，可追溯可救回）
  4. 其余所有表/看板/部门数据不动

整库留底由调用方（db-sync-ctl.py）在合并前通过 tapd snap 完成。
stdout 末行输出统计 JSON：{"snapshot_rows":n,"soft_deleted":n,"range_alive_after":n}
"""
import sqlite3
import sys

ENV_DIR = {"prod": "/opt/tapd-workbench", "dev": "/opt/tapd-dev"}


def main():
    env, snap_path, boards_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    board_ids = [b.strip() for b in boards_arg.split(",") if b.strip()]
    if env not in ENV_DIR or not board_ids:
        print("[ERROR] 参数错误")
        return 2

    target_db = ENV_DIR[env] + "/app.db"
    ph = ",".join("?" * len(board_ids))

    cur = sqlite3.connect(target_db)
    cur.execute("ATTACH DATABASE ? AS snap", (snap_path,))

    # 两库 cards 列交集（快照可能来自旧版本代码，缺新列时按交集写）
    cur_cols = [r[1] for r in cur.execute("PRAGMA table_info(cards)")]
    snap_cols = [r[1] for r in cur.execute("PRAGMA snap.table_info(cards)")]
    cols = [c for c in cur_cols if c in snap_cols]
    collist = ",".join(cols)

    try:
        cur.execute("BEGIN")
        n_snap = cur.execute(
            "SELECT COUNT(*) FROM snap.cards WHERE board_id IN (%s)" % ph,
            board_ids).fetchone()[0]

        # ① 恢复/插入快照版本（INSERT OR REPLACE：存在即整行覆盖，不存在即插入）
        cur.execute(
            "INSERT OR REPLACE INTO cards (%s) SELECT %s FROM snap.cards WHERE board_id IN (%s)"
            % (collist, collist, ph), board_ids)

        # ② 范围内"当前有、快照没有"的活跃卡 → 软删（列表不可见，可救回）
        soft = cur.execute(
            "UPDATE cards SET deleted=1 WHERE board_id IN (%s) AND deleted=0 "
            "AND card_id NOT IN (SELECT card_id FROM snap.cards WHERE board_id IN (%s))"
            % (ph, ph), board_ids + board_ids).rowcount

        after_alive = cur.execute(
            "SELECT COUNT(*) FROM cards WHERE board_id IN (%s) AND deleted=0" % ph,
            board_ids).fetchone()[0]
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.execute("DETACH DATABASE snap")
        cur.close()

    print('{"snapshot_rows": %d, "soft_deleted": %d, "range_alive_after": %d}'
          % (n_snap, soft, after_alive))
    return 0


if __name__ == "__main__":
    sys.exit(main())
