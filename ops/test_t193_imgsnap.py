#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-193 图片快照测试（全部本地运行，不触碰生产/开发服务器）。

隔离纪律（教训：④ 曾在真实快照库上跑 prune 误删用户快照）：
  - 导出/应用/清理全部走 TEMP 隔离目录（export --out / apply --snap / prune 独立 root）；
    绝不读写 data/img-snapshots/{local,prod,dev} 下的任何真实快照；
  - list 冒烟用独立 env 名（__t193test）并整体删除；
  - DB 操作全部在库副本（--db / apply_payload 直调），不影响 8100 真实库；
  - 夹具 __t193_ 前缀 + finally 清理 + 残留自查。
"""
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "ops", ".localvenv", "Scripts", "python.exe")
CTL = os.path.join(ROOT, "ops", "img_snapshot.py")
SNAP_ROOT = os.path.join(ROOT, "data", "img-snapshots")
ISO = os.path.join(os.environ.get("TEMP", "."), "t193_snaps")   # 测试专用隔离快照根
P = "__t193_"

sys.path.insert(0, os.path.join(ROOT, "ops"))
import importlib.util
spec = importlib.util.spec_from_file_location("img_snapshot", CTL)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

RESULTS = []
TMP_DB = os.path.join(os.environ.get("TEMP", "."), "t193_app.db")
PNG1 = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
PNG2 = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Zgc"
        "AAAAFUlEQVR42mNk+M9QzQAEjBkYQAWaAQA3AAX/o6wUBAAAAABJRU5ErkJggg==")


def ok(cond, msg):
    RESULTS.append((bool(cond), msg))
    print(("  PASS " if cond else "  x FAIL ") + msg, flush=True)


def run_cli(*args, input_text=None):
    r = subprocess.run([PY, CTL] + list(args), capture_output=True, timeout=120, cwd=ROOT,
                       input=(input_text.encode() if input_text else None))
    out = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0:
        out += "\n[stderr] " + r.stderr.decode("utf-8", errors="replace")[-400:]
    return r.returncode, out


def q(db, sql, args=()):
    c = sqlite3.connect(db, timeout=20)
    c.execute("PRAGMA busy_timeout=20000")
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def ex(db, sql, args=()):
    c = sqlite3.connect(db, timeout=20)
    c.execute("PRAGMA busy_timeout=20000")
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def make_fixtures(db):
    """建库副本夹具：1 用户（头像+照片）、1 分区、2 精灵图、login_pet。"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    ex(db, "INSERT OR REPLACE INTO users(username,password_hash,role,active_seq,avatar,photo) "
           "VALUES(?,?,?,?,?,?)", (P + "u1", b"x", "editor", 1, PNG1, PNG1))
    ex(db, "INSERT INTO pet_zones(id,name,sort,created_at) VALUES(900001,?,1,?)", (P + "区甲", now))
    ex(db, "INSERT INTO pet_images(id,zone,name,data,sort,created_by,created_at) VALUES(900101,?,?,?,0,?,?)",
       (P + "区甲", P + "图一", PNG1, P + "u1", now))
    ex(db, "INSERT INTO pet_images(id,zone,name,data,sort,created_by,created_at) VALUES(900102,?,?,?,1,?,?)",
       (P + "区甲", P + "图二", PNG2, P + "u1", now))
    ex(db, "INSERT OR REPLACE INTO app_settings(key,value) VALUES('login_pet',?)",
       ('{"mode":"fixed","kind":"upload","image_id":900101}',))


def iso_dirs():
    return sorted(glob.glob(os.path.join(ISO, "*", "*")))


