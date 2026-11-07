@echo off
setlocal enabledelayedexpansion
title TAPD Workbench - Service Switch

rem ================================================================
rem  TAPD Workbench - One-Click Service Switch
rem
rem  Two environments in one menu:
rem    LOCAL     http://127.0.0.1:8100   (dev server, offline copy of DB)
rem    SERVER    https://123.207.252.195 (production, real data)
rem
rem  Local  : 1 start / 2 stop / 3 restart / 4 status / 5 open browser
rem  Server PROD : 6 status / 7 restart / 8 logs / A stop / B start
rem  Server DEV  : C stop / D start / E restart / F prod-data-to-dev
rem  DEV URL: https://123.207.252.195:8443   PROD URL: https://123.207.252.195
rem ================================================================

cd /d "%~dp0"

set "OPS=%~dp0ops"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "CTL_PY=%~dp0ops\local-ctl.py"
set "SRV_CTL=%~dp0ops\srv-ctl.py"
set "LOGDIR=%TEMP%\tapd-svc"

rem ---------- locate Git Bash ----------
set "BASH="
for %%P in (
  "C:\Program Files\Git\bin\bash.exe"
  "C:\Program Files (x86)\Git\bin\bash.exe"
  "C:\Git\bin\bash.exe"
  "D:\Git\bin\bash.exe"
  "D:\Program Files\Git\bin\bash.exe"
  "%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
  "%LOCALAPPDATA%\Programs\WorkBuddy\resources\vendor\PortableGit\bin\bash.exe"
) do (
  if not defined BASH (
    if exist %%P set "BASH=%%~P"
  )
)

rem ---------- locate iconv (UTF-8 -> GBK for bash output) ----------
set "ICONV="
for %%P in (
  "C:\Program Files\Git\usr\bin\iconv.exe"
  "C:\Program Files (x86)\Git\usr\bin\iconv.exe"
  "D:\Git\usr\bin\iconv.exe"
  "%LOCALAPPDATA%\Programs\Git\usr\bin\iconv.exe"
  "%LOCALAPPDATA%\Programs\WorkBuddy\resources\vendor\PortableGit\usr\bin\iconv.exe"
) do (
  if not defined ICONV (
    if exist %%P set "ICONV=%%~P"
  )
)

rem ---------- encoding ----------
rem cmd runs on code page 936 (GBK): Python must emit GBK; bash emits UTF-8,
rem so bash output goes through iconv when available.
set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=0"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

if not exist "%VENV_PY%" (
  echo.
  echo   [ERROR] Local venv not found: %VENV_PY%
  echo   Run once in Git Bash: cd ops && ./local-dev.sh
  echo.
  pause
  exit /b 1
)

