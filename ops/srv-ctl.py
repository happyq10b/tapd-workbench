# -*- coding: utf-8 -*-
"""
服务器端工具箱调用器（本地执行，实际走 SSH）

作用：让批处理无需处理路径转义/引号嵌套问题。
'服务开关.bat' 只需把子命令名传进来即可。

用法: python srv-ctl.py <sub-command> [args...]
例如: python srv-ctl.py status
      python srv-ctl.py logs 60
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OPS = HERE
SSH_CFG = os.path.join(OPS, "secrets", "sshcfg")
# Windows 路径转成 POSIX 风格，ssh -F 更稳
SSH_CFG_POSIX = SSH_CFG.replace("\\", "/")
# 'tapd logs' 用的是 journalctl -f（跟随模式），永远不会自己返回。
# 菜单里需要「看一眼就回来」，所以给它一个硬超时。
LOGS_TIMEOUT = 15


def find_bash():
    cands = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Git\bin\bash.exe",
        r"D:\Git\bin\bash.exe",
        r"D:\Program Files\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\WorkBuddy\resources\vendor\PortableGit\bin\bash.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def main():
    if len(sys.argv) < 2:
        print("用法: srv-ctl.py <sub-command> [args...]")
        return 2
    args = sys.argv[1:]
    bash = find_bash()
    if not bash:
        print("[ERROR] 未找到 Git Bash，无法连接服务器。")
        return 1
    # 远端命令：tapd <sub> <args...>
    remote = "tapd " + " ".join("'%s'" % a.replace("'", "") for a in args)
    # 本地命令：ssh -n -F <cfg> tapd "<remote>"
    cmd = [
        bash, "-c",
        "ssh -n -F '%s' tapd \"%s\"" % (SSH_CFG_POSIX, remote),
    ]
    is_logs = bool(args) and args[0] == "logs"
    try:
        if is_logs:
            # journalctl -f 不会结束，限时输出后主动断开
            try:
                subprocess.call(cmd, timeout=LOGS_TIMEOUT)
            except subprocess.TimeoutExpired:
                print("\n(日志跟随已到时限 %ds，自动停止)" % LOGS_TIMEOUT)
            return 0
        return subprocess.call(cmd)
    except Exception as ex:
        print("[ERROR] 调用失败: %s" % ex)
        return 1


if __name__ == "__main__":
    sys.exit(main())
