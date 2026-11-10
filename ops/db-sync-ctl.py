# -*- coding: utf-8 -*-
"""
数据库快照同步与回滚控制器（本地执行，2026-11-07）

职责：
  pull   服务器生产库 → 本地快照库（服务器侧先拍一致性快照再拉取）
  list   列出本地快照
  apply  本地快照 → 本地开发环境（8100）数据源（自动留底当前本地库）
  push   本地快照 → 服务器生产库回滚（危险：服务器自动留底 → 上传 → 恢复 → 健康检查）

快照存储：<项目根>/data/db-snapshots/<YYYYMMDD-HHMMSS>/app.db + meta.txt

编码约定：由调用方（数据库同步回滚.bat）设置 PYTHONIOENCODING=gbk；
远端（服务器）输出一律 UTF-8 字节，本脚本捕获后不直接回显，只提取 ASCII 路径。
"""
import os
import re
import sys
import shutil
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SSH_CFG = os.path.join(HERE, "secrets", "sshcfg").replace("\\", "/")
SNAP_ROOT = os.path.join(ROOT, "data", "db-snapshots")
LOCAL_DB = os.path.join(ROOT, "src", "app.db")
LOCAL_CTL = os.path.join(HERE, "local-ctl.py")
PROD_URL = "https://123.207.252.195/login"
DEV_URL = "https://123.207.252.195:8443/login"
ENV_DIR = {"prod": "/opt/tapd-workbench", "dev": "/opt/tapd-dev"}
ENV_URL = {"prod": PROD_URL, "dev": DEV_URL}


def find_bash():
    cands = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Git\bin\bash.exe",
        r"D:\Git\bin\bash.exe",
        r"D:\Program Files\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\WorkBuddy\resources\vendor\PortableGit\bin\bash.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


BASH = find_bash()


def ssh_run(remote_cmd, timeout=90):
    """SSH 执行远端命令，返回 (rc, stdout_text)。远端输出按 UTF-8 解码。"""
    if not BASH:
        print("[ERROR] 未找到 Git Bash")
        sys.exit(1)
    cmd = [BASH, "-c", 'ssh -F "%s" tapd "%s"' % (SSH_CFG, remote_cmd.replace('"', '\\"'))]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    out = r.stdout.decode("utf-8", errors="replace")
    return r.returncode, out


def scp_pull(remote_path, local_path, timeout=300):
    cmd = [BASH, "-c", 'scp -F "%s" tapd:"%s" "%s"' % (SSH_CFG, remote_path, local_path.replace("\\", "/"))]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print("[ERROR] scp 拉取失败:", r.stderr.decode("utf-8", errors="replace")[-300:])
        sys.exit(1)


def scp_push(local_path, remote_path, timeout=300):
    cmd = [BASH, "-c", 'scp -F "%s" "%s" tapd:"%s"' % (SSH_CFG, local_path.replace("\\", "/"), remote_path)]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print("[ERROR] scp 上传失败:", r.stderr.decode("utf-8", errors="replace")[-300:])
        sys.exit(1)


def now_ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def ask(prompt, expect="yes"):
    v = input(prompt).strip()
    return v == expect


