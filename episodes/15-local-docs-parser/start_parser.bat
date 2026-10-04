@echo off
rem Drag a folder with PDF acts onto this file, or double-click to process the folder "akty" next to it.
rem Result: reestr_aktov.xlsx and .csv inside that folder. Everything is processed on this computer.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: installing PyMuPDF and openpyxl. Internet is needed ONLY for this step, the parser itself never connects outside.
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3.9+ is not installed. Get it from python.org and run again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo Install failed. Check your internet connection and run again.
    pause
    exit /b 1
  )
)
set "FOLDER=%~1"
if "%FOLDER%"=="" set "FOLDER=%~dp0akty"
if not exist "%FOLDER%" (
  echo Folder not found: %FOLDER%
  echo Create a folder named akty next to this file, put PDF acts there and run again. Or try the folder samples.
  pause
  exit /b 1
)
echo Rules mode is fast. For hard documents the parser asks a LOCAL Ollama model (ollama pull qwen2.5:3b once, then it works offline). Add --no-llm below to disable the model.
".venv\Scripts\python.exe" parser_local.py "%FOLDER%" --out "%FOLDER%\reestr_aktov.xlsx"
pause
