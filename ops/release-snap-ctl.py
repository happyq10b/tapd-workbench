# -*- coding: utf-8 -*-
"""
服务器发布快照的本地镜像控制器（2026-11-10 #141）

对象 = 服务器 /var/backups/tapd-workbench/release/<prod|dev>/<名称>/（代码tar+DB）
本地镜像存储 = <项目根>/data/release-snapshots/<prod|dev>/<名称>/

命令：
  list [env]           列出本地镜像快照
  pull <env> <名称>    服务器快照 → 下载到本地（不改动服务器）
  restore <env> <名称> 本地镜像 → 上传服务器并回滚（高危！双确认，约20秒停机）
  delete <env> <名称>  删除本地镜像（只删本地）

编码约定：调用方（发布回滚.bat）设置 PYTHONIOENCODING=gbk，同 db-sync-ctl.py。
"""
import os
import re
import shutil
import subprocess
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SSH_CFG = os.path.join(HERE, "secrets", "sshcfg").replace("\\", "/")
RELEASE_DIR = "/var/backups/tapd-workbench/release"
MIRROR_ROOT = os.path.join(ROOT, "data", "release-snapshots")


def find_bash():
    for c in [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"D:\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\WorkBuddy\resources\vendor\PortableGit\bin\bash.exe"),
    ]:
        if c and os.path.exists(c):
            return c
    return None


BASH = find_bash()


def _ssh(remote_cmd, timeout=60):
    cmd = [BASH, "-c", 'ssh -n -F "%s" tapd "%s"' % (SSH_CFG, remote_cmd.replace('"', '\\"'))]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def _scp_pull(remote_path, local_path, timeout=600):
    cmd = [BASH, "-c", 'scp -r -F "%s" "tapd:%s" "%s"' % (SSH_CFG, remote_path, local_path.replace("\\", "/"))]
    return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode


def _scp_push(local_path, remote_path, timeout=600):
    cmd = [BASH, "-c", 'scp -r -F "%s" "%s" "tapd:%s"' % (SSH_CFG, local_path.replace("\\", "/"), remote_path)]
    return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode


def valid_name(env, name):
    if env not in ("prod", "dev"):
        print("[ERROR] 环境必须是 prod 或 dev")
        return False
    if not name or re.search(r'[/\\]', name) or name in (".", "..") or name.startswith("-"):
        print("[ERROR] 非法快照名: %s" % name)
        return False
    return True


def remote_exists(env, name):
    rc, out = _ssh('test -d "%s/%s/%s" && echo Y' % (RELEASE_DIR, env, name))
    return "Y" in out


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def env_of(arg):
    env = (arg or "").strip().lower()
    if env in ("prod", "dev"):
        return env
    print("[ERROR] 环境必须是 prod 或 dev")
    return None


def local_dir(env, name):
    return os.path.join(MIRROR_ROOT, env, name)


# ---------------- list ----------------
def cmd_list(env_arg=""):
    envs = [env_of(env_arg)] if env_arg else ["prod", "dev"]
    if envs[0] is None:
        sys.exit(1)
    any_found = False
    for env in envs:
        d = os.path.join(MIRROR_ROOT, env)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            sd = os.path.join(d, name)
            if not os.path.isdir(sd):
                continue
            any_found = True
            db = os.path.join(sd, "app.db")
            sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(sd) for f in fs)
            ts = datetime.datetime.fromtimestamp(os.path.getmtime(sd)).strftime("%Y-%m-%d %H:%M")
            ok = "OK" if os.path.isfile(db) else "缺 app.db!"
            print("  %s/%s  %8.1f KB  %s  [%s]" % (env, name, sz / 1024.0, ts, ok))
    if not any_found:
        print("（暂无本地镜像。菜单 [9] Pull-Local 下载）")


