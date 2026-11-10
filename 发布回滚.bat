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
echo.
echo   --- 快照创建 ---
echo   [3] 立即拍生产快照（发布/变更前手动留底）
echo   [4] 立即拍开发快照
echo.
echo   --- 回滚（危险操作，恢复代码+数据库，约20秒停机）---
echo   [5] 回滚生产  → 选择快照
echo   [6] 回滚开发  → 选择快照
echo.
echo   --- 删除（不可恢复）---
echo   [7] 删除生产快照 → 选择快照（需输入 yes 确认）
echo   [8] 删除开发快照 → 选择快照（需输入 yes 确认）
echo.
echo   --- 本地镜像（data\release-snapshots\）---
echo   [9] Pull-Local    服务器快照下载到本地（选环境与快照）
echo   [0] Restore-Local 本地镜像回滚服务器（高危！双确认，约20秒停机）
echo   [L] Del-Local     删除本地镜像快照（只删本地，需输入 yes 确认）
echo   [S] List-Local    列出本地镜像快照（名称 / 大小 / 时间 / 完整性）
echo.
echo   --- 自动快照（服务器每日定时）---
echo   [A] 自动快照设置   开关与拍摄时间（状态见子菜单）
echo.
echo   （本地库快照见「数据库同步回滚.bat」）
echo.
echo   [Q] Quit
echo ================================================================
echo.
choice /c 1234567890LASQ /n /m "   Select: "
set "PICK=%ERRORLEVEL%"

if "%PICK%"=="14" goto :QUIT
if "%PICK%"=="13" goto :LIST_LOCAL
if "%PICK%"=="12" goto :AUTOSNAP
if "%PICK%"=="11" goto :DELL_LOCAL
if "%PICK%"=="10" goto :RESTORE_LOCAL
if "%PICK%"=="9" goto :PULL_LOCAL
if "%PICK%"=="7" goto :DEL_PROD
if "%PICK%"=="8" goto :DEL_DEV
if "%PICK%"=="1" call :SRV rollbacklist prod & goto :AFTER
if "%PICK%"=="2" call :SRV rollbacklist dev & goto :AFTER
if "%PICK%"=="3" call :SRV snap prod & goto :AFTER
if "%PICK%"=="4" call :SRV snap dev & goto :AFTER
if "%PICK%"=="5" goto :RB_PROD
if "%PICK%"=="6" goto :RB_DEV
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

:DEL_PROD
set "ENV=prod"
set "ENVCN=生产"
goto :DEL_DO

:DEL_DEV
set "ENV=dev"
set "ENVCN=开发"
goto :DEL_DO

:DEL_DO
echo.
echo   当前%ENVCN%快照（新→旧）：
call :SRV rollbacklist %ENV%
echo.
set "SNAP="
set /p SNAP=   输入要删除的快照名称（直接回车取消）: 
if "%SNAP%"=="" goto :AFTER
echo.
echo   !! 将从服务器永久删除 %ENVCN% 快照：%SNAP%（不可恢复）
set "CONFIRM="
set /p CONFIRM=   确认请输入 yes: 
if not "%CONFIRM%"=="yes" (
  echo   已取消。
  goto :AFTER
)
echo.
call :SRV delsnap %ENV% %SNAP% yes
goto :AFTER

:PULL_LOCAL
echo.
choice /c PD /n /m "   环境（P=生产 / D=开发）: "
if "%ERRORLEVEL%"=="1" (set "MENV=prod") else set "MENV=dev"
echo   服务器 %MENV% 快照：
call :SRV rollbacklist %MENV%
set "MSNAP="
set /p MSNAP=   输入要下载的快照名称（直接回车取消）: 
if "%MSNAP%"=="" goto :AFTER
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" pull %MENV% %MSNAP%
goto :AFTER

:RESTORE_LOCAL
echo.
echo   本地镜像清单：
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" list
echo.
choice /c PD /n /m "   环境（P=生产 / D=开发）: "
if "%ERRORLEVEL%"=="1" (set "MENV=prod") else set "MENV=dev"
set "MSNAP="
set /p MSNAP=   输入要用于回滚的本地镜像名称（直接回车取消）: 
if "%MSNAP%"=="" goto :AFTER
echo.
echo   !! 高危：将用本地镜像回滚 %MENV% 服务器（恢复代码+数据库，约20秒停机）
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" restore %MENV% %MSNAP%
goto :AFTER

:DELL_LOCAL
echo.
echo   本地镜像清单：
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" list
echo.
choice /c PD /n /m "   环境（P=生产 / D=开发）: "
if "%ERRORLEVEL%"=="1" (set "MENV=prod") else set "MENV=dev"
set "MSNAP="
set /p MSNAP=   输入要删除的本地镜像名称（直接回车取消）: 
if "%MSNAP%"=="" goto :AFTER
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" delete %MENV% %MSNAP%
goto :AFTER
:LIST_LOCAL
echo.
echo   本地镜像快照（data\release-snapshots\）：
"%VENV_PY%" "%~dp0ops\release-snap-ctl.py" list
goto :AFTER

:AUTOSNAP
echo.
echo ================================================================
echo   自动快照设置（服务器 crontab，每日定时拍摄 prod/dev 快照）
echo ================================================================
echo.
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" status
echo.
echo   [1] 开启 / 修改时间
echo   [2] 关闭自动快照
echo   [B] 返回主菜单
echo.
choice /c 12B /n /m "   Select: "
if "%ERRORLEVEL%"=="3" goto :AFTER
if "%ERRORLEVEL%"=="2" goto :AUTO_OFF
if "%ERRORLEVEL%"=="1" goto :AUTO_ON
goto :AUTOSNAP

:AUTO_ON
echo.
set "TPROD="
set /p TPROD=   生产快照时间 HH:MM（直接回车 = 02:00）: 
set "TDEV="
set /p TDEV=   开发快照时间 HH:MM（直接回车 = 生产时间+10分钟）: 
"%VENV_PY%" "%~dp0ops\auto-snap-ctl.py" on %TPROD% %TDEV%
goto :AFTER

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
