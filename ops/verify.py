#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TAPD 工作台 · 本地验证门禁（verify）

交付流程的第一阶段：所有代码变更必须先在这里通过验证，
才允许执行 sync.sh 同步到远程环境。

检查项（全部通过才算通过）：
  1. Python 语法编译        —— py_compile app/app.py app/init_db.py
  2. JS 语法检查            —— 抽出 index.html 的 <script> 块跑 node --check
  3. 依赖完整性            —— requirements.txt 里的包都能 import
  4. 应用可导入            —— import app 不抛异常
  5. 数据库完整性          —— PRAGMA integrity_check == ok
  6. 端到端冒烟            —— 起服务 → 登录 → 核心 API → xlsx 导出 → 无合并单元格
  7. git 工作区状态        —— 有未提交改动时警告（不阻断）

产出：ops/.verify-stamp（记录代码指纹 + 时间），sync.sh 会校验它。
用法：
  python ops/verify.py            # 完整验证
  python ops/verify.py --quick    # 跳过端到端冒烟（1~4 项）
  python ops/verify.py --stamp-only  # 只按当前代码重新签发凭证
"""
import os
import re
import sys
import json
import time
import hashlib
import socket
import subprocess
import tempfile
import shutil
import urllib.request
import urllib.error

# 输出编码自适应：
#   - 被 Windows cmd 调用时（码页 936/GBK），按 GBK 输出，避免中文乱码
#   - 在 Git Bash / 终端里时，按 UTF-8 输出
def _setup_output_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (os.environ.get("PYTHONIOENCODING") or "").lower()
            if "gbk" in enc or "gb2312" in enc or "gb18030" in enc:
                stream.reconfigure(encoding="gbk", errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_setup_output_encoding()

HERE = os.path.dirname(os.path.abspath(__file__))
OPS = HERE
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
VENV = os.path.join(OPS, ".localvenv")
PY = os.path.join(VENV, "Scripts", "python.exe")
STAMP = os.path.join(OPS, ".verify-stamp")
TEST_PORT = int(os.environ.get("VERIFY_PORT", "8123"))
TEST_HOST = "127.0.0.1"

C_G = "\033[32m"; C_R = "\033[31m"; C_Y = "\033[33m"; C_B = "\033[36m"; C_D = "\033[2m"; C_0 = "\033[0m"

_results = []      # (序号, 名称, 通过?, 详情)
_failed = False


def log(msg, color=C_B):
    print(f"{color}{msg}{C_0}", flush=True)


def step(no, name, ok, detail=""):
    _results.append((no, name, ok, detail))
    global _failed
    mark = f"{C_G}✓{C_0}" if ok else f"{C_R}✗{C_0}"
    print(f"  {mark} [{no}] {name}" + (f"  {C_D}{detail}{C_0}" if detail else ""), flush=True)
    if not ok:
        _failed = True
    return ok


def run(cmd, cwd=None, timeout=180):
    """执行命令，返回 (returncode, stdout+stderr)"""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "命令超时"
    except Exception as e:
        return 1, str(e)


# ---------- 1. Python 语法 ----------
def check_python_syntax():
    files = [os.path.join(SRC, "app", "app.py"), os.path.join(SRC, "app", "init_db.py")]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        return step(1, "Python 语法编译", False, f"文件缺失: {missing}")
    rc, out = run([PY, "-m", "py_compile"] + files)
    return step(1, "Python 语法编译", rc == 0, out.strip()[:200])


# ---------- 2. JS 语法 ----------
def check_js_syntax():
    html = os.path.join(SRC, "static", "index.html")
    if not os.path.exists(html):
        return step(2, "JS 语法检查", False, "index.html 不存在")
    with open(html, encoding="utf-8") as f:
        s = f.read().replace("\r\n", "\n")
    blocks = re.findall(r"<script>(.*?)</script>", s, re.S)
    if not blocks:
        return step(2, "JS 语法检查", False, "未找到 <script> 块")
    tmp = os.path.join(tempfile.gettempdir(), "_tapd_check.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    if shutil.which("node") is None:
        os.remove(tmp)
        return step(2, "JS 语法检查", False, "未找到 node 可执行文件")
    rc, out = run(["node", "--check", tmp])
    try:
        os.remove(tmp)
    except OSError:
        pass
    return step(2, "JS 语法检查", rc == 0, f"{len(blocks)} 个 script 块" if rc == 0 else out.strip()[:200])


# ---------- 3. 依赖完整性 ----------
def check_dependencies():
    req = os.path.join(SRC, "requirements.txt")
    if not os.path.exists(req):
        return step(3, "依赖完整性", False, "requirements.txt 不存在")
    pkgs = []
    with open(req, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                name = re.split(r"[><=\[]", line)[0].strip()
                if name:
                    pkgs.append(name)
    if not pkgs:
        return step(3, "依赖完整性", False, "requirements.txt 为空")
    # 包名 != 模块名的映射（pip 名 → import 名）
    MOD_ALIAS = {
        "python-multipart": "multipart",   # FastAPI 解析 multipart 表单需要
        "pyyaml": "yaml",
        "pillow": "PIL",
        "beautifulsoup4": "bs4",
        "python-dateutil": "dateutil",
        "protobuf": "google.protobuf",
    }
    mods = [MOD_ALIAS.get(p, p.replace("-", "_")) for p in pkgs]
    code = "import importlib,sys\n" \
           "mods=%r\n" \
           "bad=[]\n" \
           "for m in mods:\n" \
           "    try: importlib.import_module(m)\n" \
           "    except Exception as e: bad.append(m+':'+str(e)[:60])\n" \
           "print('\\n'.join(bad) if bad else 'ALL_OK')\n" % (mods,)
    rc, out = run([PY, "-c", code])
    ok = rc == 0 and "ALL_OK" in out
    return step(3, "依赖完整性", ok, f"{len(pkgs)} 个包" if ok else out.strip()[:200])


# ---------- 4. 应用可导入 ----------
def check_app_import():
    """以包方式导入（app/__init__.py 不存在时用 importlib 走 app.app），
    避免 sys.path 直接指向 app/ 导致 app.init_db 相对导入失败。"""
    code = (
        "import os,sys,importlib\n"
        "os.chdir(%r)\n"
        "sys.path.insert(0, os.getcwd())\n"
        "m=importlib.import_module('app.app')\n"
        "assert hasattr(m,'app'), 'FastAPI 实例缺失'\n"
        "routes=len(m.app.routes)\n"
        "print('IMPORT_OK routes=%%d' %% routes)\n" % SRC
    )
    rc, out = run([PY, "-c", code], cwd=SRC)
    ok = "IMPORT_OK" in out
    detail = " ".join(l for l in out.strip().split("\n") if l.startswith("IMPORT_OK"))
    if not ok:
        # 过滤掉已知的 init_db 噪音，只留真实错误
        errs = [l for l in out.strip().split("\n")
                if l.strip() and not l.startswith("WARN: init_db()")]
        detail = " | ".join(errs[-3:])[:180]
    return step(4, "应用可导入", ok, detail or out.strip()[-120:])


# ---------- 5. 数据库完整性 ----------
def check_db():
    db = os.path.join(SRC, "app.db")
    if not os.path.exists(db):
        return step(5, "数据库完整性", False, "本地无 app.db（跳过）")
    code = (
        "import sqlite3\n"
        "c=sqlite3.connect(%r)\n"
        "print('INTEGRITY', c.execute('PRAGMA integrity_check').fetchone()[0])\n"
        "print('CARDS', c.execute('SELECT COUNT(*) FROM cards WHERE deleted=0').fetchone()[0])\n"
        % db
    )
    rc, out = run([PY, "-c", code])
    ok = "INTEGRITY ok" in out
    return step(5, "数据库完整性", ok, out.strip().replace("\n", " ")[:120])


# ---------- 6. 端到端冒烟 ----------
def wait_port(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((TEST_HOST, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def wait_http(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status
        except urllib.error.HTTPError:
            return 200          # 有响应即可
        except Exception:
            time.sleep(0.4)
    return None


def check_smoke():
    """起一个临时服务，跑核心链路"""
    if not os.path.exists(PY):
        return step(6, "端到端冒烟", False, "虚拟环境不存在")
    env = dict(os.environ)
    env["APP_SECRET"] = "verify-smoke-secret"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.app:app", "--host", TEST_HOST, "--port", str(TEST_PORT)],
        cwd=SRC, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://{TEST_HOST}:{TEST_PORT}"
        if not wait_port(TEST_PORT, 30):
            return step(6, "端到端冒烟", False, "服务未能启动")
        if wait_http(base + "/login", 20) is None:
            return step(6, "端到端冒烟", False, "/login 无响应")

        # 登录
        token = None
        try:
            req = urllib.request.Request(
                base + "/api/login",
                data=json.dumps({"username": "admin", "password": "At159357"}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                token = json.loads(r.read()).get("token")
        except Exception as e:
            return step(6, "端到端冒烟", False, f"登录失败: {str(e)[:80]}")
        if not token:
            return step(6, "端到端冒烟", False, "登录未返回 token")

        hdr = {"Authorization": "Bearer " + token}

        # 核心 API
        for path in ("/api/me", "/api/boards", "/api/board-config"):
            try:
                with urllib.request.urlopen(urllib.request.Request(base + path, headers=hdr), timeout=15) as r:
                    if r.status != 200:
                        return step(6, "端到端冒烟", False, f"{path} → {r.status}")
            except Exception as e:
                return step(6, "端到端冒烟", False, f"{path} 请求失败: {str(e)[:60]}")

        # xlsx 导出：内容类型 + 零合并单元格
        xlsx_path = os.path.join(tempfile.gettempdir(), "_verify_export.xlsx")
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(base + "/api/export/xlsx", headers=hdr), timeout=90) as r:
                ctype = r.headers.get("Content-Type", "")
                data = r.read()
            if "spreadsheetml" not in ctype:
                return step(6, "端到端冒烟", False, f"xlsx MIME 错误: {ctype}")
            if not data.startswith(b"PK"):
                return step(6, "端到端冒烟", False, "xlsx 不是合法 zip")
            with open(xlsx_path, "wb") as f:
                f.write(data)
        except Exception as e:
            return step(6, "端到端冒烟", False, f"xlsx 导出失败: {str(e)[:80]}")

        # 用 openpyxl 校验零合并单元格
        code = (
            "import openpyxl\n"
            "wb=openpyxl.load_workbook(%r)\n"
            "ws=wb.worksheets[0]\n"
            "m=len(ws.merged_cells.ranges)\n"
            "print('MERGED',m)\n"
            "print('ROWS',ws.max_row)\n"
            "print('COLS',ws.max_column)\n"
            "assert m==0, '存在合并单元格'\n" % xlsx_path
        )
        rc, out = run([PY, "-c", code])
        try:
            os.remove(xlsx_path)
        except OSError:
            pass
        if rc != 0:
            return step(6, "端到端冒烟", False, out.strip()[-150:])

        detail = " ".join(x for x in out.strip().split("\n") if x.startswith(("MERGED", "ROWS", "COLS")))
        return step(6, "端到端冒烟", True, detail)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ---------- 7. git 状态 ----------
def check_git():
    rc, out = run(["git", "status", "--short"], cwd=SRC)
    changed = [l for l in out.strip().split("\n") if l.strip()]
    if not changed:
        return step(7, "git 工作区状态", True, "干净")
    return step(7, "git 工作区状态", True, f"{len(changed)} 处未提交（不阻断）")


# ---------- 代码指纹 & 凭证 ----------
def code_fingerprint():
    """对被同步的代码内容取指纹（与文件 mtime 无关，内容变了指纹就变）"""
    h = hashlib.sha256()
    targets = []
    for d in ("app", "static"):
        base = os.path.join(SRC, d)
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
            for fn in sorted(files):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                targets.append(os.path.join(root, fn))
    for extra in ("requirements.txt", "manage_users.py"):
        p = os.path.join(SRC, extra)
        if os.path.exists(p):
            targets.append(p)
    for p in sorted(targets):
        rel = os.path.relpath(p, SRC).replace("\\", "/")
        try:
            with open(p, "rb") as f:
                h.update(rel.encode() + b":" + hashlib.sha256(f.read()).digest())
        except OSError:
            continue
    return h.hexdigest()


def write_stamp(fp):
    data = {"fingerprint": fp, "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": int(time.time())}
    tmp = STAMP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STAMP)
    return data


def read_stamp():
    if not os.path.exists(STAMP):
        return None
    try:
        with open(STAMP, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    quick = "--quick" in sys.argv
    stamp_only = "--stamp-only" in sys.argv

    log("═" * 62)
    log(" TAPD 工作台 · 本地验证门禁（阶段一：本地执行与验证）")
    log("═" * 62)

    if stamp_only:
        fp = code_fingerprint()
        d = write_stamp(fp)
        log(f"{C_G}已重新签发验证凭证{C_0}  {d['verified_at']}  fp={fp[:16]}")
        return 0

    print()
    log(f"{C_B}检查项{C_0}")
    check_python_syntax()
    check_js_syntax()
    check_dependencies()
    check_app_import()
    check_db()
    if not quick:
        check_smoke()
    else:
        log(f"  {C_Y}—{C_0} [6] 端到端冒烟  {C_D}--quick 已跳过{C_0}")
    check_git()

    print()
    total = len(_results)
    passed = sum(1 for r in _results if r[2])
    if _failed:
        log(f"{C_R}✗ 验证未通过：{passed}/{total} 项通过{C_0}")
        log(f"{C_R}  禁止执行 sync.sh —— 请先修复上述失败项{C_0}")
        log(f"{C_R}  失败项: " + ", ".join(r[1] for r in _results if not r[2]) + f"{C_0}")
        return 1

    fp = code_fingerprint()
    d = write_stamp(fp)
    log(f"{C_G}✓ 验证通过：{passed}/{total} 项全部通过{C_0}")
    log(f"{C_G}  验证凭证已签发{C_0}  {d['verified_at']}")
    log(f"{C_D}  fingerprint={fp[:32]}{C_0}")
    print()
    log(f"{C_B}阶段一完成。下一步由你手动触发阶段二：{C_0}")
    log(f"{C_B}  cd ops && ./sync.sh --dev   （推到服务器开发环境）{C_0}")
    log(f"{C_B}  cd ops && ./sync.sh --prod  （推到生产环境）{C_0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
