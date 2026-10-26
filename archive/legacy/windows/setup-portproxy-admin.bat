@echo off
title Setup persistent localhost:8000 -> WSL bridge

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [ERROR] Administrator rights required.
  echo   Right-click this file and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)

set "WIP="
for /f "usebackq tokens=1" %%a in (`wsl.exe -d Ubuntu-24.04 hostname -I`) do set "WIP=%%a"
if "%WIP%"=="" (
  echo   [ERROR] Could not read the WSL IP. Is Ubuntu-24.04 running?
  pause
  exit /b 1
)

echo   WSL IP: %WIP%
echo   Creating kernel-level port proxy 127.0.0.1:8000 -^> %WIP%:8000 ...
netsh interface portproxy delete v4tov4 listenaddress=127.0.0.1 listenport=8000 >nul 2>&1
netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=8000 connectaddress=%WIP% connectport=8000
echo.
netsh interface portproxy show all
echo.
echo   Done. http://localhost:8000 now stays up even when idle.
echo   NOTE: re-run this file after WSL restarts (the WSL IP may change).
echo.
pause
