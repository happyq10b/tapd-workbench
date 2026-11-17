#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片资源快照与回滚管理（T-193，2026-11-13）

快照范围（全部为 app.db 内 data URL 范式的图片资源）：
  1. 精灵设置区：pet_zones（分区）+ pet_images（上传图）+ app_settings.login_pet（登录页精灵配置）
  2. 用户头像：users.avatar
  3. 用户照片：users.photo

目录约定：
  本地快照库  data/img-snapshots/<env>/<YYYYMMDD-HHMMSS>/
                manifest.json   元信息（来源/时间/各项计数/字节数）
                payload.json    权威数据（data URL 原文，应用回滚以它为准）
                preview/        解码后的图片文件（仅供人工查看，非权威）
  服务器存档  /var/backups/tapd-workbench/img-snapshots/<env>/<ts>/payload.json
  自动快照配置 data/img-snapshots/auto.json（enabled / interval_min / keep）
  自动快照日志 data/img-snapshots/auto.log

安全约定：
  - 一切 apply 前自动做一次「应用前留底」快照（pre-apply-<ts>，不参与按份数清理）；
  - prod/dev 应用需交互双确认（或 CLI 传 --yes 跳过，仅建议脚本场景）；
  - 应用是「行内 UPDATE + 精灵区整体替换」的事务，不整库替换，不碰其它业务数据；
  - 快照中不存在、而当前库中新出现的账号不动（非破坏性回滚）。

本地用法：
  python img_snapshot.py export --env local            本地库快照
  python img_snapshot.py export --env prod|dev         服务器导出存档并拉回本地
  python img_snapshot.py pull  prod|dev [ts]           把服务器已有快照拉到本地
  python img_snapshot.py apply local|prod|dev <ts> [--yes]   应用本地快照
  python img_snapshot.py list [env]                    快照清单
  python img_snapshot.py prune <env> --keep N          本地按份数清理
  python img_snapshot.py delete local [ts] [--snap DIR] [--yes]   删除本地快照
  python img_snapshot.py delete prod|dev [ts] [--yes]  删除服务器快照
  python img_snapshot.py auto                          计划任务入口（静默）
  python img_snapshot.py auto-config                   交互设置开关/间隔/份数/计划任务
远端用法（由本地推上去执行）：
  python3 img_snapshot.py export --env prod --db <path> --out <dir>   --remote
  python3 img_snapshot.py remote-apply --db <path> --payload <file> --env prod
"""
import argparse
import base64
import glob
import json
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAP_ROOT = os.path.join(ROOT, "data", "img-snapshots")
LOCAL_DB = os.path.join(ROOT, "src", "app.db")
AUTO_CFG = os.path.join(SNAP_ROOT, "auto.json")
AUTO_LOG = os.path.join(SNAP_ROOT, "auto.log")
AUTO_LOCK = os.path.join(SNAP_ROOT, ".auto.lock")
TASK_NAME = "FISP-ImgSnap-Prod"
ENV_DIR = {"prod": "/opt/tapd-workbench", "dev": "/opt/tapd-dev"}     # 与 db-sync-ctl 同口径
REMOTE_IMG_ROOT = "/var/backups/tapd-workbench/img-snapshots"         # 服务器侧存档根
PAYLOAD_MAGIC = "fisp-img-snapshot"
PAYLOAD_VERSION = 1
TS_PAT = re.compile(r"^\d{8}-\d{6}$")
DATAURL_PAT = re.compile(
    r"^data:image/(png|jpeg|jpg|gif|webp|bmp|x-icon|svg\+xml);base64,[A-Za-z0-9+/=\r\n]+$")

EXT_BY_MIME = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "gif": "gif", "webp": "webp",
               "bmp": "bmp", "x-icon": "ico", "svg+xml": "svg"}


def _out(s):
    """控制台输出：GBK 控制台下不可编码字符替换输出，避免崩溃。"""
    try:
        sys.stdout.write(s + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.write(s.encode(enc, errors="replace").decode(enc) + "\n")
        sys.stdout.flush()


def _dw(s):
    """显示宽度：CJK/全角按 2 列，其余按 1 列（用于表格对齐）。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def _pad(s, n):
    s = str(s)
    return s + " " * max(0, n - _dw(s))


def _builtin_count():
    """内置宝可梦精灵数量（src/static/pokemon_sprites，静态资产不入库，仅作口径展示）。"""
    d = os.path.join(ROOT, "src", "static", "pokemon_sprites")
    try:
        return len([f for f in os.listdir(d) if f.lower().endswith(".png")])
    except OSError:
        return 0


def _rel(p):
    """相对 ROOT 的展示路径；跨盘符（如 TEMP 在 C:）时回退绝对路径。"""
    try:
        return os.path.relpath(p, ROOT)
    except ValueError:
        return str(p)