def main():
    # ---------- ① 库副本导出（隔离目录）：payload/manifest/preview ----------
    print("【① 库副本导出（隔离目录）：payload + manifest + preview】", flush=True)
    shutil.copy(os.path.join(ROOT, "src", "app.db"), TMP_DB)
    make_fixtures(TMP_DB)
    rc, out = run_cli("export", "--env", "local", "--db", TMP_DB, "--out", ISO)
    ok(rc == 0, "export CLI 退出码 0")
    snap_dir = None
    for l in out.splitlines():
        if "快照完成" in l:
            cand = l.split("：", 1)[1].strip()
            if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "payload.json")):
                snap_dir = cand
    ok(snap_dir is not None and ISO.lower() in snap_dir.lower(),
       "快照落在隔离目录（未污染真实快照库）")
    ts = os.path.basename(snap_dir)
    payload = json.load(open(os.path.join(snap_dir, "payload.json"), encoding="utf-8"))
    ok(payload.get("kind") == "fisp-img-snapshot", "payload 标识正确")
    ok(any(u == P + "u1" for u in payload["users"]), "快照含夹具用户（头像+照片）")
    ok(sum(1 for im in payload["pet"]["images"] if im["zone"] == P + "区甲") == 2,
       "快照含夹具 2 张精灵图")
    ok(payload["pet"]["login_pet"] is not None, "快照含 login_pet 配置")
    ok(os.path.isdir(os.path.join(snap_dir, "preview", "avatars"))
       and len(os.listdir(os.path.join(snap_dir, "preview", "avatars"))) >= 1,
       "preview/avatars 已解码落盘")
    ok(os.path.isdir(os.path.join(snap_dir, "preview", "pet"))
       and len(os.listdir(os.path.join(snap_dir, "preview", "pet"))) >= 2,
       "preview/pet 已解码落盘")

    # ---------- ② 破坏后应用（--snap 按路径）：全部还原 ----------
    print("【② 破坏后应用（--snap）：头像/照片/精灵区/login_pet 全部还原】", flush=True)
    ex(TMP_DB, "UPDATE users SET avatar=?, photo='' WHERE username=?", (PNG2, P + "u1"))
    ex(TMP_DB, "DELETE FROM pet_images WHERE id=900102")
    ex(TMP_DB, "DELETE FROM app_settings WHERE key='login_pet'")
    ex(TMP_DB, "INSERT INTO users(username,password_hash,role,active_seq,avatar) VALUES(?,?,?,?,?)",
       (P + "u2", b"x", "editor", 1, PNG2))          # 快照外新增账号（非破坏性校验点）
    rc, out = run_cli("apply", "local", "--snap", snap_dir, "--yes", "--db", TMP_DB)
    ok(rc == 0, "apply CLI 退出码 0")
    avatar, photo = q(TMP_DB, "SELECT avatar,photo FROM users WHERE username=?", (P + "u1",))[0]
    ok(avatar == PNG1 and photo == PNG1, "头像/照片还原为快照值")
    n = q(TMP_DB, "SELECT COUNT(*) FROM pet_images WHERE zone=?", (P + "区甲",))[0][0]
    ok(n == 2, "被删除的精灵图已还原（2 张）")
    lp = q(TMP_DB, "SELECT value FROM app_settings WHERE key='login_pet'")
    ok(len(lp) == 1 and "900101" in lp[0][0], "login_pet 配置还原")
    u2 = q(TMP_DB, "SELECT avatar FROM users WHERE username=?", (P + "u2",))[0][0]
    ok(u2 == PNG2, "快照外新增账号不被破坏（非破坏性回滚）")
    zid = q(TMP_DB, "SELECT id FROM pet_zones WHERE name=?", (P + "区甲",))[0][0]
    ok(zid == 900001, "分区 id 保持一致")
    seq = q(TMP_DB, "SELECT seq FROM sqlite_sequence WHERE name='pet_images'")
    ok(seq and seq[0][0] >= 900102, "sqlite_sequence 已抬高，后续插入不撞 id")
    pre = [d for d in iso_dirs() if os.path.basename(d).startswith("pre-apply-")]
    ok(bool(pre), "应用前留底 pre-apply-* 已生成（在隔离目录内）")

    # ---------- ②b 分类应用：按大类选择，不能一口气全应用 ----------
    print("【②b 分类应用：--parts 仅还原所选大类】", flush=True)
    ex(TMP_DB, "UPDATE users SET avatar=? WHERE username=?", (PNG2, P + "u1"))
    ex(TMP_DB, "DELETE FROM pet_images WHERE id=900102")
    ex(TMP_DB, "DELETE FROM app_settings WHERE key='login_pet'")
    rc, out = run_cli("apply", "local", "--snap", snap_dir, "--yes", "--db", TMP_DB, "--parts", "avatar")
    ok(rc == 0, "apply --parts avatar 退出码 0")
    avatar, photo = q(TMP_DB, "SELECT avatar,photo FROM users WHERE username=?", (P + "u1",))[0]
    ok(avatar == PNG1, "仅应用「头像」→ 头像还原")
    n = q(TMP_DB, "SELECT COUNT(*) FROM pet_images WHERE zone=?", (P + "区甲",))[0][0]
    lp = q(TMP_DB, "SELECT COUNT(*) FROM app_settings WHERE key='login_pet'")[0][0]
    ok(n == 1 and lp == 0, "未选「精灵图」→ 精灵区保持被破坏状态（不越界应用）")
    rc, out = run_cli("apply", "local", "--snap", snap_dir, "--yes", "--db", TMP_DB, "--parts", "pet")
    ok(rc == 0, "apply --parts pet 退出码 0")
    n = q(TMP_DB, "SELECT COUNT(*) FROM pet_images WHERE zone=?", (P + "区甲",))[0][0]
    lp = q(TMP_DB, "SELECT value FROM app_settings WHERE key='login_pet'")
    ok(n == 2 and len(lp) == 1 and "900101" in lp[0][0], "仅应用「精灵图」→ 精灵区还原")
    avatar, photo = q(TMP_DB, "SELECT avatar,photo FROM users WHERE username=?", (P + "u1",))[0]
    ok(avatar == PNG1 and photo == PNG1, "头像/照片未被精灵图应用触碰")
    parts_bad = M._norm_parts("9,x")
    ok(parts_bad is None, "非法大类输入归一化为 None（交互侧会拒绝）")

    # ---------- ③ 校验防线：非法 payload 拒绝应用 ----------
    print("【③ 校验防线：非法 data URL 拒绝应用】", flush=True)
    bad = json.loads(json.dumps(payload))
    bad["users"][P + "u1"]["avatar"] = "data:text/html;base64,PGI+aGk8L2I+"
    errs = M.validate_payload(bad)
    ok(len(errs) >= 1, "validate_payload 拦截非图片 data URL")
    before = q(TMP_DB, "SELECT avatar FROM users WHERE username=?", (P + "u1",))[0][0]
    snap_bad = os.path.join(ISO, "local", "20990101-000001")
    os.makedirs(snap_bad, exist_ok=True)
    json.dump(bad, open(os.path.join(snap_bad, "payload.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rc, out = run_cli("apply", "local", "--snap", snap_bad, "--yes", "--db", TMP_DB)
    ok(rc != 0 and "校验未通过" in out, "CLI 应用非法快照 → 非零退出 + 提示")
    after = q(TMP_DB, "SELECT avatar FROM users WHERE username=?", (P + "u1",))[0][0]
    ok(before == after, "校验失败时数据库未被改动")

    # ---------- ④ 按份数清理（隔离根，按时间就近保留） ----------
    # 假目录用「过去」时间戳（1999）—— keep=2 保留的是最近两份，被清理的只会是假目录，
    # snap_dir（当前时间）必须存活供 ⑥ 删除用例使用
    print("【④ 按份数清理：keep=2 保留最近两份（隔离根）】", flush=True)
    for t in ("19990101-000001", "19990101-000002", "19990101-000003"):
        d = os.path.join(ISO, "local", t)
        os.makedirs(d, exist_ok=True)
        shutil.copy(os.path.join(snap_dir, "payload.json"), os.path.join(d, "payload.json"))
    victims = M.prune_dir(os.path.join(ISO, "local"), 2, quiet=True)
    ok(len(victims) == 3 and all("19990101" in v for v in victims),
       "超过份数的旧快照被清理（3 份 1999 假目录，keep=2）")
    left = sorted(os.path.basename(d) for d in iso_dirs()
                  if "pre-apply" not in os.path.basename(d))
    ok(left == sorted([os.path.basename(snap_dir), "20990101-000001"]),
       "按时间就近保留最近 2 份（真快照 + 较新假目录）")
    ok(os.path.exists(snap_dir), "真实测试快照存活（不被份数清理波及）")

    # ---------- ⑤ 快照清单（独立 env 名冒烟，不碰 local/prod/dev） ----------
    print("【⑤ 快照清单（对齐 + 内置口径）】", flush=True)
    fake_env = os.path.join(SNAP_ROOT, "__t193test", "20990202-000000")
    os.makedirs(fake_env, exist_ok=True)
    json.dump({"kind": "fisp-img-snapshot", "version": 1, "created_at": "x", "source": "local",
               "source_db": "x", "counts": {"pet_zones": 1, "pet_images": 26}, "payload_bytes": 10},
              open(os.path.join(fake_env, "manifest.json"), "w", encoding="utf-8"))
    json.dump({"kind": "fisp-img-snapshot", "version": 1, "pet": {}, "users": {}},
              open(os.path.join(fake_env, "payload.json"), "w", encoding="utf-8"))
    rc, out = run_cli("list", "__t193test")
    ok(rc == 0 and "20990202-000000" in out and "(+386)" in out,
       "list 输出含时间戳与内置精灵口径 (+386)")
    import re
    widths = (7, 17, 6, 13, 6, 6, 10)

    def _exp_starts(cells):
        """期望的字符起始位（len + 按 CJK 显示宽补的空格数累计）。"""
        offs, pos = [], 2
        for c, w in zip(cells, widths):
            offs.append(pos)
            pos += len(str(c)) + max(0, w - M._dw(str(c))) + 2
        return offs

    lines7 = [l for l in out.splitlines()
              if l.startswith("  ") and len(re.findall(r"\S+", l)) == 7]
    header = [l for l in lines7 if "payload" in l]
    ok(bool(header) and [m.start() for m in re.finditer(r"\S+", header[0])]
       == _exp_starts(["来源", "时间戳", "分区", "精灵图", "头像", "照片", "payload"]),
       "表头各列起始位符合 CJK 显示宽度计算")
    # 数据行前两列（env/时间戳为 ASCII，解码不失真）与表头对齐
    exp2 = _exp_starts(["__t193test", "20990202-000000", "x", "x", "x", "x", "x"])[:2]
    data2 = [[m.start() for m in re.finditer(r"\S+", l)][:2]
             for l in lines7 if "payload" not in l]
    ok(bool(data2) and all(s == exp2 for s in data2), "数据行 env/时间戳列与表头严格对齐")

    # ---------- ⑥ 删除快照：本地（确认/取消）+ 远端（mock 验证范围与确认） ----------
    print("【⑥ 删除快照：本地 + 远端（mock）】", flush=True)
    # 造第二份（更早时间戳的）本地隔离快照
    snap_b = os.path.join(ISO, "local", "20980101-000000")
    os.makedirs(snap_b, exist_ok=True)
    shutil.copy(os.path.join(snap_dir, "payload.json"), os.path.join(snap_b, "payload.json"))
    shutil.copy(os.path.join(snap_dir, "manifest.json"), os.path.join(snap_b, "manifest.json"))
    # ⑥a 删除本地：--snap 路径 + --yes
    rc, out = run_cli("delete", "local", "--snap", snap_dir, "--yes")
    ok(rc == 0 and not os.path.exists(snap_dir), "本地快照已删除（目录消失）")
    ok(os.path.exists(snap_b), "其它快照不受影响")
    # ⑥b 取消路径：不传 --yes，stdin 喂 n
    rc, out = run_cli("delete", "local", "--snap", snap_b, input_text="n\n")
    ok(rc == 0 and os.path.exists(snap_b), "确认输入 n → 取消，不删除")
    # ⑥c 不存在的 ts → 报错
    rc, out = run_cli("delete", "local", "20991231-000000", "--yes")
    ok(rc != 0 and "不存在" in out, "删除不存在的本地快照 → 报错退出")
    # ⑥d 远端删除（mock ssh，不触真实服务器）：只删所选、YES 确认、pre-apply 不可选
    saved_ctl = M._remote_ctl

    class FakeCtl:
        ENV_URL = {"prod": "https://fake", "dev": "https://fake"}
        ENV_DIR = {"prod": "/opt/tapd-workbench", "dev": "/opt/tapd-dev"}

        def __init__(self):
            self.cmds = []
            self.listing = ("20990101-000002\n20990101-000001\npre-apply-20990101-000003\n")

        def ssh_run(self, cmd, timeout=90):
            self.cmds.append(cmd)
            if "ls -1" in cmd:
                return 0, self.listing
            if "rm -rf" in cmd:
                return 0, "DELETED"
            return 0, ""

    fake = FakeCtl()
    M._remote_ctl = lambda: fake
    try:
        M.cmd_delete_remote("prod", ts="20990101-000001", assume_yes=True)
        rms = [c for c in fake.cmds if "rm -rf" in c]
        ok(len(rms) == 1 and "/prod/20990101-000001" in rms[0]
           and "20990101-000002" not in rms[0] and "pre-apply" not in rms[0],
           "远端删除：rm 命令仅指向所选快照（不波及其它/留底）")
        ok("test ! -d" in rms[0], "删除后带目录消失复核")
        # 取消路径：YES 问询输入非 YES → 不发 rm
        import builtins
        old_input = builtins.input
        builtins.input = lambda *a, **k: "no"
        try:
            M.cmd_delete_remote("prod", ts="20990101-000002", assume_yes=False)
        finally:
            builtins.input = old_input
        rms2 = [c for c in fake.cmds if "rm -rf" in c]
        ok(len(rms2) == 1, "服务器快照删除未输入 YES → 取消（不发 rm）")
        # 不存在的 ts → 报错
        try:
            M.cmd_delete_remote("prod", ts="20991231-000000", assume_yes=True)
            ok(False, "删除服务器不存在快照 → 应报错")
        except SystemExit as e:
            ok(e.code == 1, "删除服务器不存在快照 → 报错退出（rc=1）")
    finally:
        M._remote_ctl = saved_ctl

    # ---------- ⑦ 自动配置迁移（分钟→天+执行时间）与计划任务命令 ----------
    print("【⑦ 自动配置迁移 + 计划任务命令构造】", flush=True)
    tmpcfg = os.path.join(os.environ.get("TEMP", "."), "t193_auto.json")
    with open(tmpcfg, "w", encoding="utf-8") as f:
        json.dump({"enabled": True, "interval_min": 2880, "keep": 3}, f)
    old_cfg_path = M.AUTO_CFG
    M.AUTO_CFG = tmpcfg
    try:
        cfg = M.load_auto_cfg()
        ok(cfg.get("interval_days") == 2 and cfg.get("snap_time") == "02:00"
           and cfg.get("enabled") is True,
           "旧配置迁移：2880 分钟 → 2 天 + 默认执行时间 02:00")
        cfg["snap_time"] = "25:99"
        cfg["interval_days"] = 0
        cfg.pop("interval_min", None)   # 剔除旧字段 → 验证纯默认回退路径
        with open(tmpcfg, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        cfg2 = M.load_auto_cfg()
        ok(cfg2.get("snap_time") == "02:00" and cfg2.get("interval_days") == 1,
           "非法时间回退 02:00、非法间隔回退 1 天")
    finally:
        M.AUTO_CFG = old_cfg_path
        if os.path.exists(tmpcfg):
            os.remove(tmpcfg)
    import subprocess as _sp
    calls = []
    real_run = _sp.run

    def fake_run(args, **kw):
        calls.append(args)
        return type("P", (), {"returncode": 0})()

    _sp.run = fake_run
    try:
        okr = M.subprocess_schtasks(3, "02:30")
    finally:
        _sp.run = real_run
    ok(bool(okr) and calls and calls[0][calls[0].index("/SC") + 1] == "DAILY"
       and calls[0][calls[0].index("/MO") + 1] == "3"
       and calls[0][calls[0].index("/ST") + 1] == "02:30",
       "计划任务命令 = /SC DAILY /MO 天数 /ST HH:MM")

    # ---------- ⑧ 开关自动注册 / 关闭自动移除 ----------
    print("【⑧ 开关自动注册计划任务】", flush=True)
    import builtins as _bi
    tmpcfg2 = os.path.join(os.environ.get("TEMP", "."), "t193_auto2.json")
    with open(tmpcfg2, "w", encoding="utf-8") as f:
        json.dump({"enabled": False, "interval_days": 1, "snap_time": "02:00", "keep": 3}, f)
    old_cfg_path2 = M.AUTO_CFG
    M.AUTO_CFG = tmpcfg2
    calls2 = []
    real_run2 = _sp.run
    real_input = _bi.input

    def fake_run2(args, **kw):
        calls2.append(list(args))
        return type("P", (), {"returncode": 0})()

    _sp.run = fake_run2
    answers = iter(["1", "1"])
    _bi.input = lambda *a, **k: next(answers)
    try:
        M.cmd_auto_config()   # 开 → 自动注册
        M.cmd_auto_config()   # 关 → 自动移除
    finally:
        _sp.run = real_run2
        _bi.input = real_input
        M.AUTO_CFG = old_cfg_path2
        if os.path.exists(tmpcfg2):
            os.remove(tmpcfg2)
    creates = [c for c in calls2 if "/Create" in c]
    deletes = [c for c in calls2 if "/Delete" in c]
    ok(len(creates) == 1 and creates[0][creates[0].index("/SC") + 1] == "DAILY"
       and creates[0][creates[0].index("/ST") + 1] == "02:00",
       "开启 → 自动注册计划任务（/SC DAILY /ST 02:00）")
    ok(len(deletes) == 1, "关闭 → 自动移除计划任务")
    shutil.rmtree(os.path.join(SNAP_ROOT, "__t193test"), ignore_errors=True)


def residue():
    """残留自查：夹具（真实库只读核对）+ 隔离目录整体删除。"""
    real = os.path.join(ROOT, "src", "app.db")
    n_user = q(real, "SELECT COUNT(*) FROM users WHERE username LIKE ?", (P + "%",))[0][0]
    n_pet = q(real, "SELECT COUNT(*) FROM pet_images WHERE zone LIKE ?", (P + "%",))[0][0]
    n_zone = q(real, "SELECT COUNT(*) FROM pet_zones WHERE name LIKE ?", (P + "%",))[0][0]
    # login_pet 是真实业务数据（超管配置），只检查是否混入夹具标记（image_id=900101）
    lp_rows = q(real, "SELECT value FROM app_settings WHERE key='login_pet'")
    lp = sum(1 for r in lp_rows if "900101" in (r[0] or ""))
    # 隔离目录与 list 冒烟目录整体删除（带重试，防文件锁）
    leftovers = []
    for attempt in range(3):
        leftovers = []
        shutil.rmtree(ISO, ignore_errors=True)
        if os.path.exists(ISO):
            leftovers.append(ISO)
        if os.path.exists(os.path.join(SNAP_ROOT, "__t193test")):
            shutil.rmtree(os.path.join(SNAP_ROOT, "__t193test"), ignore_errors=True)
            if os.path.exists(os.path.join(SNAP_ROOT, "__t193test")):
                leftovers.append(SNAP_ROOT + "/__t193test")
        if not leftovers:
            break
        time.sleep(2)
    # 真实快照库 local/prod/dev 的既有内容不得被测试触碰（只核对数量变化口径：不做断言，只报告）
    return n_user + n_pet + n_zone + lp + len(leftovers)


if __name__ == "__main__":
    code = 0
    try:
        main()
    finally:
        n = residue()
        if os.path.exists(TMP_DB):
            try:
                os.remove(TMP_DB)
            except OSError:
                pass
        fails = [m for c, m in RESULTS if not c]
        print("夹具/隔离目录残留自查: %d（应为 0）" % n, flush=True)
        print("结果: PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)), flush=True)
        if fails or n:
            code = 1
    sys.exit(code)