# ---------------- pull ----------------
def cmd_pull():
    print("==> [1/3] 服务器拍一致性快照（sqlite backup API，不停服）")
    rc, out = ssh_run("tapd backup", timeout=120)
    m = re.search(r"(/var/backups/tapd-workbench/app\.db\.\d{8}-\d{6})", out)
    if rc != 0 or not m:
        print("[ERROR] 服务器备份失败（rc=%s）" % rc)
        print(out[-500:].encode("gbk", errors="replace").decode("gbk"))
        sys.exit(1)
    remote_snap = m.group(1)
    ts = now_ts().replace("-", "_")
    dest = os.path.join(SNAP_ROOT, "prod_%s" % ts)   # 编号规则（#109）：来源前缀_YYYYMMDD_HHMMSS
    os.makedirs(dest, exist_ok=True)

    print("==> [2/3] 拉取快照 → data/db-snapshots/prod_%s/" % ts)
    scp_pull(remote_snap, os.path.join(dest, "app.db"))

    size = os.path.getsize(os.path.join(dest, "app.db"))
    with open(os.path.join(dest, "meta.txt"), "w", encoding="utf-8") as f:
        f.write("source=prod:/opt/tapd-workbench/app.db\n")
        f.write("remote_snap=%s\n" % remote_snap)
        f.write("pulled_at=%s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.write("bytes=%d\n" % size)
    print("==> [3/3] 完成")
    print("  快照: data/db-snapshots/prod_%s/app.db（%d bytes）" % (ts, size))
    print("  用途: 菜单 [3] 应用为本地开发数据源；菜单 [4] 回滚到服务器生产")
    return ts


# ---------------- snaplocal（拍本地库快照）----------------
def cmd_snaplocal():
    """把本地开发环境（src/app.db，8100 数据源）的当前数据拍成快照留存。

    与菜单 [1]（从服务器拉取）对称：本地库在 apply/日常使用后会产生新数据，
    在应用别的快照或推回服务器之前，先把当前本地数据留存一份。
    """
    if not os.path.isfile(LOCAL_DB):
        print("[ERROR] 本地库不存在: %s" % LOCAL_DB)
        sys.exit(1)
    ts = now_ts().replace("-", "_")
    dest = os.path.join(SNAP_ROOT, "local_%s" % ts)   # 编号规则（#109）：来源前缀_YYYYMMDD_HHMMSS
    os.makedirs(dest, exist_ok=True)
    print("==> [1/2] 本地库一致性快照（sqlite backup API，允许服务运行中）...")
    import sqlite3
    src = sqlite3.connect(LOCAL_DB)
    dst = sqlite3.connect(os.path.join(dest, "app.db"))
    src.backup(dst)
    dst.close()
    src.close()
    size = os.path.getsize(os.path.join(dest, "app.db"))
    with open(os.path.join(dest, "meta.txt"), "w", encoding="utf-8") as f:
        f.write("source=local:src/app.db\n")
        f.write("pulled_at=%s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.write("bytes=%d\n" % size)
    print("==> [2/2] 完成")
    print("  快照: data/db-snapshots/local_%s/app.db（%d bytes）" % (ts, size))
    print("  后续: 菜单 [3] 应用回本地开发；菜单 [4]/[6] 回滚到服务器")
    return ts



# ---------------- list ----------------
def snapshots():
    if not os.path.isdir(SNAP_ROOT):
        return []
    out = []
    for name in os.listdir(SNAP_ROOT):
        db = os.path.join(SNAP_ROOT, name, "app.db")
        if os.path.isfile(db):
            out.append(name)
    # #135 用户需求：按「拍摄时间」倒序，而不是目录名字母序 ——
    # 字母序会把 bak-local_ 排最前，来源混杂看不清时间线
    def ts_key(n):
        m = re.search(r'(\d{8})_(\d{6})$', n)
        return (m.group(1) + m.group(2)) if m else '000000000000000'
    out.sort(key=ts_key, reverse=True)
    return out


def snap_label(name):
    """快照目录名 → (来源中文标签, 可读时间串)。

    命名规则（#109）：来源前缀_YYYYMMDD_HHMMSS
      prod_      服务器生产拉取    dev_        服务器开发拉取
      local_     本地拍摄          bak-local_  回滚前自动留底
    """
    m = re.match(r'^(.+?)_(\d{8})_(\d{6})$', name)
    if not m:
        return '其他', ''
    prefix, d, t = m.group(1), m.group(2), m.group(3)
    tm = '%s-%s-%s %s:%s:%s' % (d[:4], d[4:6], d[6:8], t[:2], t[2:4], t[4:6])
    label = {'prod': '服务器生产拉取',
             'dev': '服务器开发拉取',
             'local': '本地拍摄',
             'bak-local': '回滚前自动留底'}.get(prefix, prefix)
    return label, tm


def cmd_list():
    names = snapshots()
    if not names:
        print("（暂无本地快照。菜单 [1] 拉服务器 / [7] 拍本地）")
        return
    print("本地快照（按拍摄时间 新→旧）：")
    for i, n in enumerate(names, 1):
        db = os.path.join(SNAP_ROOT, n, "app.db")
        label, tm = snap_label(n)
        print("  [%d] %s ｜ %s  %8.1f KB  （%s）"
              % (i, tm or '(无时间)', label, os.path.getsize(db) / 1024.0, n))
    print("  图例：prod_=服务器生产拉取 dev_=服务器开发拉取 local_=本地拍摄 bak-local_=回滚前自动留底")


def pick_snapshot():
    names = snapshots()
    if not names:
        print("（暂无本地快照）")
        return None
    cmd_list()
    v = input("选择快照序号（直接回车取消）: ").strip()
    if not v.isdigit() or not (1 <= int(v) <= len(names)):
        return None
    return names[int(v) - 1]


# ---------------- apply（本地开发数据源）----------------
def cmd_apply():
    name = pick_snapshot()
    if not name:
        print("已取消。")
        return
    snap_db = os.path.join(SNAP_ROOT, name, "app.db")
    print("==> 将用快照 %s 作为本地开发库（src/app.db）" % name)

    # ① 本地服务需先停（避免 WAL 并发写坏库）
    r = subprocess.run([sys.executable, LOCAL_CTL, "status"], capture_output=True, timeout=30)
    running = b"200" in r.stdout or "运行中".encode("gbk") in r.stdout
    was_running = False
    if running:
        was_running = True
        print("==> [1/3] 停止本地服务（8100）...")
        subprocess.run([sys.executable, LOCAL_CTL, "stop"], timeout=60)

    # ② 当前本地库自动留底（防误覆盖丢本地开发数据）
    ts = now_ts()
    keep = os.path.join(SNAP_ROOT, "bak-local_%s" % ts)   # 编号规则（#109）：应用前本地留底
    os.makedirs(keep, exist_ok=True)
    if os.path.isfile(LOCAL_DB):
        src = __import__("sqlite3").connect(LOCAL_DB)
        dst = __import__("sqlite3").connect(os.path.join(keep, "app.db"))
        src.backup(dst)
        dst.close(); src.close()
        print("==> [2/3] 当前本地库已留底: data/db-snapshots/bak-local_%s/" % ts)

    # ③ 替换
    shutil.copyfile(snap_db, LOCAL_DB)
    for ext in ("-wal", "-shm"):
        p = LOCAL_DB + ext
        if os.path.exists(p):
            os.remove(p)
    print("==> [3/3] 已替换 src/app.db ← 快照 %s" % name)

    if was_running:
        v = input("立即启动本地服务（8100）？直接回车=启动 / n=暂不: ").strip().lower()
        if v != "n":
            subprocess.run([sys.executable, LOCAL_CTL, "start"], timeout=90)
            print("本地服务已启动，浏览器打开 http://127.0.0.1:8100/login 验证。")


# ---------------- orgpush（按架构部门回滚）----------------
# 口径：部门范围 = org_nodes 中该节点及其全部子孙节点，经 board_config 绑定的看板，
#       这些看板上的全部卡片（含子事项）。「财务中心（全部）」= 根节点全树；
#       「财务中心（公共部分）」= 仅根节点自身绑定的看板。未绑定部门的看板不在任何范围内。

def _descendants(nodes, root_id):
    """org_nodes[(id,parent_id)] 中 root_id 及其全部子孙 id"""
    kids = {}
    for nid, pid in nodes:
        kids.setdefault(pid, []).append(nid)
    out, stack = [], [root_id]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(kids.get(n, []))
    return out


def cmd_orgpush():
    # ① 环境
    print("回滚目标环境：")
    print("  [1] 生产（https://123.207.252.195，高危，影响真实用户）")
    print("  [2] 开发（https://123.207.252.195:8443，仅测试环境）")
    v = input("选择环境序号（直接回车取消）: ").strip()
    env = {"1": "prod", "2": "dev"}.get(v)
    if not env:
        print("已取消。")
        return

    # ② 快照
    name = pick_snapshot()
    if not name:
        print("已取消。")
        return
    snap_db = os.path.join(SNAP_ROOT, name, "app.db")

    # ③ 从快照库读架构树 + 部门范围统计（范围口径以快照时点的绑定为权威）
    import sqlite3
    snap = sqlite3.connect("file:%s?mode=ro" % snap_db.replace(chr(92), "/"), uri=True)
    nodes = snap.execute("SELECT id, parent_id, name, node_type FROM org_nodes").fetchall()
    parents = [(r[0], r[1]) for r in nodes]
    depts = [(r[0], r[2]) for r in nodes if r[3] == "dept"]
    roots = [(r[0], r[2]) for r in nodes if r[3] == "center"]

    bind = {}
    for nid, bid in snap.execute("SELECT dept_node_id, board_id FROM board_config"):
        bind.setdefault(nid, []).append(bid)

    def scope_of(node_id):
        ids = _descendants(parents, node_id)
        boards, seen = [], set()
        for i in ids:
            for b in bind.get(i, []):
                if b not in seen:
                    seen.add(b)
                    boards.append(b)
        return ids, boards

    def card_count(boards):
        if not boards:
            return 0
        ph = ",".join("?" * len(boards))
        return snap.execute(
            "SELECT COUNT(*) FROM cards WHERE deleted=0 AND board_id IN (%s)" % ph,
            boards).fetchone()[0]

    options = []   # (显示文本, boards)
    for nid, nm in sorted(depts, key=lambda x: x[1]):
        ids, boards = scope_of(nid)
        options.append(("%s（含 %d 个下级）" % (nm, len(ids) - 1), boards))
    for rid, nm in roots:
        ids, allb = scope_of(rid)
        options.append(("%s（全部——含所有部门）" % nm, allb))
        options.append(("%s（仅公共部分，不含部门）" % nm, bind.get(rid, [])))

    print()
    print("按架构选择回滚范围（卡数 = 快照时点该范围活跃卡）：")
    for i, (label, boards) in enumerate(options, 1):
        print("  [%d] %-28s %d 张卡 / %d 个看板" % (i, label, card_count(boards), len(boards)))
    v = input("选择范围序号（直接回车取消）: ").strip()
    if not v.isdigit() or not (1 <= int(v) <= len(options)):
        print("已取消。")
        return
    label, board_ids = options[int(v) - 1]
    if not board_ids:
        print("该范围在快照时点没有绑定任何看板，无可回滚内容。")
        return

    # ④ 确认
    env_cn = "生产" if env == "prod" else "开发"
    svc = "tapd-web" if env == "prod" else "tapd-dev"
    venvdir = "tapd-workbench" if env == "prod" else "tapd-dev"
    print()
    print("=" * 60)
    print("!! 将把【%s】环境按架构【%s】回滚到快照 %s" % (env_cn, label, name))
    print("!! 范围 = %d 个看板；快照中 %d 张卡将恢复为快照版本" % (len(board_ids), card_count(board_ids)))
    print("!! 范围内当前有、快照中没有的活跃卡将被【软删除】（可救回）")
    print("!! 范围外的一切数据（其他部门/看板/用户/配置）零接触")
    print("!! 执行前服务器自动整库留底（<env>-rollback-before-orgpush-*）")
    print("=" * 60)
    if not ask("  确认继续？输入 yes: "):
        print("已取消。")
        return

    ts = now_ts()
    print("==> [1/5] 服务器整库留底...")
    rc, out = ssh_run("tapd snap %s %s-rollback-before-orgpush-%s" % (env, env, ts), timeout=180)
    if rc != 0:
        print("[ERROR] 留底失败，中止（服务器未做任何变更）")
        sys.exit(1)

    print("==> [2/5] 上传快照库到服务器...")
    remote_tmp = "/tmp/tapd-orgpush-%s.db" % ts
    scp_push(snap_db, remote_tmp)

    print("==> [3/5] 停服 → 按部门合并 → 启动（事务内完成，范围外零接触）...")
    boards_arg = ",".join(board_ids)
    rc, out = ssh_run(
        "systemctl stop %s && /opt/%s/venv/bin/python /usr/local/bin/tapd-org-merge.py %s %s '%s'; "
        "RC=$?; systemctl start %s; sleep 4; systemctl is-active %s; exit $RC"
        % (svc, venvdir, env, remote_tmp, boards_arg, svc, svc), timeout=300)
    if rc != 0:
        print("[ERROR] 合并失败（rc=%s）——服务已重启，数据库有整库留底，可用发布回滚.bat 还原" % rc)
        sys.exit(1)
    stats = [l for l in out.splitlines() if l.startswith("{")]
    print("    合并统计: %s" % (stats[-1] if stats else "(无)"))
    print("    服务状态: %s" % (out.strip().splitlines()[-1] if out.strip() else "未知"))
    ssh_run("rm -f %s" % remote_tmp)

    print("==> [5/5] 公网健康复查...")
    import urllib.request
    import ssl
    try:
        code = urllib.request.urlopen(urllib.request.Request(ENV_URL[env], method="GET"),
                                      timeout=15, context=ssl._create_unverified_context()).status
    except Exception as ex:
        code = "ERR:%s" % ex
    print()
    if code == 200:
        print("√ 部门回滚完成：%s环境【%s】已回到快照 %s 时点" % (env_cn, label, name))
        print("  浏览器验证: %s；整库留底: release/%s/%s-rollback-before-orgpush-%s"
              % (ENV_URL[env], env, ts))
    else:
        print("!! 健康检查异常（%s）——请人工确认，或用发布回滚.bat 整库还原" % code)


# ---------------- push（回滚到服务器生产/开发库）----------------
def cmd_push():
    print("回滚目标环境：")
    print("  [1] 生产（https://123.207.252.195，高危，影响真实用户）")
    print("  [2] 开发（https://123.207.252.195:8443，仅测试环境）")
    v = input("选择环境序号（直接回车取消）: ").strip()
    if v == "1":
        env = "prod"
    elif v == "2":
        env = "dev"
    else:
        print("已取消。")
        return
    name = pick_snapshot()
    if not name:
        print("已取消。")
        return
    snap_db = os.path.join(SNAP_ROOT, name, "app.db")
    if env == "prod":
        print()
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!! 高危操作：将用本地快照【%s】覆盖服务器【生产】库" % name)
        print("!! 影响: 生产停服约 10~20 秒；快照之后生产产生的新数据将不可见")
        print("!! 兜底: 回滚前服务器会自动拍当前快照（<env>-rollback-before-*）")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        print()
        print("========================================================")
        print("!! 将用本地快照【%s】覆盖服务器【开发】库" % name)
        print("!! 影响: 开发环境停机几秒；开发库当前数据被覆盖（自动留底）")
        print("========================================================")
    if not ask("  确认继续？输入 yes: "):
        print("已取消。")
        return

    ts = now_ts()
    print("==> [1/4] 服务器自动拍当前 %s 快照（留底）..." % ("生产" if env == "prod" else "开发"))
    rc, out = ssh_run("tapd snap %s %s-rollback-before-push-%s" % (env, env, ts), timeout=180)
    if rc != 0:
        print("[ERROR] 留底快照失败，中止（服务器未做任何变更）")
        sys.exit(1)

    print("==> [2/4] 上传快照到服务器...")
    remote_tmp = "/tmp/tapd-push-%s.db" % ts
    scp_push(snap_db, remote_tmp)

    print("==> [3/4] 恢复 %s 库（停服→覆盖→启动）..." % ("生产" if env == "prod" else "开发"))
    rc, out = ssh_run("tapd restore %s %s" % (env, remote_tmp), timeout=180)
    if rc != 0:
        print("[ERROR] 服务器恢复失败（rc=%s），请立即人工检查：" % rc)
        print("  ssh -F ops/secrets/sshcfg tapd 'systemctl status tapd-%s'" % env)
        sys.exit(1)
    ssh_run("rm -f %s" % remote_tmp)

    print("==> [4/4] 公网健康复查...")
    import urllib.request
    import ssl
    try:
        code = urllib.request.urlopen(
            urllib.request.Request(ENV_URL[env], method="GET"),
            timeout=15, context=ssl._create_unverified_context()).status
    except Exception as ex:
        code = "ERR:%s" % ex
    env_cn = "生产" if env == "prod" else "开发"
    print()
    if code == 200:
        print("√ 回滚完成：%s环境 https://123.207.252.195%s 健康（HTTP 200），内容 = 快照 %s"
              % (env_cn, "" if env == "prod" else ":8443", name))
        print("  留底: 服务器 release/%s/%s-rollback-before-push-%s（可再次回滚）" % (env, env, ts))
    else:
        print("!! 回滚已执行但健康检查异常（%s）——请打开浏览器人工确认，或用发布回滚.bat 再回滚" % code)


# ---------------- delete（删除本地快照）----------------
def cmd_delete():
    name = pick_snapshot()
    if not name:
        print("已取消。")
        return
    d = os.path.join(SNAP_ROOT, name)
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(d) for f in fs)
    print("即将删除本地快照：%s（%.1f KB）" % (name, size / 1024.0))
    print("仅删除本地文件，不影响服务器上的任何快照。")
    if not ask("  确认删除？输入 yes: "):
        print("已取消。")
        return
    shutil.rmtree(d)
    print("已删除：%s" % d)


def main():
    if len(sys.argv) < 2:
        print("用法: db-sync-ctl.py <pull|list|apply|push|delete|orgpush|snaplocal> [参数]")
        return 2
    cmd = sys.argv[1]
    if cmd == "pull":
        cmd_pull()
    elif cmd == "list":
        cmd_list()
    elif cmd == "apply":
        cmd_apply()
    elif cmd == "push":
        cmd_push()
    elif cmd == "delete":
        cmd_delete()
    elif cmd == "orgpush":
        cmd_orgpush()
    elif cmd == "snaplocal":
        cmd_snaplocal()
    else:
        print("未知命令: %s（可用: pull|list|apply|push|delete）" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
