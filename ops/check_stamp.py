#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TAPD 工作台 · 验证凭证校验器（sync.sh 门禁调用）

用法: python check_stamp.py <stamp路径> <src目录> <最大有效期秒数>
输出（供 shell 解析）:
  OK <验证时间>            凭证有效
  STALE <旧> -> <新>       代码已变更，凭证失效
  EXPIRED <验证时间>        凭证过期
  BAD <原因>               凭证损坏/无法解析
"""
import json
import os
import sys
import time
import hashlib


def code_fingerprint(src):
    h = hashlib.sha256()
    targets = []
    for d in ("app", "static"):
        base = os.path.join(src, d)
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
            for fn in sorted(files):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                targets.append(os.path.join(root, fn))
    # T-013f：精灵图片是静态资产（走 sync.sh --pets 独立通道同步），
    #   不参与代码指纹 —— 否则图片微调会使验证凭证失效、被迫重跑 verify.py
    targets = [t for t in targets
               if os.path.relpath(t, src).replace("\\", "/") != "static/pokemon_sprites"]
    for extra in ("requirements.txt", "manage_users.py"):
        p = os.path.join(src, extra)
        if os.path.exists(p):
            targets.append(p)
    for p in sorted(targets):
        rel = os.path.relpath(p, src).replace("\\", "/")
        try:
            with open(p, "rb") as f:
                h.update(rel.encode() + b":" + hashlib.sha256(f.read()).digest())
        except OSError:
            continue
    return h.hexdigest()


def main():
    if len(sys.argv) < 4:
        print("BAD usage")
        return 0
    stamp_path, src, max_age = sys.argv[1], sys.argv[2], int(sys.argv[3])
    try:
        with open(stamp_path, encoding="utf-8") as f:
            st = json.load(f)
    except Exception as e:
        print("BAD " + str(e)[:60])
        return 0

    cur = code_fingerprint(src)
    if cur != st.get("fingerprint"):
        print("STALE " + str(st.get("fingerprint", ""))[:12] + " -> " + cur[:12])
        return 0
    age = int(time.time()) - int(st.get("timestamp", 0))
    if age > max_age:
        print("EXPIRED " + str(st.get("verified_at", "")))
        return 0
    print("OK " + str(st.get("verified_at", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
