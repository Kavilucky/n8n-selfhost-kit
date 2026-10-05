@echo off
rem Local AI document assistant: checks Ollama, starts the local server, opens the browser.
setlocal
cd /d "%~dp0"
set "MODEL=qwen2.5:3b"

where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed. Get it from https://ollama.com/download and run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: installing components, this takes a minute...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.9+ is not installed. Get it from python.org and run again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet pymupdf
  if errorlevel 1 (
    echo Install failed. Check your internet connection.
    pause
    exit /b 1
  )
)

curl -s -o nul http://127.0.0.1:11434/api/tags
if errorlevel 1 (
  echo Ollama is not running. Starting it...
  start "" /min ollama serve
  for /l %%i in (1,1,20) do (
    curl -s -o nul http://127.0.0.1:11434/api/tags && goto ollama_ok
    timeout /t 1 /nobreak >nul
  )
  echo Could not start Ollama. Start it manually and run this file again.
  pause
  exit /b 1
)
:ollama_ok

ollama list | findstr /i /c:"%MODEL%" >nul
if errorlevel 1 (
  echo Model %MODEL% not found. Downloading once, about 2 GB...
  ollama pull %MODEL%
  if errorlevel 1 (
    echo Model download failed. Check your internet connection.
    pause
    exit /b 1
  )
)

echo Starting the assistant at http://localhost:8000
start "" http://localhost:8000
".venv\Scripts\python.exe" app.py
pause
