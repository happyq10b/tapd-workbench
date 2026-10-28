@echo off
setlocal enabledelayedexpansion
title TAPD Workbench - Sync Switch

rem ================================================================
rem  TAPD Workbench - One-Click Sync Switch
rem
rem  Double-click this file to run: local verification -> sync.
rem
rem  Stage 1  Local verification   ops/verify.py    7 checks, all must pass
rem  Stage 2  Manual sync          ops/sync.sh      gate check -> push -> restart
rem
rem  If verification fails, the script aborts and NOTHING is pushed.
rem ================================================================

cd /d "%~dp0"

set "OPS=%~dp0ops"
set "VENV_PY=%~dp0ops\.localvenv\Scripts\python.exe"
set "SYNC_SH=%~dp0ops\sync.sh"
set "VERIFY_PY=%~dp0ops\verify.py"
set "LOGDIR=%TEMP%\tapd-sync"

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
if not defined BASH (
  echo.
  echo   [ERROR] Git Bash not found.
  echo.
  echo   Install Git for Windows, or make sure bash.exe exists at:
  echo     C:\Program Files\Git\bin\bash.exe
  echo     D:\Git\bin\bash.exe
  echo.
  pause
  exit /b 1
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

echo.
echo ================================================================
echo   TAPD Workbench . Sync Switch
echo ================================================================
echo   Workspace: %~dp0
echo   Bash     : %BASH%
echo ================================================================
echo.
echo   Select target:
echo.
echo     [1] Dev  (--dev)    推送到服务器开发环境
echo     [2] Prod (--prod)   推送到生产环境
echo     [3] Verify only     仅本地检查，不推送
echo     [4] Cancel          取消
echo.
choice /c 1234 /n /m "   Enter 1-4: "

rem NOTE: 'if errorlevel N' means "errorlevel >= N", so they must be tested from
rem high to low AND each must be mutually exclusive. Using separate 'if' lines
rem for the two targets lets a later line overwrite an earlier match, so we
rem use goto labels instead.
if errorlevel 4 goto :CANCEL
if errorlevel 3 goto :ONLY_VERIFY
if errorlevel 2 goto :PICK_PROD
if errorlevel 1 goto :PICK_DEV
goto :CANCEL

:PICK_PROD
set "TARGET=--prod"
goto :AFTER_PICK

:PICK_DEV
set "TARGET=--dev"

:AFTER_PICK

rem ---------- Stage 1: local verification ----------
echo.
echo ================================================================
echo   Stage 1 . Local verification
echo ================================================================
echo.
"%VENV_PY%" "%VERIFY_PY%"
set "VRC=%ERRORLEVEL%"
echo.
if not "%VRC%"=="0" (
  echo ================================================================
  echo   VERIFICATION FAILED - aborted
  echo ================================================================
  echo.
  echo   Fix the failures above, then run this switch again.
  echo   Nothing was pushed to the server.
  echo.
  pause
  exit /b 1
)

if "%TARGET%"=="" goto :VERIFY_OK

rem ---------- Stage 2: manual sync ----------
echo.
echo ================================================================
echo   Stage 2 . Manual sync  (%TARGET%)
echo ================================================================
echo.

if defined ICONV (
  "%BASH%" "%SYNC_SH%" %TARGET% > "%LOGDIR%\sync.out" 2>&1
  call :Drain "%LOGDIR%\sync.out"
) else (
  "%BASH%" "%SYNC_SH%" %TARGET%
)
set "SYNC_RC=%ERRORLEVEL%"

echo.
if not "%SYNC_RC%"=="0" (
  echo ================================================================
  echo   SYNC FAILED  (exit code %SYNC_RC%)
  echo ================================================================
  echo.
  pause
  exit /b %SYNC_RC%
)

echo ================================================================
echo   SYNC COMPLETE
echo ================================================================
echo.
echo   Public URL : https://123.207.252.195
echo   Server log : ssh -F ops\secrets\sshcfg tapd "tail -f /var/log/tapd-dev.log"
echo.
pause
exit /b 0

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

:ONLY_VERIFY
echo.
echo ================================================================
echo   Verify only
echo ================================================================
echo.
"%VENV_PY%" "%VERIFY_PY%"
set "VRC=%ERRORLEVEL%"
echo.
if not "%VRC%"=="0" (
  echo   VERIFICATION FAILED - fix the issues and retry
  echo.
  pause
  exit /b %VRC%
)
echo   Verification passed. Credential issued.
echo.
echo   Run this switch again and pick 1 or 2 to sync.
echo.
pause
exit /b 0

:VERIFY_OK
echo   Verification passed. Credential issued.
echo.
pause
exit /b 0

:CANCEL
echo.
echo   Cancelled.
echo.
pause
exit /b 0
