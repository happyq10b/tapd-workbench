@echo off
setlocal enabledelayedexpansion
title TAPD Workbench - DB Sync ^&^& Rollback

rem ================================================================
rem  TAPD Workbench - 数据库快照 同步与回滚开关（2026-11-07）
rem
rem  快照存储: data\db-snapshots\YYYYMMDD-HHMMSS\app.db + meta.txt
rem
rem  [1] Pull       服务器生产库 → 本地快照库（服务器先拍一致性快照，不停服）
rem  [2] Snap-Local 拍本地库快照（留存本地当前数据，8100 运行中可拍）
rem  [3] List       查看本地已有快照（时间倒序 + 来源标签）
rem  [4] Apply      选定快照 → 本地开发环境(8100)数据源（当前本地库自动留底）
rem  [5] Rollback   选定快照 → 服务器库（高危！双确认，服务器自动留底）
rem  [6] Org-Rollback 按架构部门回滚
rem  [7] Delete     删除本地快照（只删本地）
rem ================================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "CTL_PY=%~dp0ops\db-sync-ctl.py"
set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=0"

if not exist "%VENV_PY%" (
  echo   [ERROR] Local venv not found: %VENV_PY%
  pause
  exit /b 1
)

:MENU
echo.
echo ================================================================
echo   TAPD Workbench . DB Sync ^& Rollback
echo ================================================================
echo   Workspace: %~dp0
echo   快照目录  : data\db-snapshots\
echo.
echo   --- 快照拉取 ---
echo   [1] Pull-Prod    拉取生产库数据到本地
echo   [2] Pull-Dev     拉取开发库数据到本地
echo   [3] Snap-Local   拉取本地库快照（留存本地当前数据）
echo   [4] List         列出本地快照
echo   [5] Pull-Release 服务器发布快照下载到本地（选环境 / 代码+数据库）
echo.
echo   --- 快照使用 ---
echo   [6] Apply        应用快照为本地开发环境数据源
echo   [7] Rollback     本地快照回滚到服务器库（选：生产 / 开发）
echo   [8] Org-Rollback 按架构部门回滚（核算/商务/总账/管理/资金/财务中心）
echo.
echo   --- 快照删除 ---
echo   [9] Delete       删除本地快照（只删本地，不影响服务器）
echo.
echo   --- 自动快照（服务器每日定时）---
echo   [A] 自动快照设置   开关与拍摄时间（状态见子菜单）
echo.
echo   （「保留近10份」策略由服务器自动执行，无需配置）
echo.
echo   [Q] Quit
echo ================================================================
echo.
choice /c 123456789AQ /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

if "%PICK%"=="11" goto :QUIT
if "%PICK%"=="10" goto :AUTOSNAP
if "%PICK%"=="1" "%VENV_PY%" "%CTL_PY%" pull prod & goto :AFTER
if "%PICK%"=="2" "%VENV_PY%" "%CTL_PY%" pull dev & goto :AFTER
if "%PICK%"=="3" "%VENV_PY%" "%CTL_PY%" snaplocal & goto :AFTER
if "%PICK%"=="4" "%VENV_PY%" "%CTL_PY%" list & goto :AFTER
if "%PICK%"=="5" goto :PULL_RELEASE
if "%PICK%"=="6" "%VENV_PY%" "%CTL_PY%" apply & goto :AFTER
if "%PICK%"=="7" "%VENV_PY%" "%CTL_PY%" push & goto :AFTER
if "%PICK%"=="8" "%VENV_PY%" "%CTL_PY%" orgpush & goto :AFTER
if "%PICK%"=="9" "%VENV_PY%" "%CTL_PY%" delete & goto :AFTER
goto :MENU
:PULL_RELEASE
echo.
choice /c PD /n /m "   环境（P=生产 / D=开发）: "
if "%ERRORLEVEL%"=="1" (set "MENV=prod") else set "MENV=dev"
echo   服务器 %MENV% 发布快照：
call :SRV_RB rollbacklist %MENV%
set "MSNAP="
set /p MSNAP=   输入要下载的发布快照名称（直接回车取消）: 
if "%MSNAP%"=="" goto :AFTER
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" pull %MENV% %MSNAP%
goto :AFTER
:AUTOSNAP
echo.
echo ================================================================
echo   自动快照设置（服务器 crontab，每日定时拍摄生产库快照——仅生产）
echo ================================================================
echo.
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" status
echo.
echo   [1] 开启 / 修改时间
echo   [2] 关闭自动快照
echo   [3] 设置保留快照份数（每环境，超出自动删最旧）
echo   [B] 返回主菜单
echo.
choice /c 123B /n /m "   Select: "
if "%ERRORLEVEL%"=="4" goto :AFTER
if "%ERRORLEVEL%"=="3" goto :AUTO_KEEP
if "%ERRORLEVEL%"=="2" goto :AUTO_OFF
if "%ERRORLEVEL%"=="1" goto :AUTO_ON
goto :AUTOSNAP

:AUTO_ON
echo.
set "TPROD="
set /p TPROD=   生产快照时间 HH:MM（直接回车 = 02:00）: 
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" on %TPROD%
goto :AFTER

:AUTO_KEEP
echo.
set "KEEP="
set /p KEEP=   每环境保留快照份数（1-100，直接回车 = 查看当前值）: 
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" keep %KEEP%
goto :AUTOSNAP
:AUTO_OFF
echo.
set "CONFIRM="
set /p CONFIRM=   确认关闭每日自动快照？输入 yes: 
if not "%CONFIRM%"=="yes" (
  echo   已取消。
  goto :AFTER
)
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" off
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

rem ---------- 远端只读命令（rollbacklist 走 srv-ctl 转发）----------
:SRV_RB
"%VENV_PY%" "%~dp0ops\srv-ctl.py" %*
goto :eof