# ---------------- pull ----------------
def cmd_pull(env_arg="", name_arg=""):
    env = env_of(env_arg)
    if not env:
        sys.exit(1)
    name = name_arg.strip()
    if not valid_name(env, name):
        sys.exit(1)
    if not remote_exists(env, name):
        print("[ERROR] 服务器上不存在该快照: %s/%s（先 [1]/[2] 列出确认名称）" % (env, name))
        sys.exit(1)
    dest = local_dir(env, name)
    if os.path.isdir(dest):
        v = ask("本地已存在 %s/%s，覆盖？输入 yes: " % (env, name))
        if v != "yes":
            print("已取消。")
            return
        shutil.rmtree(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("==> 下载 release/%s/%s → data\\release-snapshots\\%s\\ ..." % (env, name, env))
    rc = _scp_pull("%s/%s/%s" % (RELEASE_DIR, env, name), os.path.dirname(dest))
    if rc != 0 or not os.path.isfile(os.path.join(dest, "app.db")):
        print("[ERROR] 下载失败（rc=%s）或缺少 app.db" % rc)
        sys.exit(1)
    sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(dest) for f in fs)
    print("完成：本地镜像 %s/%s（%.1f KB）" % (env, name, sz / 1024.0))


# ---------------- restore ----------------
def cmd_restore(env_arg="", name_arg=""):
    env = env_of(env_arg)
    if not env:
        sys.exit(1)
    name = name_arg.strip()
    if not valid_name(env, name):
        sys.exit(1)
    src = local_dir(env, name)
    if not os.path.isfile(os.path.join(src, "app.db")):
        print("[ERROR] 本地镜像不存在或不完整: %s/%s（先 Pull-Local）" % (env, name))
        sys.exit(1)
    print("即将用本地镜像回滚服务器（恢复代码+数据库，约20秒停机）：")
    print("  环境: %s    镜像: %s" % (env.upper(), name))
    if remote_exists(env, name):
        print("  注意: 服务器上已存在同名快照，上传将覆盖它")
    print("  安全网: 回滚前服务器会自动拍当前状态留底（%s-rollback-before-%s）" % (env, name))
    if ask("  第一重确认，继续？输入 yes: ") != "yes":
        print("已取消。")
        return
    if ask("  第二重确认，确定回滚 %s？输入 yes: " % env.upper()) != "yes":
        print("已取消。")
        return
    tmp_remote = "/tmp/rs-upload-%s" % name
    print("==> [1/3] 上传本地镜像到服务器 ...")
    _ssh("rm -rf %s" % tmp_remote)
    rc = _scp_push(src, tmp_remote)
    if rc != 0:
        print("[ERROR] 上传失败（rc=%s）" % rc)
        sys.exit(1)
    print("==> [2/3] 就位 + 回滚（约20秒停机）...")
    _ssh("rm -rf %s/%s/%s && mv %s %s/%s/%s" % (RELEASE_DIR, env, name, tmp_remote, RELEASE_DIR, env, name), timeout=60)
    rc, out = _ssh("tapd rollback %s %s" % (env, name), timeout=300)
    print(out.strip()[-800:] if out.strip() else "(无输出)")
    if rc != 0:
        print("[ERROR] 回滚失败（rc=%s），服务器已自动留底可再回滚" % rc)
        sys.exit(1)
    print("==> [3/3] 完成。留底与日志见上方输出。")


# ---------------- delete ----------------
def cmd_delete(env_arg="", name_arg=""):
    env = env_of(env_arg)
    if not env:
        sys.exit(1)
    name = name_arg.strip()
    if not valid_name(env, name):
        sys.exit(1)
    d = local_dir(env, name)
    if not os.path.isdir(d):
        print("[ERROR] 本地镜像不存在: %s/%s" % (env, name))
        sys.exit(1)
    sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs)
    print("即将删除本地镜像：%s/%s（%.1f KB）—— 只删本地文件，不影响服务器。" % (env, name, sz / 1024.0))
    if ask("  确认删除？输入 yes: ") != "yes":
        print("已取消。")
        return
    shutil.rmtree(d)
    print("已删除：%s" % d)


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: release-snap-ctl.py <list|pull|restore|delete> [prod|dev] [名称]")
        return 2
    cmd = args[0]
    env = args[1] if len(args) > 1 else ""
    name = args[2] if len(args) > 2 else ""
    if cmd == "list":
        cmd_list(env)
    elif cmd == "pull":
        cmd_pull(env, name)
    elif cmd == "restore":
        cmd_restore(env, name)
    elif cmd == "delete":
        cmd_delete(env, name)
    else:
        print("未知命令: %s（可用: list|pull|restore|delete）" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
