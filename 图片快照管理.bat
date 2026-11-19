@echo off
setlocal enabledelayedexpansion
title FISP - Img Snapshot ^&^& Rollback

rem ================================================================
rem  FISP 图片资源快照与回滚（T-193，2026-11-13）
rem  快照范围：精灵设置区（pet_zones/pet_images/login_pet）+ 用户头像 + 用户照片
rem  本地快照库: data\img-snapshots\<env>\<YYYYMMDD-HHMMSS>\
rem  服务器存档: /var/backups/tapd-workbench/img-snapshots/<env>/<ts>/
rem
rem  CLI: 图片快照管理.bat snap local|prod|dev
rem       图片快照管理.bat pull  prod|dev [ts]
rem       图片快照管理.bat apply local|prod|dev <ts|快照目录> [--parts pet,avatar,photo] [--yes]
rem       图片快照管理.bat delete local|prod|dev [ts] [--yes]
rem       图片快照管理.bat list | auto | auto-config
rem  交互模式：每个动作执行完回到主菜单；仅 [Q] 或 CLI 模式退出。
rem ================================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "CTL_PY=%~dp0ops\img_snapshot.py"
set "PYTHONIOENCODING=gbk"

if not exist "%VENV_PY%" (
  echo   [ERROR] Local venv not found: %VENV_PY%
  pause
  exit /b 1
)
if not exist "%CTL_PY%" (
  echo   [ERROR] img_snapshot.py not found: %CTL_PY%
  pause
  exit /b 1
)

rem ---- CLI 直通模式：带参数时直接转交 python（执行完即退出） ----
if not "%~1"=="" goto CLI

:MENU
cls
echo ================================================================
echo   FISP 图片资源快照与回滚    工作区: %~dp0
echo ================================================================
echo   快照范围: 精灵设置区 + 用户头像 + 用户照片（app.db 内 data URL 资源）
echo   本地快照库: data\img-snapshots\   服务器存档: /var/backups/.../img-snapshots/
echo.
echo   --- 快照储存 ---
echo   [P] 生产库图片快照    服务器存档一份 + 拉回本地
echo   [D] 开发库图片快照    服务器存档一份 + 拉回本地
echo   [L] 本地库图片快照    当前本地数据存档
echo.
echo   --- 快照应用 ---
echo   [S] 拉取服务器已有快照 → 本地（列出服务器存档，选一份拉回）
echo   [A] 本地快照 → 应用到本地库（应用前自动留底）
echo   [1] 本地快照 → 应用到生产服务器（高危，需输入 YES 双确认）
echo   [2] 本地快照 → 应用到开发服务器（高危，需输入 YES 双确认）
echo.
echo   --- 快照删除（删除前需确认） ---
echo   [R]  删除本地快照      选自本地快照库
echo   [RP] 删除生产服务器快照  选自服务器存档
echo   [RD] 删除开发服务器快照  选自服务器存档
echo.
echo   --- 管理 ---
echo   [I] 查看快照清单（本地各环境 + 计数）
echo   [X] 生产自动快照设置  开关自动注册 / 时间 / 间隔(天) / 份数 / 手动注册
echo.
echo   [Q] 退出
echo ================================================================
set /p CHOICE=请选择:
if /i "%CHOICE%"=="P" %VENV_PY% "%CTL_PY%" export --env prod & goto BACK
if /i "%CHOICE%"=="D" %VENV_PY% "%CTL_PY%" export --env dev & goto BACK
if /i "%CHOICE%"=="L" %VENV_PY% "%CTL_PY%" export --env local & goto BACK
if /i "%CHOICE%"=="S" goto PULL
if /i "%CHOICE%"=="A" %VENV_PY% "%CTL_PY%" apply local & goto BACK
if "%CHOICE%"=="1" %VENV_PY% "%CTL_PY%" apply prod & goto BACK
if "%CHOICE%"=="2" %VENV_PY% "%CTL_PY%" apply dev & goto BACK
if /i "%CHOICE%"=="R" %VENV_PY% "%CTL_PY%" delete local & goto BACK
if /i "%CHOICE%"=="RP" %VENV_PY% "%CTL_PY%" delete prod & goto BACK
if /i "%CHOICE%"=="RD" %VENV_PY% "%CTL_PY%" delete dev & goto BACK
if /i "%CHOICE%"=="I" %VENV_PY% "%CTL_PY%" list & goto BACK
if /i "%CHOICE%"=="X" %VENV_PY% "%CTL_PY%" auto-config & goto BACK
if /i "%CHOICE%"=="Q" exit /b 0
goto MENU

:PULL
echo 选择来源环境: [P] 生产  [D] 开发
set /p PE=请选择:
if /i "%PE%"=="P" %VENV_PY% "%CTL_PY%" pull prod & goto BACK
if /i "%PE%"=="D" %VENV_PY% "%CTL_PY%" pull dev & goto BACK
goto MENU

:BACK
echo.
echo   —— 按回车返回主菜单 ——
pause >nul
goto MENU

:CLI
rem CLI 直通：snap / pull / apply / delete / list / prune / auto / auto-config
if /i "%~1"=="snap" %VENV_PY% "%CTL_PY%" export --env %~2 & goto EOF
%VENV_PY% "%CTL_PY%" %*
goto EOF

:EOF
exit /b 0
