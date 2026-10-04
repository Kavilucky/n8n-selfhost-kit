@echo off
rem Starts check_proxy_ip.py by double click. No packages needed (Python standard library only).
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.9+ is not installed. Install it from python.org and run this file again.
  pause
  exit /b 1
)
%PY% check_proxy_ip.py %*
echo.
echo Done. Press any key to close.
pause >nul
