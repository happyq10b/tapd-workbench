@echo off
title Open TAPD Board Workbench

rem Make sure WSL distro and tapd-web service are up (no restart unless dead,
rem because restarting the service breaks the Windows-side localhost relay).
wsl.exe -d Ubuntu-24.04 -u root -- bash -lc "systemctl is-active --quiet tapd-web || systemctl start tapd-web" >nul 2>&1

rem Wait until uvicorn listens inside WSL (max ~20s)
set /a _try=0
:wsvc
wsl.exe -d Ubuntu-24.04 -u root -- bash -lc "ss -ltn | grep -q ':8000 '" >nul 2>&1
if not errorlevel 1 goto :open
set /a _try+=1
if %_try% geq 20 goto :fail
ping -n 2 127.0.0.1 >nul
goto :wsvc

:open
set "WIP="
for /f "usebackq tokens=1" %%a in (`wsl.exe -d Ubuntu-24.04 hostname -I`) do set "WIP=%%a"
if "%WIP%"=="" goto :fail

echo.
echo   Workbench : http://%WIP%:8000/
echo   Login page: http://%WIP%:8000/login
echo.
echo   NOTE: use the IP above, NOT localhost. On Windows 10 the WSL
echo   localhost relay is a user-mode process that exits when idle,
echo   which causes "network error" right after you type your password.
echo.

start "" "http://%WIP%:8000/"
ping -n 5 127.0.0.1 >nul
exit /b 0

:fail
echo [FAIL] tapd-web did not become ready within 20 seconds.
echo Run: wsl -d Ubuntu-24.04 -u root -- systemctl status tapd-web
pause
exit /b 1
