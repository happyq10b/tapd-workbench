# -*- coding: utf-8 -*-
"""
自动快照定时任务控制器（2026-11-10 #143）

管理服务器 crontab 中的「tapd snap prod/dev」两条定时任务：
  status              查看开关状态与拍摄时间
  on <HH:MM> [HH:MM]  开启（第1个=生产，第2个=开发；省略则开发=生产+10分钟）
  off                 关闭（仅移除 tapd snap 两条，不动 crontab 其他条目）

编码约定：调用方（发布回滚.bat）设置 PYTHONIOENCODING=gbk。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SSH_CFG = os.path.join(HERE, "secrets", "sshcfg").replace("\\", "/")
LOG_PATH = "/var/log/tapd-autosnap.log"
SNAP_RE = re.compile(r'^\s*(\d+)\s+(\d+)\s+\*\s+\*\s+\*\s+/usr/local/bin/tapd\s+snap\s+(prod|dev)\b')
TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')


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


def ssh_run(cmd, timeout=60):
    full = 'ssh -n -F "%s" tapd "%s"' % (SSH_CFG, cmd.replace('"', '\\"'))
    r = subprocess.run([BASH, "-c", full], capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def read_crontab():
    rc, out = ssh_run("crontab -l 2>/dev/null")
    return [l.rstrip("\n") for l in out.splitlines() if l.strip()]


def write_crontab(lines):
    import tempfile
    fd, tmp_local = tempfile.mkstemp(suffix=".cron")
    os.close(fd)
    with open(tmp_local, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    cmd = 'scp -F "%s" "%s" "tapd:/tmp/.newcron"' % (SSH_CFG, tmp_local.replace("\\", "/"))
    subprocess.run([BASH, "-c", cmd], capture_output=True, timeout=60, check=True)
    rc, out = ssh_run("crontab /tmp/.newcron && rm -f /tmp/.newcron")
    os.remove(tmp_local)
    if rc != 0:
        print("[ERROR] 写入 crontab 失败: %s" % out)
        sys.exit(1)


def parse_jobs(lines):
    """→ {env: 'HH:MM'}"""
    jobs = {}
    for l in lines:
        m = SNAP_RE.match(l)
        if m:
            jobs[m.group(3)] = "%02d:%02d" % (int(m.group(2)), int(m.group(1)))
    return jobs


def cmd_status():
    jobs = parse_jobs(read_crontab())
    if not jobs:
        print("自动快照：已关闭")
        print("（开启后服务器每天定时自动拍摄生产/开发快照，日志: %s）" % LOG_PATH)
    else:
        print("自动快照：已开启")
        print("  生产快照: 每天 %s" % jobs.get("prod", "(未配置)"))
        print("  开发快照: 每天 %s" % jobs.get("dev", "(未配置)"))
        print("  日志: %s" % LOG_PATH)


def parse_time(v, label, default):
    v = (v or "").strip()
    if not v:
        v = default
    m = TIME_RE.match(v)
    if not m:
        print("[ERROR] %s 时间格式应为 HH:MM（24小时制），收到: %s" % (label, v))
        sys.exit(1)
    return int(m.group(1)), int(m.group(2))


def cmd_on(t_prod, t_dev):
    hh_p, mm_p = parse_time(t_prod, "生产", "02:00")
    if t_dev:
        hh_d, mm_d = parse_time(t_dev, "开发", None)
    else:
        # 开发默认=生产+10分钟（错峰，避免同时拍两份的 IO 峰值）；跨日回绕
        total = (hh_p * 60 + mm_p + 10) % (24 * 60)
        hh_d, mm_d = total // 60, total % 60
    lines = [l for l in read_crontab() if not SNAP_RE.match(l)]
    lines.append("%d %d * * * /usr/local/bin/tapd snap prod >> %s 2>&1" % (mm_p, hh_p, LOG_PATH))
    lines.append("%d %d * * * /usr/local/bin/tapd snap dev >> %s 2>&1" % (mm_d, hh_d, LOG_PATH))
    write_crontab(lines)
    print("自动快照已开启：生产 %02d:%02d / 开发 %02d:%02d" % (hh_p, mm_p, hh_d, mm_d))
    cmd_status()


def cmd_off():
    lines = [l for l in read_crontab() if not SNAP_RE.match(l)]
    write_crontab(lines)
    print("自动快照已关闭（crontab 其他条目未动）")
    cmd_status()


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: auto-snap-ctl.py <status|on|off> [生产HH:MM] [开发HH:MM]")
        return 2
    cmd = args[0]
    if cmd == "status":
        cmd_status()
    elif cmd == "on":
        cmd_on(args[1] if len(args) > 1 else "", args[2] if len(args) > 2 else "")
    elif cmd == "off":
        cmd_off()
    else:
        print("未知命令: %s（可用: status|on|off）" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
