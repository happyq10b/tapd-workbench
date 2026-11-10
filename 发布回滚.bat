@echo off
setlocal enabledelayedexpansion
title TAPD Workbench - Release Rollback

rem ================================================================
rem  TAPD Workbench - 发布回滚开关（2026-11-06 三环境版）
rem
rem  快照内容 = 代码 tar 包 + 一致性数据库，存于服务器
rem    /var/backups/tapd-workbench/release/<prod|dev>/<快照名>/
rem
rem  流程约定：
rem    · 发布前 sync.sh --prod 会自动拍快照（名字=时间戳）
rem    · 回滚 = 停服 → 恢复代码+DB → 启动 → 健康检查（约 20 秒）
rem    · 每次回滚前会自动再拍一次「回滚前快照」，可反复回滚
rem ================================================================

cd /d "%~dp0"

set "OPS=%~dp0ops"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "SRV_CTL=%~dp0ops\srv-ctl.py"
set "LOGDIR=%TEMP%\tapd-svc"

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

set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=0"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
if not exist "%VENV_PY%" (
  echo   [ERROR] Local venv not found: %VENV_PY%
  pause
  exit /b 1
)

:MENU
echo.
echo ================================================================
echo   TAPD Workbench . Release Rollback
echo ================================================================
echo   Workspace: %~dp0
echo.
echo   --- 快照查看 ---
echo   [1] 列出生产快照（prod）
echo   [2] 列出开发快照（dev）
echo   [3] 列出本地快照（local）
echo.
echo   --- 快照创建 ---
echo   [4] 立即拍生产快照
echo   [5] 立即拍开发快照
echo   [6] 立即拍本地快照
echo.
echo   --- 回滚（危险操作，恢复代码+数据库，约20秒停机）---
echo   [7] 回滚生产  → 选择快照
echo   [8] 回滚开发  → 选择快照
echo   [9] 回滚本地  → 选择快照
echo.
echo   --- 删除---
echo   [10] 删除本地快照 → 选择快照（仅删本地文件，需输入 yes 确认）
echo.
echo   [Q] Quit
echo ================================================================
echo.
choice /c 1234567890Q /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

if "%PICK%"=="11" goto :QUIT
if "%PICK%"=="10" "%VENV_PY%" "%~dp0ops\db-sync-ctl.py" delete & goto :AFTER
if "%PICK%"=="9" "%VENV_PY%" "%~dp0ops\db-sync-ctl.py" apply & goto :AFTER
if "%PICK%"=="6" "%VENV_PY%" "%~dp0ops\db-sync-ctl.py" snaplocal & goto :AFTER
if "%PICK%"=="3" "%VENV_PY%" "%~dp0ops\db-sync-ctl.py" list & goto :AFTER
if "%PICK%"=="1" call :SRV rollbacklist prod & goto :AFTER
if "%PICK%"=="2" call :SRV rollbacklist dev & goto :AFTER
if "%PICK%"=="4" call :SRV snap prod & goto :AFTER
if "%PICK%"=="5" call :SRV snap dev & goto :AFTER
if "%PICK%"=="7" goto :RB_PROD
if "%PICK%"=="8" goto :RB_DEV
goto :MENU

:RB_PROD
set "ENV=prod"
set "ENVCN=生产"
goto :RB_DO

:RB_DEV
set "ENV=dev"
set "ENVCN=开发"
goto :RB_DO

:RB_DO
echo.
echo   可用快照如下（第一行为最新）：
call :SRV rollbacklist %ENV%
echo.
set "SNAP="
set /p SNAP=   输入要回滚到的快照名（上面列表中的名称，直接回车取消）: 
if "%SNAP%"=="" goto :AFTER
echo.
echo   !! 即将把【%ENVCN%环境】的代码与数据库回滚到快照：%SNAP%
echo   !! 该快照之后产生的数据将不可见（回滚前会自动再拍一次快照留底）
set "CONFIRM="
set /p CONFIRM=   确认请输入 yes: 
if not "%CONFIRM%"=="yes" (
  echo   已取消。
  goto :AFTER
)
echo.
echo   开始回滚 ...
call :SRV rollback %ENV% %SNAP%
goto :AFTER

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

rem ---------- run a command on the server via SSH ----------
:SRV
set "SRV_ARGS=%*"
if defined ICONV (
  "%VENV_PY%" "%SRV_CTL%" %SRV_ARGS% > "%LOGDIR%\rb.out" 2>&1
  call :Drain "%LOGDIR%\rb.out"
) else (
  "%VENV_PY%" "%SRV_CTL%" %SRV_ARGS%
)
goto :eof

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