:MENU
echo.
echo ================================================================
echo   TAPD Workbench . Service Switch
echo ================================================================
echo   Workspace: %~dp0
echo.
echo   --- LOCAL  (http://127.0.0.1:8100) ---
echo   [1] Start      启动本地开发服务（后台）
echo   [2] Stop       停止本地开发服务
echo   [3] Restart    重启本地开发服务
echo   [4] Status     查看本地服务状态
echo   [5] Open       打开浏览器
echo.
echo   --- SERVER PROD (https://123.207.252.195) ---
echo   [6] Status     双环境状态与健康检查
echo   [7] Restart    重启生产服务
echo   [8] Logs       查看生产日志(15秒)
echo   [A] Stop       生产停服（发布窗口用）
echo   [B] Start      生产恢复
echo.
echo   --- SERVER DEV (https://123.207.252.195:8443) ---
echo   [C] Dev-Stop     开发停服
echo   [D] Dev-Start    开发恢复
echo   [E] Dev-Restart  开发重启（代码改动后）
echo   [F] Data-Sync    生产数据回迁开发库
echo.
echo   [Q] Quit
echo ================================================================
echo.
rem 选项里刻意不含 8/9：这两个功能已从菜单隐藏，仅保留代码供直接调用
rem 退出用 Q 而不是 0 —— 数字 0 在 choice 里会与最后一个数字键的 errorlevel 撞车
choice /c 12345678ABCDEFQ /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

rem 'choice' returns 1..10 for a valid pick; 0 for key 0.
rem On EOF / aborted input it returns 1 as well, so validate the value
rem explicitly instead of relying on 'if errorlevel N' ranges.
if "%PICK%"=="15" goto :QUIT
if "%PICK%"=="1" goto :LOC_START
if "%PICK%"=="2" goto :LOC_STOP
if "%PICK%"=="3" goto :LOC_RESTART
if "%PICK%"=="4" goto :LOC_STATUS
if "%PICK%"=="5" goto :OPEN_BROWSER
if "%PICK%"=="6" goto :SRV_STATUS
if "%PICK%"=="7" goto :SRV_RESTART
if "%PICK%"=="8" goto :SRV_LOGS
if "%PICK%"=="9" goto :SRV_PROD_STOP
if "%PICK%"=="10" goto :SRV_PROD_START
if "%PICK%"=="11" goto :SRV_DEV_STOP
if "%PICK%"=="12" goto :SRV_DEV_START
if "%PICK%"=="13" goto :SRV_DEV_RESTART
if "%PICK%"=="14" goto :SRV_DEVDB
echo   Invalid selection.
goto :MENU

rem ================================================================
rem  LOCAL
rem ================================================================
:LOC_START
echo.
echo   Starting local dev service ...
"%VENV_PY%" "%CTL_PY%" start
goto :AFTER

:LOC_STOP
echo.
echo   Stopping local dev service ...
"%VENV_PY%" "%CTL_PY%" stop
goto :AFTER

:LOC_RESTART
echo.
echo   Restarting local dev service ...
"%VENV_PY%" "%CTL_PY%" restart
goto :AFTER

:LOC_STATUS
echo.
"%VENV_PY%" "%CTL_PY%" status
goto :AFTER

:OPEN_BROWSER
start "" "http://127.0.0.1:8100/login"
echo   Browser opened: http://127.0.0.1:8100/login
goto :AFTER

rem ================================================================
rem  SERVER
rem ================================================================
:SRV_STATUS
call :SRV status
goto :AFTER

:SRV_RESTART
echo.
echo   Restarting production service on server ...
call :SRV restart
:SRV_LOGS
echo.
call :SRV logs 60

:SRV_PROD_STOP
echo.
echo   停止生产服务（发布窗口）。期间用户无法访问，恢复请选 [B]。
call :SRV stopprod
goto :AFTER

:SRV_PROD_START
echo.
echo   恢复生产服务 ...
call :SRV startprod
goto :AFTER

:SRV_DEV_STOP
echo.
echo   停止开发服务（https://123.207.252.195:8443 将不可访问）...
call :SRV stopdev
goto :AFTER

:SRV_DEV_START
echo.
echo   恢复开发服务 ...
call :SRV startdev
goto :AFTER

:SRV_DEV_RESTART
echo.
echo   重启开发服务 ...
call :SRV devrestart
goto :AFTER

:SRV_DEVDB
echo.
echo   生产数据回迁开发库（一致性快照，dev 停机几秒，生产不受影响）...
call :SRV devdb-sync
goto :AFTER   ← 用带行数的 logs（不带行数是 tail -f，会一直挂着不返回）
goto :AFTER

rem ---------- run a command on the server via SSH ----------
rem 'tapd' is the toolbox installed on the SERVER (/usr/local/bin/tapd),
rem so it must run over SSH - not locally.
rem The actual call is delegated to ops/srv-ctl.py: doing the path building
rem and quote nesting inside a .bat is fragile (backslash-escaped quotes,
rem spaces inside variables), so Python handles it instead.
rem Usage: call :SRV <sub-command> [args...]
rem NOTE: use %1 %2 ... explicitly instead of %* - 'call' re-parses %* and
rem can split a multi-word argument (e.g. "logs 60") into separate tokens.
:SRV
set "SRV_ARGS=%*"
if defined ICONV (
  "%VENV_PY%" "%SRV_CTL%" %SRV_ARGS% > "%LOGDIR%\srv.out" 2>&1
  call :Drain "%LOGDIR%\srv.out"
) else (
  "%VENV_PY%" "%SRV_CTL%" %SRV_ARGS%
)
goto :eof

rem ---------- drain a UTF-8 file to the console as GBK ----------
rem iconv -c is required: without it, a single unconvertible char (e.g. U+2713)
rem aborts the whole conversion and truncates the output.
:Drain
set "LF=%~1"
if not exist "%LF%" goto :eof
set "CONV=%LF%.gbk"
if defined ICONV (
  "%ICONV%" -c -f UTF-8 -t GBK "%LF%" > "%CONV%" 2>nul
  if exist "%CONV%" (
    type "%CONV%"
    del "%CONV%" >nul 2>&1
    goto :eof
  )
)
type "%LF%"
goto :eof

:AFTER
echo.
echo   ------------------------------------------------------------
echo.
choice /c YN /n /m "   Back to menu? (Y/N): "
set "AGAIN=%ERRORLEVEL%"
if "%AGAIN%"=="2" goto :QUIT
goto :MENU

:QUIT
echo.
echo   Bye.
echo.
exit /b 0