def now_ts():
    return time.strftime("%Y%m%d-%H%M%S")


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 远端通道（复用 db-sync-ctl 的成熟封装） ----------------
def _remote_ctl():
    """延迟导入 db-sync-ctl（文件名带连字符，importlib 装载），拿 ssh/scp/ENV_DIR。"""
    import importlib.util
    path = os.path.join(HERE, "db-sync-ctl.py")
    spec = importlib.util.spec_from_file_location("db_sync_ctl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def remote_db_path(ctl, env):
    """探测服务器上 app.db 的真实路径（prod: /opt/tapd-workbench/app.db）。"""
    base = ctl.ENV_DIR[env]
    cands = ["%s/app.db" % base, "%s/src/app.db" % base, "%s/data/app.db" % base]
    rc, out = ctl.ssh_run(
        'for f in %s; do test -f "$f" && echo "$f" && break; done' % " ".join(cands), timeout=30)
    p = out.strip().splitlines()
    if rc == 0 and p and p[0].strip():
        return p[0].strip()
    rc, out = ctl.ssh_run(
        "find %s -maxdepth 3 -name 'app.db' -not -path '*snap*' 2>/dev/null | head -1" % base, timeout=30)
    p = [x.strip() for x in out.splitlines() if x.strip()]
    if rc == 0 and p:
        return p[0]
    _out("[ERROR] 未能在服务器 %s 下定位 app.db（探测过：%s）" % (base, ", ".join(cands)))
    sys.exit(1)


def remote_python(ctl, env):
    """优先用应用自带 venv 的 python（版本一致），回退系统 python3。"""
    base = ctl.ENV_DIR[env]
    rc, out = ctl.ssh_run(
        'for f in %s/venv/bin/python %s/venv/bin/python3 /usr/bin/python3; do '
        'test -x "$f" && echo "$f" && break; done' % (base, base), timeout=30)
    p = [x.strip() for x in out.splitlines() if x.strip()]
    return p[0] if (rc == 0 and p) else "python3"


# ---------------- payload 提取 / 校验 ----------------
def open_consistent(db_path):
    """sqlite backup API 取一致性只读副本（源库被服务占用也安全，不停服）。"""
    src = sqlite3.connect(db_path, timeout=20)
    try:
        dst = sqlite3.connect(":memory:")
        src.backup(dst)
        return dst
    finally:
        src.close()


def extract_payload(db_path, source):
    con = open_consistent(db_path)
    con.row_factory = sqlite3.Row
    try:
        pet = {
            "login_pet": None,
            "zones": [dict(r) for r in con.execute("SELECT id,name,sort,created_at FROM pet_zones ORDER BY sort,id")],
            "images": [dict(r) for r in con.execute(
                "SELECT id,zone,name,data,sort,created_by,created_at FROM pet_images ORDER BY zone,sort,id")],
        }
        row = con.execute("SELECT value FROM app_settings WHERE key='login_pet'").fetchone()
        if row:
            pet["login_pet"] = row["value"]
        users = {}
        for r in con.execute("SELECT username, avatar, photo FROM users ORDER BY username"):
            users[r["username"]] = {"avatar": r["avatar"] or "", "photo": r["photo"] or ""}
        payload = {
            "kind": PAYLOAD_MAGIC,
            "version": PAYLOAD_VERSION,
            "source": source,
            "source_db": os.path.normpath(db_path),
            "created_at": now_str(),
            "pet": pet,
            "users": users,
        }
        counts = {
            "pet_zones": len(pet["zones"]),
            "pet_images": len(pet["images"]),
            "login_pet": bool(pet["login_pet"]),
            "users": len(users),
            "users_avatar": sum(1 for u in users.values() if u["avatar"]),
            "users_photo": sum(1 for u in users.values() if u["photo"]),
        }
        return payload, counts
    finally:
        con.close()


def validate_payload(payload, parts=None):
    """结构 + data URL 合法性校验（应用前的最后防线）。只校验将应用的大类
    （parts=None 视为全部）。返回错误列表。"""
    parts = _norm_parts(parts) or {"pet", "avatar", "photo"}
    errs = []
    if not isinstance(payload, dict) or payload.get("kind") != PAYLOAD_MAGIC:
        errs.append("payload 结构不合法（缺少 kind=%s 标识）" % PAYLOAD_MAGIC)
        return errs
    if int(payload.get("version") or 0) != PAYLOAD_VERSION:
        errs.append("payload 版本不兼容（%s ≠ %s）" % (payload.get("version"), PAYLOAD_VERSION))
    pet = payload.get("pet") or {}
    if "pet" in parts:
        for z in pet.get("zones") or []:
            if not (z.get("name") or "").strip():
                errs.append("精灵分区存在空名称（id=%s）" % z.get("id"))
        for im in pet.get("images") or []:
            if not DATAURL_PAT.match(im.get("data") or ""):
                errs.append("精灵图 #%s（%s）data URL 非法" % (im.get("id"), im.get("name") or im.get("zone")))
        lp = pet.get("login_pet")
        if lp and not isinstance(lp, str):
            errs.append("login_pet 配置非字符串")
    users = payload.get("users") or {}
    for acc, f in users.items():
        if "avatar" in parts and (f.get("avatar") or "") and not DATAURL_PAT.match(f["avatar"]):
            errs.append("用户 %s 的头像 data URL 非法" % acc)
        if "photo" in parts and (f.get("photo") or "") and not DATAURL_PAT.match(f["photo"]):
            errs.append("用户 %s 的照片 data URL 非法" % acc)
    return errs


CAT_LABEL = {"pet": "精灵图", "avatar": "头像", "photo": "照片"}


def _norm_parts(parts):
    """归一化大类选择：'1/2/3/A/pet/avatar/photo/all'（逗号分隔）→ 集合。"""
    if parts is None:
        return None
    if isinstance(parts, str):
        parts = [x.strip() for x in parts.split(",") if x.strip()]
    out = set()
    for x in parts or []:
        x = str(x).strip().lower()
        if x in ("1", "pet"):
            out.add("pet")
        elif x in ("2", "avatar"):
            out.add("avatar")
        elif x in ("3", "photo"):
            out.add("photo")
        elif x in ("a", "all"):
            out |= {"pet", "avatar", "photo"}
    return out or None


def choose_parts():
    """交互选择要应用的大类（可多选）。"""
    _out("选择要应用的大类：[1] 精灵图（分区/上传图/登录页配置）  [2] 头像  [3] 照片  [A] 全部")
    v = input("输入序号（可多选，逗号分隔；回车=全部）：").strip()
    parts = _norm_parts(v if v else "all")
    if not parts:
        _out("[ERROR] 未选择任何有效大类")
        sys.exit(1)
    _out("    将应用：" + "、".join(CAT_LABEL[c] for c in ("pet", "avatar", "photo") if c in parts))
    return parts


def decode_preview(dataurl, path):
    m = re.match(r"^data:image/([a-z0-9+-]+);base64,([A-Za-z0-9+/=\r\n]+)$", dataurl or "")
    if not m:
        return False
    ext = EXT_BY_MIME.get(m.group(1))
    if not ext:
        return False
    try:
        raw = base64.b64decode(m.group(2), validate=False)
        with open(path, "wb") as f:
            f.write(raw)
        return True
    except Exception:
        return False


def regen_preview(snap_dir, payload=None):
    """从 payload 重建 preview/ 目录（拉回本地的快照不带 preview，本地重建）。"""
    if payload is None:
        with open(os.path.join(snap_dir, "payload.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
    pv = os.path.join(snap_dir, "preview")
    for sub in ("avatars", "photos", "pet"):
        os.makedirs(os.path.join(pv, sub), exist_ok=True)
    n = 0
    for acc, f in (payload.get("users") or {}).items():
        safe = re.sub(r"[^A-Za-z0-9_\-.一-龥]", "_", acc)
        if f.get("avatar") and decode_preview(f["avatar"], os.path.join(pv, "avatars", safe + ".png")):
            n += 1
        if f.get("photo") and decode_preview(f["photo"], os.path.join(pv, "photos", safe + ".png")):
            n += 1
    for im in (payload.get("pet") or {}).get("images") or []:
        z = re.sub(r"[^A-Za-z0-9_\-.一-龥]", "_", im.get("zone") or "zone")
        if decode_preview(im.get("data"), os.path.join(pv, "pet", "%s_%s.png" % (z, im.get("id")))):
            n += 1
    return n


def write_snapshot(snap_dir, payload, counts, source):
    os.makedirs(os.path.join(snap_dir, "preview"), exist_ok=True)
    pj = os.path.join(snap_dir, "payload.json")
    with open(pj, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    manifest = {
        "kind": PAYLOAD_MAGIC, "version": PAYLOAD_VERSION,
        "created_at": payload["created_at"], "source": source,
        "source_db": payload["source_db"], "counts": counts,
        "payload_bytes": os.path.getsize(pj),
    }
    with open(os.path.join(snap_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    n = regen_preview(snap_dir, payload)
    return manifest, n


def export_local(env, db_path=None, out_dir=None):
    db_path = db_path or LOCAL_DB
    if not os.path.exists(db_path):
        _out("[ERROR] 数据库不存在：%s" % db_path)
        sys.exit(1)
    ts = now_ts()
    # out_dir：测试/演练用隔离根（保持 <根>/<env>/<ts> 结构一致）
    base = os.path.join(out_dir, env) if out_dir else os.path.join(SNAP_ROOT, env)
    snap_dir = os.path.join(base, ts)
    k = 1
    while os.path.exists(snap_dir):
        k += 1
        snap_dir = os.path.join(base, "%s-%d" % (ts, k))
    _out("==> 提取图片资源（sqlite backup API 一致性读取，不停服）")
    payload, counts = extract_payload(db_path, env)
    manifest, n_prev = write_snapshot(snap_dir, payload, counts, env)
    _out("==> 快照完成：%s" % _rel(snap_dir))
    _out("    精灵：%d 分区 / %d 图 / login_pet=%s；头像 %d、照片 %d（%d 个账号）"
         % (counts["pet_zones"], counts["pet_images"], "有" if counts["login_pet"] else "无",
            counts["users_avatar"], counts["users_photo"], counts["users"]))
    _out("    权威数据 payload.json（%d bytes）+ 预览图 %d 张" % (manifest["payload_bytes"], n_prev))
    return snap_dir


# ---------------- 远端导出（服务器存档 + 拉回本地） ----------------
def export_remote(env, pull_to_local=True):
    """生产/开发图片快照：服务器侧导出存档 + 按份数清理。
    pull_to_local=True（人工操作）时把 payload/manifest 拉回本地并重建预览；
    False（自动任务 #107 口径）= 纯服务器侧，不拉本地。"""
    ctl = _remote_ctl()
    ts = now_ts()
    remote_dir = "%s/%s/%s" % (REMOTE_IMG_ROOT, env, ts)
    tmp = "/tmp/imgsnap-%s" % ts
    dbp = remote_db_path(ctl, env)
    py = remote_python(ctl, env)
    _out("==> [1/4] 上传导出脚本到服务器 %s（DB=%s）" % (env, dbp))
    ctl.ssh_run("mkdir -p %s %s" % (remote_dir, tmp), timeout=30)
    ctl.scp_push(os.path.abspath(__file__), "%s/img_snapshot.py" % tmp, timeout=120)
    _out("==> [2/4] 服务器导出图片资源（backup API 一致性读取，不停服）")
    rc, out = ctl.ssh_run(
        "cd %s && %s img_snapshot.py export --env %s --db %s --out %s --remote"
        % (tmp, py, env, dbp, remote_dir), timeout=300)
    if rc != 0:
        ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
        _out("[ERROR] 服务器导出失败（rc=%s）" % rc)
        _out(out[-800:])
        sys.exit(1)
    _out("    " + "\n    ".join([x for x in out.splitlines() if x.strip()][-6:]))
    probe = ctl.ssh_run('test -f "%s/payload.json" && echo Y' % remote_dir, timeout=30)[1]
    if "Y" not in probe:
        ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
        _out("[ERROR] 服务器侧 payload.json 未生成，导出中止")
        sys.exit(1)
    if pull_to_local:
        _out("==> [3/4] 拉回本地（payload + manifest，preview 本地重建）")
        local_dir = os.path.join(SNAP_ROOT, env, ts)
        os.makedirs(local_dir, exist_ok=True)
        ctl.scp_pull("%s/payload.json" % remote_dir, os.path.join(local_dir, "payload.json"), timeout=300)
        ctl.scp_pull("%s/manifest.json" % remote_dir, os.path.join(local_dir, "manifest.json"), timeout=60)
        ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
        with open(os.path.join(local_dir, "payload.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
        n_prev = regen_preview(local_dir, payload)
        _out("==> [4/4] 完成")
        _out("    服务器存档：%s:%s" % (env, remote_dir))
        _out("    本地快照  ：%s" % _rel(local_dir))
        _out("    预览图 %d 张已本地重建" % n_prev)
        return local_dir
    # 自动任务口径（#107）：纯服务器侧，不拉本地
    ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
    _out("==> [3/3] 完成（自动任务口径：仅服务器侧存档，不拉本地）")
    _out("    服务器存档：%s:%s" % (env, remote_dir))
    return remote_dir


def remote_list(env):
    ctl = _remote_ctl()
    rc, out = ctl.ssh_run(
        "ls -1 %s/%s 2>/dev/null | grep -E '^[0-9]{8}-[0-9]{6}$|pre-apply' | sort -r" % (REMOTE_IMG_ROOT, env),
        timeout=30)
    return [x.strip() for x in out.splitlines() if x.strip()]


def cmd_pull(env, ts=None):
    ctl = _remote_ctl()
    snaps = remote_list(env)
    snaps = [s for s in snaps if TS_PAT.match(s)]
    if not snaps:
        _out("[ERROR] 服务器 %s 尚无图片快照（先执行导出）" % env)
        sys.exit(1)
    if not ts:
        _out("服务器 %s 可用快照（新→旧）：" % env)
        for i, s in enumerate(snaps):
            _out("  [%d] %s" % (i + 1, s))
        v = input("选择序号（回车=1）：").strip() or "1"
        try:
            ts = snaps[int(v) - 1]
        except (ValueError, IndexError):
            _out("[ERROR] 序号不合法")
            sys.exit(1)
    if ts not in snaps:
        _out("[ERROR] 服务器上不存在快照 %s" % ts)
        sys.exit(1)
    remote_dir = "%s/%s/%s" % (REMOTE_IMG_ROOT, env, ts)
    local_dir = os.path.join(SNAP_ROOT, env, ts)
    os.makedirs(local_dir, exist_ok=True)
    _out("==> 拉取 %s → %s" % (remote_dir, _rel(local_dir)))
    ctl.scp_pull("%s/payload.json" % remote_dir, os.path.join(local_dir, "payload.json"), timeout=300)
    rc, _ = ctl.ssh_run('test -f "%s/manifest.json" && echo Y' % remote_dir, timeout=30)
    if rc == 0:
        ctl.scp_pull("%s/manifest.json" % remote_dir, os.path.join(local_dir, "manifest.json"), timeout=60)
    with open(os.path.join(local_dir, "payload.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)
    n = regen_preview(local_dir, payload)
    _out("==> 完成（预览图 %d 张本地重建）" % n)


# ---------------- 应用（回滚） ----------------
def apply_payload(db_path, payload, env_label, quiet=False, pre_snapshot=True, parts=None,
                  pre_dir_base=None):
    """把 payload 应用进 db_path（事务）。parts 限定大类（pet/avatar/photo），None=全部。
    pre_dir_base：留底目录的父目录（缺省=快照库对应 env 目录；测试/演练传隔离目录）。
    返回 (changed dict, pre_dir)。"""
    parts = _norm_parts(parts) or {"pet", "avatar", "photo"}
    errs = validate_payload(payload, parts)
    if errs:
        for e in errs[:8]:
            _out("  [X] " + e)
        _out("[ERROR] 快照校验未通过（共 %d 处），已中止，未改动数据库" % len(errs))
        sys.exit(1)
    con = sqlite3.connect(db_path, timeout=20)
    con.execute("PRAGMA busy_timeout=20000")
    con.row_factory = sqlite3.Row
    try:
        need = {"users", "app_settings", "pet_zones", "pet_images"}
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        miss = need - have
        if miss:
            _out("[ERROR] 目标库缺少数据表：%s（请先启动一次服务完成建表）" % ",".join(sorted(miss)))
            sys.exit(1)
        ts = now_ts()
        pre_dir = None
        if pre_snapshot:
            pre_dir = os.path.join(pre_dir_base or os.path.join(SNAP_ROOT, env_label), "pre-apply-" + ts)
            # 应用前留底（write_snapshot 需 (payload, counts)；extract 返回 (payload, counts)）
            pre_payload, pre_counts = extract_payload(db_path, env_label)
            write_snapshot(pre_dir, pre_payload, pre_counts, env_label)
            _out("==> 应用前留底：%s" % _rel(pre_dir))
        if not quiet:
            _out("==> 应用快照（%s；事务内执行，失败自动回滚）"
                 % "、".join(CAT_LABEL[c] for c in ("pet", "avatar", "photo") if c in parts))
        cur = con.cursor()
        changed = {"pet": 0, "avatar": 0, "photo": 0}
        pet = payload.get("pet") or {}
        users = payload.get("users") or {}
        try:
            cur.execute("BEGIN")
            # 精灵设置区：整体替换（分区/图片/登录页配置）——仅当选中「精灵图」大类
            if "pet" in parts:
                cur.execute("DELETE FROM pet_images")
                cur.execute("DELETE FROM pet_zones")
                for z in pet.get("zones") or []:
                    cur.execute("INSERT INTO pet_zones (id,name,sort,created_at) VALUES (?,?,?,?)",
                                (z.get("id"), z.get("name"), z.get("sort") or 0, z.get("created_at") or ""))
                for im in pet.get("images") or []:
                    cur.execute("INSERT INTO pet_images (id,zone,name,data,sort,created_by,created_at) "
                                "VALUES (?,?,?,?,?,?,?)",
                                (im.get("id"), im.get("zone"), im.get("name") or "", im.get("data"),
                                 im.get("sort") or 0, im.get("created_by") or "", im.get("created_at") or ""))
                seq = cur.execute("SELECT seq FROM sqlite_sequence WHERE name='pet_images'").fetchone()
                max_id = max([int(im.get("id") or 0) for im in (pet.get("images") or [])] or [0])
                if seq and int(seq["seq"]) < max_id:
                    cur.execute("UPDATE sqlite_sequence SET seq=? WHERE name='pet_images'", (max_id,))
                elif not seq and max_id:
                    cur.execute("INSERT INTO sqlite_sequence (name,seq) SELECT 'pet_images',? "
                                "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='pet_images')", (max_id,))
                cur.execute("DELETE FROM app_settings WHERE key='login_pet'")
                if pet.get("login_pet"):
                    cur.execute("INSERT INTO app_settings (key,value) VALUES ('login_pet',?)", (pet["login_pet"],))
                changed["pet"] = 1
            # 头像/照片：仅覆盖快照中存在的账号、仅更新选中字段；值相同的跳过
            if "avatar" in parts or "photo" in parts:
                db_users = {r["username"] for r in cur.execute("SELECT username FROM users")}
                skip = [a for a in users if a not in db_users]
                for acc, f in users.items():
                    if acc not in db_users:
                        continue
                    row = cur.execute("SELECT avatar,photo FROM users WHERE username=?", (acc,)).fetchone()
                    sets, vals = [], []
                    if "avatar" in parts and (row["avatar"] or "") != (f.get("avatar") or ""):
                        sets.append("avatar=?")
                        vals.append(f.get("avatar") or "")
                        changed["avatar"] += 1
                    if "photo" in parts and (row["photo"] or "") != (f.get("photo") or ""):
                        sets.append("photo=?")
                        vals.append(f.get("photo") or "")
                        changed["photo"] += 1
                    if sets:
                        vals.append(acc)
                        cur.execute("UPDATE users SET %s WHERE username=?" % ",".join(sets), vals)
            con.commit()
        except Exception:
            con.rollback()
            raise
        msgs = []
        if "pet" in parts:
            msgs.append("精灵图已还原（%d 分区 / %d 图 / login_pet=%s）"
                        % (len(pet.get("zones") or []), len(pet.get("images") or []),
                           "有" if pet.get("login_pet") else "无"))
        if "avatar" in parts:
            msgs.append("头像 %d 个账号更新" % changed["avatar"])
        if "photo" in parts:
            msgs.append("照片 %d 个账号更新" % changed["photo"])
        if ("avatar" in parts or "photo" in parts) and skip:
            msgs.append("%d 个快照外账号未动" % len(skip))
        _out("==> 应用完成：" + "；".join(msgs))
        return changed, pre_dir
    finally:
        con.close()


def find_local_snap(ts):
    """在本地快照库所有 env 下找 ts 目录。"""
    for d in sorted(glob.glob(os.path.join(SNAP_ROOT, "*", ts))):
        if os.path.isfile(os.path.join(d, "payload.json")):
            return d
    return None


def list_local():
    out = []
    for p in sorted(glob.glob(os.path.join(SNAP_ROOT, "*", "*"))):
        d = p.replace("\\", "/").rstrip("/")
        parts = d.split("/")
        env, ts = parts[-2], parts[-1]
        if not os.path.isfile(os.path.join(d, "payload.json")):
            continue
        mf = os.path.join(d, "manifest.json")
        info = {}
        if os.path.exists(mf):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except Exception:
                info = {}
        c = info.get("counts") or {}
        out.append((env, ts, c, info.get("payload_bytes") or os.path.getsize(os.path.join(d, "payload.json"))))
    return out


def cmd_list(env=None):
    rows = list_local()
    if env:
        rows = [r for r in rows if r[0] == env]
    if not rows:
        _out("（本地暂无快照）")
        return
    builtin = _builtin_count()
    heads = ("来源", "时间戳", "分区", "精灵图", "头像", "照片", "payload")
    widths = (7, 17, 6, 13, 6, 6, 10)
    _out("本地图片快照（新→旧）：%s" % ("，限定 env=%s" % env if env else ""))
    _out("  " + "  ".join(_pad(h, w) for h, w in zip(heads, widths)))
    for env_, ts, c, b in sorted(rows, key=lambda x: x[1], reverse=True):
        pet_cell = str(c.get("pet_images", "-"))
        if builtin and pet_cell != "-":
            pet_cell += "(+%d)" % builtin
        cells = (env_, ts, c.get("pet_zones", "-"), pet_cell,
                 c.get("users_avatar", "-"), c.get("users_photo", "-"), "%dKB" % (b // 1024))
        _out("  " + "  ".join(_pad(x, w) for x, w in zip(cells, widths)))
    if builtin:
        _out("  注：「精灵图」=入库上传图；(+%d) 为内置宝可梦精灵——静态资源随代码发布，"
             "不入库、不参与快照。" % builtin)
    pre = [r for r in rows if r[1].startswith("pre-apply-")]
    if pre:
        _out("  （另有 %d 份应用前留底 pre-apply-*，不参与按份数清理）" % len(pre))


def prune_dir(root_dir, keep, quiet=False):
    """按时间序保留最近 keep 份（只清 ^\\d{8}-\\d{6}$，pre-apply-* 永不清理）。"""
    if keep is None or keep < 1:
        return []
    dirs = [d for d in glob.glob(os.path.join(root_dir, "*")) if TS_PAT.match(os.path.basename(d))]
    dirs.sort()
    victims = dirs[:-keep] if len(dirs) > keep else []
    for v in victims:
        import shutil
        shutil.rmtree(v, ignore_errors=True)
        if not quiet:
            _out("    清理过期快照 %s" % _rel(v))
    return victims


def cmd_prune(env, keep):
    n = prune_dir(os.path.join(SNAP_ROOT, env), keep)
    _out("本地 %s 清理完成：保留 %d 份，删除 %d 份" % (env, keep, len(n)))


# ---------------- 删除快照 ----------------
def choose_local_snapshot():
    """交互选择一份要删除的本地快照（pre-apply-* 留底不列出，防止误删安全网）。"""
    rows = [r for r in list_local() if not r[1].startswith("pre-apply-")]
    if not rows:
        _out("[ERROR] 本地尚无可删除的快照")
        sys.exit(1)
    rows.sort(key=lambda x: x[1], reverse=True)
    _out("本地快照（新→旧）：")
    for i, (env, ts, c, b) in enumerate(rows):
        _out("  [%d] %-5s %s  精灵图%s/头像%s/照片%s/%dKB"
             % (i + 1, env, ts, c.get("pet_images", "-"), c.get("users_avatar", "-"),
                c.get("users_photo", "-"), b // 1024))
    v = input("选择要删除的序号：").strip()
    try:
        env, ts = rows[int(v) - 1][0], rows[int(v) - 1][1]
    except (ValueError, IndexError):
        _out("[ERROR] 序号不合法")
        sys.exit(1)
    return find_local_snap(ts), env, ts


def cmd_delete_local(ts=None, snap=None, assume_yes=False):
    """删除本地快照（删除前展示内容并确认；pre-apply-* 留底不在可删清单）。"""
    import shutil
    if snap:
        if not (os.path.isdir(snap) and os.path.isfile(os.path.join(snap, "payload.json"))):
            _out("[ERROR] 快照目录不存在或缺 payload.json：%s" % snap)
            sys.exit(1)
        d = os.path.abspath(snap)
        env, ts_ = os.path.basename(os.path.dirname(d)), os.path.basename(d)
    else:
        d = find_local_snap(ts) if ts else None
        if d is None and ts is None:
            d, env, ts_ = choose_local_snapshot()
        elif d is None:
            _out("[ERROR] 本地不存在快照 %s" % ts)
            sys.exit(1)
        else:
            env, ts_ = os.path.basename(os.path.dirname(os.path.abspath(d))), os.path.basename(d)
    c, b = {}, 0
    mf = os.path.join(d, "manifest.json")
    if os.path.exists(mf):
        try:
            with open(mf, "r", encoding="utf-8") as f:
                info = json.load(f)
            c = info.get("counts") or {}
            b = info.get("payload_bytes") or 0
        except Exception:
            pass
    _out("=== 删除本地快照（%s %s）===" % (env, ts_))
    _out("    目录：%s" % _rel(d))
    _out("    内容：精灵图%s/头像%s/照片%s，payload %dKB"
         % (c.get("pet_images", "-"), c.get("users_avatar", "-"),
            c.get("users_photo", "-"), b // 1024))
    _out("    删除后不可恢复（如需保留请先另存目录内 payload.json）。")
    if not assume_yes:
        v = input("确认删除？(y/N)：").strip().lower()
        if v != "y":
            _out("已取消（未删除）")
            return
    try:
        shutil.rmtree(d)
    except OSError as e:
        _out("[ERROR] 删除失败（目录可能被占用）：%s" % e)
        sys.exit(1)
    if os.path.exists(d):
        _out("[ERROR] 目录仍存在，删除未生效：%s" % d)
        sys.exit(1)
    _out("==> 已删除本地快照（%s %s）" % (env, ts_))


def cmd_delete_remote(env, ts=None, assume_yes=False):
    """删除服务器（prod/dev）侧存档快照。仅列时间戳快照；pre-apply-* 留底不可删。"""
    ctl = _remote_ctl()
    snaps = [s for s in remote_list(env) if TS_PAT.match(s)]
    if not snaps:
        _out("[ERROR] 服务器 %s 尚无可删除的快照" % env)
        sys.exit(1)
    if ts is None:
        _out("服务器 %s 快照（新→旧）：" % env)
        for i, s in enumerate(snaps):
            _out("  [%d] %s" % (i + 1, s))
        v = input("选择要删除的序号：").strip()
        try:
            ts = snaps[int(v) - 1]
        except (ValueError, IndexError):
            _out("[ERROR] 序号不合法")
            sys.exit(1)
    if ts not in snaps:
        _out("[ERROR] 服务器 %s 上不存在快照 %s" % (env, ts))
        sys.exit(1)
    d = "%s/%s/%s" % (REMOTE_IMG_ROOT, env, ts)
    _out("=== 高危操作：删除【%s】服务器快照 ===" % env)
    _out("    目录：%s" % d)
    _out("    删除后服务器侧不可恢复（本地若仍有同名快照可重新拉取；业务数据不受影响）。")
    _out("    pre-apply-* 应用前留底不在此列，永不清理。")
    if not assume_yes:
        v = input("确认请输入 YES：").strip()
        if v != "YES":
            _out("已取消（未删除）")
            return
    rc, out = ctl.ssh_run("rm -rf %s && test ! -d %s && echo DELETED" % (d, d), timeout=60)
    if rc == 0 and "DELETED" in out:
        _out("==> 已删除服务器 %s 快照 %s" % (env, ts))
    else:
        _out("[ERROR] 服务器删除失败（rc=%s）——请检查 SSH 连接与目录权限" % rc)
        _out("    " + out[-300:])
        sys.exit(1)


# ---------------- 应用到远端 ----------------
def apply_remote(env, snap_dir, assume_yes=False, parts=None):
    ctl = _remote_ctl()
    url = ctl.ENV_URL[env]
    if parts is None and not assume_yes:
        parts = choose_parts()
    parts = _norm_parts(parts) or {"pet", "avatar", "photo"}
    _out("=== 高危操作：把本地快照应用到【%s】%s ===" % (env, url))
    _out("    应用大类：%s" % "、".join(CAT_LABEL[c] for c in ("pet", "avatar", "photo") if c in parts))
    _out("    将覆盖服务器上所选大类的数据（其它业务数据不受影响）。")
    _out("    服务器会在应用前自动留底（pre-apply-*），但请确认已知晓影响范围。")
    if not assume_yes:
        v = input("确认请输入 YES：").strip()
        if v != "YES":
            _out("已取消（未做任何改动）")
            return
    dbp = remote_db_path(ctl, env)
    py = remote_python(ctl, env)
    ts = now_ts()
    tmp = "/tmp/imgsnap-apply-%s" % ts
    payload_path = os.path.join(snap_dir, "payload.json")
    if not os.path.exists(payload_path):
        _out("[ERROR] 快照不存在或缺 payload.json：%s" % payload_path)
        sys.exit(1)
    _out("==> [1/5] 上传应用脚本与 payload → %s" % tmp)
    ctl.ssh_run("mkdir -p %s" % tmp, timeout=30)
    ctl.scp_push(os.path.abspath(__file__), "%s/img_snapshot.py" % tmp, timeout=120)
    ctl.scp_push(payload_path, "%s/payload.json" % tmp, timeout=300)
    _out("==> [2/5] 服务器应用（自动留底 → 事务应用 → 计数复核）")
    rc, out = ctl.ssh_run(
        "cd %s && %s img_snapshot.py remote-apply --db %s --payload payload.json --env %s --parts %s"
        % (tmp, py, dbp, env, ",".join(sorted(parts))), timeout=300)
    ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
    tail = [x for x in out.splitlines() if x.strip()][-12:]
    for line in tail:
        _out("    " + line)
    if rc != 0:
        _out("[ERROR] 服务器应用失败（rc=%s）" % rc)
        _out("    数据未变更或已回滚。应用前的留底在服务器：")
        _out("    %s/%s/pre-apply-*（含 payload.json，可用 remote-apply 流程还原）" % (REMOTE_IMG_ROOT, env))
        _out("    排查：ssh -F ops/secrets/sshcfg tapd 查看服务状态 systemctl status tapd-*")
        sys.exit(1)
    _out("==> [3/5] 健康检查 %s" % url)
    rc2, out2 = ctl.ssh_run(
        "curl -k -s -o /dev/null -w '%%{http_code}' --max-time 20 %s" % url, timeout=40)
    code = out2.strip()[-3:]
    if code in ("200", "301", "302"):
        _out("    服务健康（HTTP %s）" % code)
    else:
        _out("    [WARN] 健康检查未通过（HTTP %s）——图片已应用，请人工确认服务状态" % (code or "?"))
    _out("==> [4/5] 服务器侧留底：%s/%s/pre-apply-*（误操作可据此还原）" % (REMOTE_IMG_ROOT, env))
    _out("==> [5/5] 完成")


def remote_apply(db_path, payload_file, env, parts=None):
    """仅在服务器上执行：留底 → 事务应用 → 失败自动回滚。parts 限定大类。"""
    parts = _norm_parts(parts) or {"pet", "avatar", "photo"}
    try:
        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        _out("[ERROR] payload 解析失败：%s" % e)
        sys.exit(1)
    errs = validate_payload(payload, parts)
    if errs:
        for e in errs[:8]:
            _out("  [X] " + e)
        _out("[ERROR] 校验未通过，未改动数据库")
        sys.exit(1)
    if not os.path.exists(db_path):
        _out("[ERROR] 服务器数据库不存在：%s" % db_path)
        sys.exit(1)
    pre_dir = "%s/%s/pre-apply-%s" % (REMOTE_IMG_ROOT, env, now_ts())
    pre_payload, pre_counts = extract_payload(db_path, env)
    os.makedirs(pre_dir, exist_ok=True)
    with open(os.path.join(pre_dir, "payload.json"), "w", encoding="utf-8") as f:
        json.dump(pre_payload, f, ensure_ascii=False)
    _out("    应用前留底：%s（%d 账号 / %d 精灵图）" % (pre_dir, pre_counts["users"], pre_counts["pet_images"]))
    try:
        changed, _ = apply_payload(db_path, payload, env, quiet=True, pre_snapshot=False, parts=parts)
        _out("    应用成功（%s）：头像 %d 账号更新、照片 %d 账号更新、精灵区 %s"
             % ("、".join(CAT_LABEL[c] for c in ("pet", "avatar", "photo") if c in parts),
                changed["avatar"], changed["photo"],
                ("已还原" if changed["pet"] else "未选中")))
    except sqlite3.Error as e:
        _out("[ERROR] 应用事务失败，已回滚：%s" % e)
        _out("    数据保持原样；如需还原到应用前状态，留底：%s/payload.json" % pre_dir)
        sys.exit(1)


# ---------------- 自动快照（生产） ----------------
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def load_auto_cfg():
    """读取自动快照配置；旧格式（interval_min 分钟）自动迁移为
    interval_days（天，最小粒度=日）+ snap_time（每日执行时间 HH:MM）。"""
    try:
        with open(AUTO_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    days = cfg.get("interval_days")
    if not isinstance(days, int) or days < 1:
        mins = int(cfg.get("interval_min") or 0)
        cfg["interval_days"] = max(1, mins // 1440) if mins >= 1440 else 1
    if not cfg.get("snap_time") or not _TIME_RE.match(str(cfg["snap_time"])):
        cfg["snap_time"] = "02:00"
    cfg.setdefault("enabled", False)
    cfg.setdefault("keep", 10)
    return cfg


def save_auto_cfg(cfg):
    os.makedirs(SNAP_ROOT, exist_ok=True)
    cfg["updated_at"] = now_str()
    with open(AUTO_CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def cmd_auto():
    """计划任务入口：静默执行生产图片快照（开关关闭则直接退出）。"""
    cfg = load_auto_cfg()
    if not cfg.get("enabled"):
        return 0
    os.makedirs(SNAP_ROOT, exist_ok=True)
    try:
        fd = os.open(AUTO_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        if time.time() - os.path.getmtime(AUTO_LOCK) < 1800:
            return 0          # 上一次还没跑完（或残留未超 30 分钟），跳过本轮
        os.remove(AUTO_LOCK)
        return cmd_auto()
    try:
        keep = int(cfg.get("keep") or 10)
        # #107 口径：自动任务 = 纯服务器侧快照（服务器存档 + 服务器侧按份数清理），
        # 不拉回本地、不写任何数据库；本地副本一律由人工 [P] 快照 / [S] 拉取产生。
        export_remote("prod", pull_to_local=False)
        try:
            ctl = _remote_ctl()
            py = remote_python(ctl, "prod")
            tmp = "/tmp/imgsnap-prune-%s" % now_ts()
            ctl.ssh_run("mkdir -p %s" % tmp, timeout=30)
            ctl.scp_push(os.path.abspath(__file__), "%s/img_snapshot.py" % tmp, timeout=120)
            ctl.ssh_run("%s %s/img_snapshot.py prune --root %s/prod --keep %d --remote"
                        % (py, tmp, REMOTE_IMG_ROOT, keep), timeout=120)
            ctl.ssh_run("rm -rf %s" % tmp, timeout=30)
        except SystemExit:
            pass
        with open(AUTO_LOG, "a", encoding="utf-8") as f:
            f.write("%s auto prod OK(服务器侧) keep=%d\n" % (now_str(), keep))
        return 0
    except SystemExit as e:
        with open(AUTO_LOG, "a", encoding="utf-8") as f:
            f.write("%s auto prod FAIL rc=%s\n" % (now_str(), e.code))
        return e.code or 1
    except Exception as e:
        with open(AUTO_LOG, "a", encoding="utf-8") as f:
            f.write("%s auto prod FAIL %r\n" % (now_str(), e))
        return 1
    finally:
        try:
            os.remove(AUTO_LOCK)
        except OSError:
            pass


def _task_exists():
    import subprocess
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True)
    return r.returncode == 0


def _register_task(cfg):
    """按当前配置注册计划任务。返回 (是否成功, 天数, 时间)。"""
    days = int(cfg.get("interval_days") or 1)
    st = str(cfg.get("snap_time") or "02:00")
    return subprocess_schtasks(days, st), days, st


def _remove_task():
    import subprocess
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True)
    return r.returncode == 0


def cmd_auto_config():
    cfg = load_auto_cfg()
    reg = _task_exists()
    _out("=== 生产环境自动快照设置（仅生产库；纯服务器侧快照，不拉本地/不应用）===")
    _out("  当前：开关=%s  执行时间=%s  间隔=%s 天  保留=%s 份  计划任务=%s" %
         ("开" if cfg.get("enabled") else "关", cfg.get("snap_time"),
          cfg.get("interval_days"), cfg.get("keep"),
          "已注册" if reg else "未注册"))
    _out("  [1] 开/关切换（自动注册/移除计划任务）  [2] 设置执行时间(HH:MM)  [3] 设置间隔天数(≥1)")
    _out("  [4] 设置保留份数    [5] 手动注册计划任务    [6] 手动移除")
    _out("  [7] 立即执行一次    [0] 返回")
    v = input("选择：").strip()
    if v == "1":
        cfg["enabled"] = not cfg.get("enabled")
        if cfg["enabled"]:
            okr, days, st = _register_task(cfg)
            _out("自动快照已开启" +
                 ("，计划任务已注册（每 %d 天，每天 %s 执行）" % (days, st) if okr else
                  "；⚠️ 计划任务注册失败（需管理员权限？）——可稍后用 [5] 手动注册"))
        else:
            okr = _remove_task()
            _out("自动快照已关闭，计划任务已" + ("移除" if okr else "未在系统中（无需移除）"))
    elif v == "2":
        t = input("执行时间 HH:MM（24 小时制，如 02:30）：").strip()
        m = _TIME_RE.match(t)
        if not m:
            _out("[ERROR] 时间格式应为 HH:MM（24 小时制），收到: %s" % (t or "(空)")); return
        cfg["snap_time"] = "%02d:%02d" % (int(m.group(1)), int(m.group(2)))
        if cfg.get("enabled"):
            okr, days, st = _register_task(cfg)
            _out("执行时间已设为每天 %s，计划任务已%s（每 %d 天）"
                 % (st, "同步更新" if okr else "更新失败（请用 [5] 手动注册）", days))
        else:
            _out("执行时间已设为每天 %s（开关开启后将按该时间自动注册）" % cfg["snap_time"])
    elif v == "3":
        n = input("间隔天数（≥1，最小粒度为天）：").strip()
        if not n.isdigit() or int(n) < 1:
            _out("[ERROR] 间隔必须为 ≥1 的整数天"); return
        cfg["interval_days"] = int(n)
        if cfg.get("enabled"):
            okr, days, st = _register_task(cfg)
            _out("间隔已设为 %d 天，计划任务已%s（每天 %s）"
                 % (int(n), "同步更新" if okr else "更新失败（请用 [5] 手动注册）", st))
        else:
            _out("间隔已设为 %d 天（开关开启后将按该间隔自动注册）" % int(n))
    elif v == "4":
        n = input("保留份数（≥1，按时间就近保留）：").strip()
        if not n.isdigit() or int(n) < 1:
            _out("[ERROR] 份数必须为 ≥1 的整数"); return
        cfg["keep"] = int(n)
        _out("保留份数已设为 %d（仅服务器侧按份数清理；本地副本不参与自动清理）" % int(n))
    elif v == "5":
        if not cfg.get("enabled"):
            _out("[WARN] 自动快照当前为「关」，任务会注册但每次静默跳过；建议先执行 [1] 开启")
        okr, days, st = _register_task(cfg)
        if okr:
            _out("计划任务已注册：`%s`（每 %d 天，每天 %s 执行）" % (TASK_NAME, days, st))
        else:
            _out("[ERROR] 注册失败（需管理员权限？）——也可手动：")
            _out('  schtasks /Create /TN "%s" /SC DAILY /MO %d /ST %s /TR "\'%s\' auto"'
                 % (TASK_NAME, days, st, sys.argv[0]))
    elif v == "6":
        okr = _remove_task()
        _out("计划任务已移除" if okr else "[WARN] 移除失败或任务不存在")
    elif v == "7":
        save_auto_cfg(cfg)
        code = cmd_auto()
        _out("执行结束（rc=%s），日志：%s" % (code, _rel(AUTO_LOG)))
        return
    else:
        return
    save_auto_cfg(cfg)
    _out("配置已保存：%s" % _rel(AUTO_CFG))


def subprocess_schtasks(days, time_str):
    """注册计划任务：每 days 天的 time_str（HH:MM）执行一次（/SC DAILY）。
    （2026-11-17 #125）任务动作路径改用 __file__ —— 原用 sys.argv[0]，若经由
    `python -c ...` 调用注册，argv[0] 是 '-c'，注册出的任务动作损坏
    （"python.exe" "-c" auto，267011 从未运行成功）。"""
    import subprocess
    me = os.path.abspath(__file__)
    py = os.path.abspath(sys.executable)
    tr = '"%s" "%s" auto' % (py, me)
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "DAILY",
                        "/MO", str(days), "/ST", time_str, "/TR", tr, "/F"],
                       capture_output=True)
    return r.returncode == 0


# ---------------- 交互选择 ----------------
def choose_snapshot():
    rows = [r for r in list_local() if not r[1].startswith("pre-apply-")]
    if not rows:
        _out("[ERROR] 本地尚无任何快照（先执行快照储存）")
        sys.exit(1)
    rows.sort(key=lambda x: x[1], reverse=True)
    _out("本地快照（新→旧）：")
    for i, (env, ts, c, b) in enumerate(rows):
        _out("  [%d] %-5s %s  精灵图%s/头像%s/照片%s/%dKB"
             % (i + 1, env, ts, c.get("pet_images", "-"), c.get("users_avatar", "-"),
                c.get("users_photo", "-"), b // 1024))
    v = input("选择序号：").strip()
    try:
        env, ts = rows[int(v) - 1][0], rows[int(v) - 1][1]
    except (ValueError, IndexError):
        _out("[ERROR] 序号不合法")
        sys.exit(1)
    return find_local_snap(ts)


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="图片资源快照与回滚（精灵设置/头像/照片）")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("export"); p.add_argument("--env", required=True, choices=["local", "prod", "dev"])
    p.add_argument("--db"); p.add_argument("--out"); p.add_argument("--remote", action="store_true")
    p = sub.add_parser("apply"); p.add_argument("env", choices=["local", "prod", "dev"])
    p.add_argument("ts", nargs="?"); p.add_argument("--snap"); p.add_argument("--yes", action="store_true")
    p.add_argument("--parts")   # 大类：pet/avatar/photo（逗号分隔，1/2/3/A 亦可）；缺省交互选择
    p.add_argument("--db")   # 仅 env=local 且测试/演练时覆盖目标库（默认 src/app.db）
    p = sub.add_parser("pull"); p.add_argument("env", choices=["prod", "dev"]); p.add_argument("ts", nargs="?")
    p = sub.add_parser("list"); p.add_argument("env", nargs="?")
    p = sub.add_parser("prune"); p.add_argument("env"); p.add_argument("--keep", type=int, default=10)
    p.add_argument("--root"); p.add_argument("--remote", action="store_true")
    p = sub.add_parser("delete"); p.add_argument("env", choices=["local", "prod", "dev"])
    p.add_argument("ts", nargs="?"); p.add_argument("--snap"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("remote-apply"); p.add_argument("--db", required=True)
    p.add_argument("--payload", required=True); p.add_argument("--env", required=True, choices=["prod", "dev"])
    p.add_argument("--parts", default="pet,avatar,photo")
    sub.add_parser("auto"); sub.add_parser("auto-config")
    a = ap.parse_args()

    if a.cmd == "export":
        if a.env in ("prod", "dev") and not a.remote:
            export_remote(a.env)
        elif a.remote:
            # 远端模式：--out 为服务器上的目标目录
            dbp = a.db or (ENV_DIR[a.env] + "/app.db")
            payload, counts = extract_payload(dbp, a.env)
            out_dir = a.out or os.path.join(SNAP_ROOT, a.env, now_ts())
            os.makedirs(out_dir, exist_ok=True)
            manifest, n_prev = write_snapshot(out_dir, payload, counts, a.env)
            _out("    服务器导出完成：%s" % out_dir)
            _out("    精灵 %d 分区/%d 图；头像 %d、照片 %d（%d 账号）；payload %d bytes"
                 % (counts["pet_zones"], counts["pet_images"], counts["users_avatar"],
                    counts["users_photo"], counts["users"], manifest["payload_bytes"]))
        else:
            export_local(a.env, a.db, a.out)
    elif a.cmd == "pull":
        cmd_pull(a.env, a.ts)
    elif a.cmd == "apply":
        snap = a.snap or (find_local_snap(a.ts) if a.ts else choose_snapshot())
        if not snap or not os.path.isdir(snap):
            _out("[ERROR] 本地快照不存在：%s" % (a.ts or a.snap))
            sys.exit(1)
        if a.env == "local":
            with open(os.path.join(snap, "payload.json"), "r", encoding="utf-8") as f:
                payload = json.load(f)
            parts = _norm_parts(a.parts)
            _out("=== 应用本地快照 → 本地库（%s）===" % _rel(snap))
            if not a.yes:
                if parts is None:
                    parts = choose_parts()
                v = input("确认应用？(y/N)：").strip().lower()
                if v != "y":
                    _out("已取消"); return
            else:
                parts = parts or {"pet", "avatar", "photo"}
            try:
                # 留底目录跟随所应用快照所在目录（正常=快照库 env 目录；--snap 指向隔离目录时留底也在隔离目录）
                apply_payload(a.db or LOCAL_DB, payload, "local", parts=parts,
                              pre_dir_base=os.path.dirname(os.path.abspath(snap)))
            except sqlite3.Error as e:
                _out("[ERROR] 应用事务失败，已回滚（数据保持原样）：%s" % e)
                _out("    应用前的留底在 data/img-snapshots/local/pre-apply-*（可用本工具还原）")
                sys.exit(1)
            _out("==> 完成（8100 服务无需重启，页面刷新即生效）")
        else:
            apply_remote(a.env, snap, assume_yes=a.yes, parts=a.parts)
    elif a.cmd == "list":
        cmd_list(a.env)
    elif a.cmd == "prune":
        if a.remote:
            n = prune_dir(a.root, a.keep, quiet=True)
            _out("    prune 完成：删除 %d 份，保留 %d 份" % (len(n), a.keep))
        else:
            cmd_prune(a.env, a.keep)
    elif a.cmd == "delete":
        if a.env == "local":
            cmd_delete_local(a.ts, a.snap, a.yes)
        else:
            cmd_delete_remote(a.env, a.ts, a.yes)
    elif a.cmd == "remote-apply":
        remote_apply(a.db, a.payload, a.env, a.parts)
    elif a.cmd == "auto":
        sys.exit(cmd_auto())
    elif a.cmd == "auto-config":
        cmd_auto_config()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _out("\n已中断")
        sys.exit(130)
