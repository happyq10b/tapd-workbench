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
REMOTE_DIR = "/opt/tapd-workbench"
PROD_URL = "https://123.207.252.195/login"


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
    ts = now_ts()
    dest = os.path.join(SNAP_ROOT, ts)
    os.makedirs(dest, exist_ok=True)

    print("==> [2/3] 拉取快照 → data/db-snapshots/%s/" % ts)
    scp_pull(remote_snap, os.path.join(dest, "app.db"))

    size = os.path.getsize(os.path.join(dest, "app.db"))
    with open(os.path.join(dest, "meta.txt"), "w", encoding="utf-8") as f:
        f.write("source=prod:/opt/tapd-workbench/app.db\n")
        f.write("remote_snap=%s\n" % remote_snap)
        f.write("pulled_at=%s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.write("bytes=%d\n" % size)
    print("==> [3/3] 完成")
    print("  快照: data/db-snapshots/%s/app.db（%d bytes）" % (ts, size))
    print("  用途: 菜单 [3] 应用为本地开发数据源；菜单 [4] 回滚到服务器生产")
    return ts


# ---------------- list ----------------
def snapshots():
    if not os.path.isdir(SNAP_ROOT):
        return []
    out = []
    for name in sorted(os.listdir(SNAP_ROOT), reverse=True):
        db = os.path.join(SNAP_ROOT, name, "app.db")
        if os.path.isfile(db):
            out.append(name)
    return out


def cmd_list():
    names = snapshots()
    if not names:
        print("（暂无本地快照。先用菜单 [1] 从服务器拉取）")
        return
    print("本地快照（新→旧）：")
    for i, n in enumerate(names, 1):
        db = os.path.join(SNAP_ROOT, n, "app.db")
        meta = os.path.join(SNAP_ROOT, n, "meta.txt")
        src = ""
        if os.path.isfile(meta):
            for line in open(meta, encoding="utf-8"):
                if line.startswith("source="):
                    src = line.split("=", 1)[1].strip()
        print("  [%d] %s  %8.1f KB  来源: %s" % (i, n, os.path.getsize(db) / 1024.0, src))


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
    keep = os.path.join(SNAP_ROOT, "local-before-%s-%s" % (name, ts))
    os.makedirs(keep, exist_ok=True)
    if os.path.isfile(LOCAL_DB):
        src = __import__("sqlite3").connect(LOCAL_DB)
        dst = __import__("sqlite3").connect(os.path.join(keep, "app.db"))
        src.backup(dst)
        dst.close(); src.close()
        print("==> [2/3] 当前本地库已留底: data/db-snapshots/local-before-%s-%s/" % (name, ts))

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


# ---------------- push（回滚到生产）----------------
def cmd_push():
    name = pick_snapshot()
    if not name:
        print("已取消。")
        return
    snap_db = os.path.join(SNAP_ROOT, name, "app.db")
    print()
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!! 高危操作：将用本地快照【%s】覆盖服务器生产库" % name)
    print("!! 影响: 生产停服约 10~20 秒；快照之后生产产生的新数据将不可见")
    print("!! 兜底: 回滚前服务器会自动拍当前生产快照（rollback-before-*）")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    if not ask("  确认继续？输入 yes: "):
        print("已取消。")
        return

    ts = now_ts()
    print("==> [1/4] 服务器自动拍当前生产快照（留底）...")
    rc, out = ssh_run("tapd snap prod rollback-before-push-%s" % ts, timeout=180)
    if rc != 0:
        print("[ERROR] 留底快照失败，中止（生产未做任何变更）")
        sys.exit(1)

    print("==> [2/4] 上传快照到服务器...")
    remote_tmp = "/tmp/tapd-push-%s.db" % ts
    scp_push(snap_db, remote_tmp)

    print("==> [3/4] 恢复生产库（停服→覆盖→启动）...")
    rc, out = ssh_run("tapd restore %s" % remote_tmp, timeout=180)
    if rc != 0:
        print("[ERROR] 服务器恢复失败（rc=%s），请立即人工检查：" % rc)
        print("  ssh -F ops/secrets/sshcfg tapd 'systemctl status tapd-web'")
        sys.exit(1)
    ssh_run("rm -f %s" % remote_tmp)

    print("==> [4/4] 公网健康复查...")
    import urllib.request
    import ssl
    try:
        code = urllib.request.urlopen(
            urllib.request.Request(PROD_URL, method="GET"),
            timeout=15, context=ssl._create_unverified_context()).status
    except Exception as ex:
        code = "ERR:%s" % ex
    print()
    if code == 200:
        print("√ 回滚完成：生产 https://123.207.252.195 健康（HTTP 200），内容 = 快照 %s" % name)
        print("  留底: 服务器 release/prod/rollback-before-push-%s（可再次回滚）" % ts)
    else:
        print("!! 回滚已执行但健康检查异常（%s）——请打开浏览器人工确认，或用发布回滚.bat 再回滚" % code)


def main():
    if len(sys.argv) < 2:
        print("用法: db-sync-ctl.py <pull|list|apply|push> [参数]")
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
    else:
        print("未知命令: %s" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
