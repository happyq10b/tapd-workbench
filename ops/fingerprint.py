#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码指纹（内容哈希）—— 本地与服务器共用的唯一实现

用法:
    python ops/fingerprint.py <src_dir>      # 打印指纹（hex）

★ 为什么要归一化 CRLF：
  同步时会把代码里的 CRLF 转成 LF 再推上服务器（Windows 编辑器会写入 CRLF，
  Linux 侧统一 LF 更稳）。如果不归一化，服务器上的内容指纹就永远和本地
  不一致 —— 「验证通过的代码」与「实际部署的代码」对不上号，门禁形同虚设。
  所以三处（verify.py / check_stamp.py / 本文件）统一在哈希前做 CRLF→LF。

★ 算法一旦改动，必须三处同步改，否则门禁会误判。
"""
import hashlib
import os
import sys

# 与同步范围严格一致：app/ + static/ + 两个根文件
SCAN_DIRS = ("app", "static")
SCAN_FILES = ("requirements.txt", "manage_users.py")


def _normalize(data):
    """CRLF → LF（只影响行尾，不动其它字节）"""
    return data.replace(b"\r\n", b"\n")


def code_fingerprint(src):
    """对被同步的代码内容取指纹（只看内容，不看 mtime）"""
    h = hashlib.sha256()
    targets = []
    for d in SCAN_DIRS:
        base = os.path.join(src, d)
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
            for fn in sorted(files):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                targets.append(os.path.join(root, fn))
    for extra in SCAN_FILES:
        p = os.path.join(src, extra)
        if os.path.exists(p):
            targets.append(p)
    for p in sorted(targets):
        rel = os.path.relpath(p, src).replace("\\", "/")
        try:
            with open(p, "rb") as f:
                data = _normalize(f.read())
        except OSError:
            continue
        h.update(rel.encode() + b":" + hashlib.sha256(data).digest())
    return h.hexdigest()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fingerprint.py <src_dir>", file="utf-8" and sys.stderr)
        sys.exit(2)
    print(code_fingerprint(sys.argv[1]))
