# -*- coding: utf-8 -*-
"""
本地开发服务控制器（Windows）

为什么用 Python 而不是 bash：
  Windows 上用 bash 管理后台进程不可靠 —— 进程会随终端关闭而退出、
  taskkill 有时杀不掉残留进程、端口会留下"僵尸 socket"（进程已死但端口不释放）。
  这里统一用 Python 管理 PID 文件 + 端口探测，行为可预期。

用法：
    python local-ctl.py start     后台启动（脱离终端）
    python local-ctl.py stop      停止
    python local-ctl.py restart   重启
    python local-ctl.py status    查看状态
    python local-ctl.py run       前台运行（Ctrl+C 停止，等同 local-dev.sh 旧行为）
"""
import os
import re
import sys
import time
import socket
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))   # .../ops
OPS = HERE
SRC = os.path.join(HERE, "..", "src")
VENV = os.path.join(HERE, ".localvenv")
PY = os.path.join(VENV, "Scripts", "python.exe")
WATCHDOG = os.path.join(HERE, "dev-watchdog.py")
PIDFILE = os.path.join(HERE, ".localdev.pid")
LOGFILE = os.path.join(HERE, ".localdev.log")
PORT = int(os.environ.get("PORT", "8100"))

# Windows 进程创建标志
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def eprint(s):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def venv_python():
    """返回可用的解释器：优先 venv，回退到系统 python"""
    if os.path.exists(PY):
        return PY
    return sys.executable


def port_in_use(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def http_probe(port, timeout=4):
    import urllib.request
    try:
        r = urllib.request.urlopen("http://127.0.0.1:%d/login" % port, timeout=timeout)
        return r.status
    except Exception:
        return 0


def read_pid():
    try:
        with open(PIDFILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def run_cmd(args, timeout=30):
    """执行系统命令并安全解码：Windows 中文版 tasklist/wmic 输出是 GBK，不是 UTF-8"""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
    except Exception:
        return ""
    raw = r.stdout or b""
    if isinstance(raw, bytes):
        for enc in ("utf-8", "gbk", "mbcs", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", "replace")
    return raw


def pid_alive(pid):
    if not pid:
        return False
    out = run_cmd(["tasklist", "/FI", "PID eq %d" % pid, "/NH", "/FO", "CSV"], timeout=15)
    # 形如 "python.exe","1234","Console","1","10,000 K"
    return ('"%d"' % pid) in out


def find_watchdog_pids():
    """兜底：按命令行特征找出所有看门狗/uvicorn 进程
    wmic CSV 格式固定为 Node,CommandLine,ProcessId —— PID 只能取**最后一个字段**。
    （早期版本用正则把所有数字当 PID 候选，会把命令行里的端口号等误当 PID 而误杀进程。）"""
    pids = []
    out = run_cmd(["wmic", "process", "where", "name='python.exe'",
                   "get", "ProcessId,CommandLine", "/FORMAT:CSV"], timeout=30)
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Node,"):
            continue
        # 拆 CSV：Node, CommandLine, ProcessId
        parts = line.split(",")
        if len(parts) < 3:
            continue
        cmdline = ",".join(parts[1:-1])
        pid_txt = parts[-1].strip()
        if not pid_txt.isdigit():
            continue
        pid = int(pid_txt)
        # 双重校验：命令行特征 + 进程确实存活
        is_watchdog = "dev-watchdog.py" in cmdline
        is_uvicorn = ("uvicorn" in cmdline and "app.app:app" in cmdline
                      and "--port %d" % PORT in cmdline)
        if (is_watchdog or is_uvicorn) and pid_alive(pid):
            pids.append(pid)
    return sorted(set(pids))


def kill_tree(pid):
    """杀掉进程树（/T 连子进程一起），返回是否成功"""
    out = run_cmd(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=20)
    return ("successfully" in out.lower() or "成功" in out
            or "terminated" in out.lower() or not pid_alive(pid))


def do_start():
    if port_in_use(PORT):
        eprint("  端口 %d 已被占用，先执行 stop 再 start" % PORT)
        return 1
    if not os.path.exists(WATCHDOG):
        eprint("  找不到 %s" % WATCHDOG)
        return 1
    env = dict(os.environ)
    env["APP_SECRET"] = "local-dev-secret-not-for-production"
    env["PYTHONUTF8"] = "1"
    env["PORT"] = str(PORT)
    env["PYTHONIOENCODING"] = "utf-8"
    log = open(LOGFILE, "a", encoding="utf-8", buffering=1)
    log.write("\n===== start %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    try:
        p = subprocess.Popen(
            [venv_python(), WATCHDOG],
            cwd=SRC, env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=flags)
    except Exception as ex:
        eprint("  启动失败: %s" % ex)
        return 1
    with open(PIDFILE, "w", encoding="utf-8") as f:
        f.write(str(p.pid))
    eprint("  已在后台启动 (PID %d)" % p.pid)
    # 等待就绪
    for _ in range(40):
        time.sleep(0.5)
        code = http_probe(PORT, timeout=2)
        if code:
            eprint("  服务就绪  http://127.0.0.1:%d/  (HTTP %d)" % (PORT, code))
            return 0
    eprint("  已启动但未在 20 秒内就绪，请查看日志: %s" % LOGFILE)
    return 1


def do_stop():
    pid = read_pid()
    killed = []
    if pid and pid_alive(pid):
        if kill_tree(pid):
            killed.append(pid)
    # 兜底清理残留（含之前用其他方式启动、没写 PID 文件的进程）
    for p in find_watchdog_pids():
        if p in killed:
            continue
        if kill_tree(p):
            killed.append(p)
    # 等待端口释放（含僵尸 socket 情况：进程已死但端口未释放）
    released = False
    for _ in range(24):
        if not port_in_use(PORT):
            released = True
            break
        time.sleep(0.5)
    try:
        os.remove(PIDFILE)
    except OSError:
        pass
    if killed:
        eprint("  已停止进程: %s" % ", ".join(str(x) for x in killed))
    else:
        eprint("  没有找到运行中的本地服务进程")
    if released:
        eprint("  端口 %d 已释放" % PORT)
        return 0
    eprint("  ⚠ 端口 %d 仍被占用（可能有其他程序占用该端口）" % PORT)
    return 1


def do_status():
    pid = read_pid()
    alive = pid_alive(pid)
    code = http_probe(PORT)
    eprint("  本地开发服务 (端口 %d)" % PORT)
    eprint("    PID 文件 : %s" % (PIDFILE if pid else "无"))
    eprint("    进程     : %s" % ("运行中 (PID %s)" % pid if alive else "未运行"))
    eprint("    HTTP     : %s" % ("%d 正常" % code if code else "无响应"))
    eprint("    日志     : %s" % LOGFILE)
    return 0 if code else 1


def do_restart():
    do_stop()
    time.sleep(1)
    return do_start()


def do_run():
    """前台运行（等价于旧的 local-dev.sh 行为）"""
    env = dict(os.environ)
    env["APP_SECRET"] = "local-dev-secret-not-for-production"
    env["PYTHONUTF8"] = "1"
    env["PORT"] = str(PORT)
    os.chdir(SRC)
    return subprocess.call([venv_python(), WATCHDOG], env=env)


CMDS = {
    "start": do_start,
    "stop": do_stop,
    "restart": do_restart,
    "status": do_status,
    "run": do_run,
}

if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    fn = CMDS.get(cmd)
    if not fn:
        eprint("未知命令: %s（可用: %s）" % (cmd, "/".join(CMDS)))
        sys.exit(2)
    sys.exit(fn() or 0)
