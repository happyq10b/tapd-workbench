#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TAPD 工作台 · 本地开发看门狗（Windows 专用）

为什么不用 uvicorn --reload：
    uvicorn 的 reloader 在 Windows 上第一次触发后，reload 进程会卡死，
    表现为「日志停在 Reloading...，服务还在响但代码永远不更新」。
    （Linux 服务器上 --reload 稳定，不受影响）

本脚本替代 --reload：
    轮询源码目录的文件指纹 → 变化则优雅重启 uvicorn 子进程
    指纹用 (mtime_ns, size) 组合，避开 Windows 1~2 秒的时间戳精度问题
"""
import os
import sys
import time
import signal
import subprocess
import hashlib
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))   # ops/ 目录
OPS = HERE                                          # venv 与本脚本同级
SRC = os.path.join(os.path.dirname(HERE), "src")    # 工作空间根/src
VENV = os.path.join(OPS, ".localvenv")
PY = os.path.join(VENV, "Scripts", "python.exe")
PORT = int(os.environ.get("PORT", "8100"))
HOST = "127.0.0.1"
WATCH_DIRS = [os.path.join(SRC, "app"), os.path.join(SRC, "static")]
POLL_INTERVAL = 0.4          # 轮询间隔（秒）
STARTUP_TIMEOUT = 25         # 等待服务起来的最长秒数
RESTART_COOLDOWN = 1.0       # 重启后冷却，避免连续改文件反复重启

C_G = "\033[32m"; C_Y = "\033[33m"; C_R = "\033[31m"; C_B = "\033[36m"; C_0 = "\033[0m"


def log(msg, color=C_B):
    print(f"{color}[dev]{C_0} {msg}", flush=True)


def fingerprint():
    """计算被监控目录的指纹：文件路径 + mtime_ns + size"""
    h = hashlib.sha256()
    for d in WATCH_DIRS:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
            for fn in sorted(files):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                rel = os.path.relpath(p, SRC).replace("\\", "/")
                h.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return h.hexdigest()


def wait_ready(timeout=STARTUP_TIMEOUT):
    """轮询直到服务能响应 /login"""
    deadline = time.time() + timeout
    url = f"http://{HOST}:{PORT}/login"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except urllib.error.HTTPError:
            return True          # 有响应即算起来（比如 404/401）
        except Exception:
            time.sleep(0.3)
    return False


def stop_proc(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
        log("旧进程已退出", C_G)
    except subprocess.TimeoutExpired:
        log("优雅退出超时，强制结束", C_Y)
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    except Exception as e:
        log(f"停止进程异常: {e}", C_Y)


def start_proc():
    env = dict(os.environ)
    env["APP_SECRET"] = env.get("APP_SECRET", "local-dev-secret-not-for-production")
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [PY, "-m", "uvicorn", "app.app:app",
           "--host", HOST, "--port", str(PORT)]
    proc = subprocess.Popen(cmd, cwd=SRC, env=env)
    if wait_ready():
        log(f"服务已就绪  http://{HOST}:{PORT}/", C_G)
    else:
        log("服务启动超时，请检查上方日志", C_R)
    return proc


def main():
    if not os.path.exists(PY):
        print(f"{C_R}找不到虚拟环境: {PY}{C_0}")
        print("请先运行 ops/local-dev.sh 首次会创建 venv")
        return 1
    if not os.path.isdir(os.path.join(SRC, "app")):
        print(f"{C_R}找不到源码目录: {SRC}{C_0}")
        return 1

    log(f"看门狗启动  端口 {PORT}  监控 {', '.join(os.path.basename(d) for d in WATCH_DIRS)}")
    log("改代码会自动重启（Ctrl+C 退出）")

    proc = start_proc()
    last_fp = fingerprint()
    cooldown_until = 0.0

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            if time.time() < cooldown_until:
                continue
            fp = fingerprint()
            if fp != last_fp:
                last_fp = fp
                log("检测到文件变化，正在重启...", C_Y)
                stop_proc(proc)
                time.sleep(RESTART_COOLDOWN)
                proc = start_proc()
                last_fp = fingerprint()
                cooldown_until = time.time() + RESTART_COOLDOWN
    except KeyboardInterrupt:
        log("退出中...")
        stop_proc(proc)
    except Exception as e:
        log(f"看门狗异常: {e}", C_R)
        stop_proc(proc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
