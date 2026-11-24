@echo off
setlocal
title FISP - Force Offline Admin (T-212)

rem ================================================================
rem  Force-offline admin for all environments (T-212, 2026-11-24)
rem  - local : local sqlite (src/app.db)   + local service 8100
rem  - prod  : server /opt/tapd-workbench  (tapd-web,  8000)
rem  - dev   : server /opt/tapd-dev        (tapd-dev,  8001)
rem  Mechanism: users.active_seq +1 -> all tokens invalid immediately;
rem    pages bounce to login on next request; zombie WS closed <=25s
rem    (server-side heartbeat token check).
rem  CLI: kick_admin.bat local|prod|dev|all [--yes]
rem ================================================================

cd /d "%~dp0"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "CTL_PY=%~dp0ops\kick_admin.py"
set "PYTHONIOENCODING=gbk"

if not exist "%VENV_PY%" (
  echo   [ERROR] Local venv not found: %VENV_PY%
  pause
  exit /b 1
)
if not exist "%CTL_PY%" (
  echo   [ERROR] kick_admin.py not found: %CTL_PY%
  pause
  exit /b 1
)

rem ---- CLI passthrough ----
if not "%~1"=="" goto CLI

:MENU
cls
echo ================================================================
echo   FISP - Force Offline Admin (T-212)
echo   Mechanism: active_seq +1 = all admin tokens invalid at once;
echo   pages bounce to login; zombie WS closed by server in 25s.
echo ================================================================
echo   [1] Local      (src/app.db + service 8100)
echo   [2] Prod       (123.207.252.195 /opt/tapd-workbench)
echo   [3] Dev        (123.207.252.195 /opt/tapd-dev)
echo   [4] ALL        (local + prod + dev)
echo   [Q] Quit
echo ================================================================
set /p choice=Select: 
if /i "%choice%"=="1" goto DO_LOCAL
if /i "%choice%"=="2" goto DO_PROD
if /i "%choice%"=="3" goto DO_DEV
if /i "%choice%"=="4" goto DO_ALL
if /i "%choice%"=="q" exit /b 0
goto MENU

:DO_LOCAL
echo.
"%VENV_PY%" "%CTL_PY%" local
echo.
pause
goto MENU

:DO_PROD
echo.
echo   [CONFIRM] Force-offline admin on PROD server? (users may be kicked)
set /p yn=Type Y to continue: 
if /i not "%yn%"=="Y" goto MENU
"%VENV_PY%" "%CTL_PY%" prod
echo.
pause
goto MENU

:DO_DEV
echo.
echo   [CONFIRM] Force-offline admin on DEV server?
set /p yn=Type Y to continue: 
if /i not "%yn%"=="Y" goto MENU
"%VENV_PY%" "%CTL_PY%" dev
echo.
pause
goto MENU

:DO_ALL
echo.
echo   [CONFIRM] Force-offline admin on LOCAL + PROD + DEV?
set /p yn=Type Y to continue: 
if /i not "%yn%"=="Y" goto MENU
"%VENV_PY%" "%CTL_PY%" local
"%VENV_PY%" "%CTL_PY%" prod
"%VENV_PY%" "%CTL_PY%" dev
echo.
echo   All done. admin tokens invalid on all three environments.
pause
goto MENU

:CLI
"%VENV_PY%" "%CTL_PY%" %*
exit /b %errorlevel%
