@echo off
rem Drag a folder with photos onto this file (or double-click and type the path).
rem Finds visually similar photos and moves extra copies to a quarantine folder. Nothing is deleted.
rem Undo the last run: find_duplicates.bat "C:\path\to\folder" --undo
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: installing components, this takes a minute...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.9+ is not installed. Get it from python.org and run again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet pillow numpy
  if errorlevel 1 (
    echo Install failed. Check your internet connection and run again.
    rmdir /s /q .venv
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet pillow-heif
  if errorlevel 1 echo Optional HEIC support was not installed. Photos from iPhone in HEIC format will be skipped.
)

set "TARGET=%~1"
if "%TARGET%"=="" (
  echo Drag a folder with photos onto find_duplicates.bat, or type the folder path below.
  set /p "TARGET=Folder path: "
)
set "TARGET=%TARGET:"=%"
if "%TARGET:~-1%"=="\" set "TARGET=%TARGET:~0,-1%"
if "%TARGET%"=="" (
  echo No folder given.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" find_duplicates.py "%TARGET%" %2 %3 %4
pause
