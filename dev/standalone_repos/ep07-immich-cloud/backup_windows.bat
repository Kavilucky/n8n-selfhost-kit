@echo off
setlocal
rem Copies new and changed files from the Immich library to a backup folder. Deletes nothing.
rem Usage: backup_windows.bat [SOURCE_FOLDER BACKUP_FOLDER]  (without arguments the script asks for the paths)
echo Immich library backup: copies new and changed files, never deletes anything.
echo.
set "SRC=%~1"
set "DST=%~2"
if "%SRC%"=="" set /p SRC=Path to the Immich library folder (UPLOAD_LOCATION), for example D:\immich-app\library:
if "%DST%"=="" set /p DST=Path to the backup folder on the external drive, for example E:\backup\immich-library:
if not exist "%SRC%" goto nosrc
if not exist "%DST%" mkdir "%DST%"
robocopy "%SRC%" "%DST%" /E /R:2 /W:5 /NP
rem robocopy exit codes 0-7 mean success, 8 and above mean errors
if %ERRORLEVEL% GEQ 8 goto failed
echo.
echo Done. Check that the copy opens before you delete anything from your phone or from cloud storage.
echo Do not forget to copy the database folder (DB_DATA_LOCATION) the same way.
if "%~1"=="" pause
exit /b 0
:nosrc
echo Source folder not found: %SRC%
if "%~1"=="" pause
exit /b 1
:failed
echo Backup finished with errors. Check the messages above.
if "%~1"=="" pause
exit /b 1
