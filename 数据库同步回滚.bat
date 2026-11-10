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
echo   [1] Pull        拉取生产库快照到本地
echo   [2] Snap-Local  拉取本地库快照（留存本地当前数据）
echo   [3] List        列出本地快照
echo.
echo   --- 快照使用 ---
echo   [4] Apply       应用快照为本地开发环境数据源
echo   [5] Rollback    本地快照回滚到服务器库（选：生产 / 开发）
echo   [6] Org-Rollback 按架构部门回滚（核算/商务/总账/管理/资金/财务中心）
echo.
echo   --- 快照删除 ---
echo   [7] Delete      删除本地快照（只删本地，不影响服务器）
echo.
echo   [Q] Quit
echo ================================================================
echo.
choice /c 1234567Q /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

if "%PICK%"=="8" goto :QUIT
if "%PICK%"=="1" "%VENV_PY%" "%CTL_PY%" pull & goto :AFTER
if "%PICK%"=="2" "%VENV_PY%" "%CTL_PY%" snaplocal & goto :AFTER
if "%PICK%"=="3" "%VENV_PY%" "%CTL_PY%" list & goto :AFTER
if "%PICK%"=="4" "%VENV_PY%" "%CTL_PY%" apply & goto :AFTER
if "%PICK%"=="5" "%VENV_PY%" "%CTL_PY%" push & goto :AFTER
if "%PICK%"=="6" "%VENV_PY%" "%CTL_PY%" orgpush & goto :AFTER
if "%PICK%"=="7" "%VENV_PY%" "%CTL_PY%" delete & goto :AFTER
goto :MENU

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
