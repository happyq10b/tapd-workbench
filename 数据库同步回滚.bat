@echo off
setlocal enabledelayedexpansion
title TAPD Workbench - DB Sync && Rollback

rem ================================================================
rem  TAPD Workbench - 数据库快照 同步与回滚开关（2026-11-07）
rem
rem  快照存储: data\db-snapshots\<YYYYMMDD-HHMMSS>\app.db + meta.txt
rem
rem  [1] 拉取  : 服务器生产库 → 本地快照库（服务器先拍一致性快照，不停服）
rem  [2] 列表  : 查看本地已有快照
rem  [3] 应用  : 选定快照 → 本地开发环境(8100)数据源（当前本地库自动留底）
rem  [4] 回滚  : 选定快照 → 服务器生产库（高危！双确认，服务器自动留底）
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
echo   --- 服务器 → 本地 ---
echo   [1] Pull        拉取生产库快照到本地（按时间戳存档）
echo   [2] List        列出本地快照
echo.
echo   --- 本地使用 ---
echo   [3] Apply       应用快照为本地开发环境数据源（8100）
echo.
echo   --- 本地 → 服务器（高危）---
echo   [4] Rollback    本地快照回滚到服务器生产库
echo.
echo   [Q] Quit
echo ================================================================
echo.
choice /c 1234Q /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

if "%PICK%"=="5" goto :QUIT
if "%PICK%"=="1" "%VENV_PY%" "%CTL_PY%" pull & goto :AFTER
if "%PICK%"=="2" "%VENV_PY%" "%CTL_PY%" list & goto :AFTER
if "%PICK%"=="3" "%VENV_PY%" "%CTL_PY%" apply & goto :AFTER
if "%PICK%"=="4" "%VENV_PY%" "%CTL_PY%" push & goto :AFTER
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
