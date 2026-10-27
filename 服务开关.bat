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
rem  Server : 6 status / 7 restart prod / 8 switch to dev / 9 back to prod / 10 logs
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
echo   --- SERVER (https://123.207.252.195) ---
echo   [6] Status     查看服务器服务状态
echo   [7] Restart    重启生产服务
rem   [8] To Dev     切到开发模式（占用 8000）  <- 已隐藏，日常用同步开关
rem   [9] To Prod    切回生产模式                 <- 已隐藏，日常用同步开关
echo   [8] Logs      查看服务器日志
echo.
echo   备注: [8] 切开发 / [9] 切生产 已从菜单隐藏（保留代码与备查注释）。
echo         日常切环境请用根目录「同步开关.bat」：选项 1 = 开发，选项 2 = 生产。
echo         如需手动切：cd ops ^&^& python srv-ctl.py dev   （切回用 stopdev）
echo.
echo   [Q] Quit
echo ================================================================
echo.
rem 选项里刻意不含 8/9：这两个功能已从菜单隐藏，仅保留代码供直接调用
rem 退出用 Q 而不是 0 —— 数字 0 在 choice 里会与最后一个数字键的 errorlevel 撞车
choice /c 12345678Q /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

rem 'choice' returns 1..10 for a valid pick; 0 for key 0.
rem On EOF / aborted input it returns 1 as well, so validate the value
rem explicitly instead of relying on 'if errorlevel N' ranges.
if "%PICK%"=="9" goto :QUIT
if "%PICK%"=="1" goto :LOC_START
if "%PICK%"=="2" goto :LOC_STOP
if "%PICK%"=="3" goto :LOC_RESTART
if "%PICK%"=="4" goto :LOC_STATUS
if "%PICK%"=="5" goto :OPEN_BROWSER
if "%PICK%"=="6" goto :SRV_STATUS
if "%PICK%"=="7" goto :SRV_RESTART
if "%PICK%"=="8" goto :SRV_LOGS
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
goto :AFTER

rem ---- 以下两个分支已从菜单隐藏（编号 8/9 不在 choice 选项里，无法从菜单触发）----
rem 保留是为了代码完整与备查；日常切环境用「同步开关.bat」，或直接：
rem   cd ops && python srv-ctl.py dev      切开发模式
rem   cd ops && python srv-ctl.py stopdev  切回生产模式
:SRV_DEV
echo.
echo   Switching server to DEV mode ...
call :SRV dev
goto :AFTER

:SRV_PROD
echo.
echo   Switching server back to PROD mode ...
call :SRV stopdev
goto :AFTER

:SRV_LOGS
echo.
call :SRV logs 60   ← 用带行数的 logs（不带行数是 tail -f，会一直挂着不返回）
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
