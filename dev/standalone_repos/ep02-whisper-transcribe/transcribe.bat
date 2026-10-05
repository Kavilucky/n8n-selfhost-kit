@echo off
rem Drag an audio or video file onto this file. Text appears next to it.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: installing components, this takes a few minutes...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.9+ is not installed. Get it from python.org and run again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet faster-whisper
  if errorlevel 1 (
    echo Install failed. Check your internet connection.
    pause
    exit /b 1
  )
)
if "%~1"=="" (
  echo Drag an audio or video file onto transcribe.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" transcribe.py %*
pause
