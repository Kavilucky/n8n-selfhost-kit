@echo off
setlocal enableextensions
rem Read paths from backup_config.cmd as UTF-8 (needed for Cyrillic folder names). Save the config as UTF-8 without BOM.
chcp 65001 >nul
rem Backup by the 3-2-1 rule with Kopia or Restic (Windows). Settings are in backup_config.cmd next to this file.
rem Usage: backup_windows.bat [backup|verify]   (no argument means backup)
rem   backup  makes a snapshot of SOURCE_DIR into REPO1 (and into REPO2 if it is set). Nothing is deleted.
rem   verify  checks the repositories (a random 5 percent of data is read back), run it once a month.
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=backup"
set "HERE=%~dp0"
if not exist "%HERE%backup_config.cmd" goto noconfig
call "%HERE%backup_config.cmd"
if defined TOOL_DIR set "PATH=%TOOL_DIR%;%PATH%"
if not defined TOOL goto badtool
where %TOOL% >nul 2>nul
if errorlevel 1 goto notool
if not defined SOURCE_DIR goto nosource
if not exist "%SOURCE_DIR%" goto nosource
if not defined REPO1 goto norepo
if not defined PASSWORD_FILE goto nopass
if not exist "%PASSWORD_FILE%" goto nopass
if /i "%TOOL%"=="kopia" goto kopia
if /i "%TOOL%"=="restic" goto restic
goto badtool

:kopia
set /p KOPIA_PASSWORD=<"%PASSWORD_FILE%"
if not defined KOPIA_PASSWORD goto nopass
set "REPO=%REPO1%"
set "CFG=%HERE%kopia_repo1.config"
call :kopia_one
if errorlevel 1 goto failed
if not defined REPO2 goto done
set "REPO=%REPO2%"
set "CFG=%HERE%kopia_repo2.config"
call :kopia_one
if errorlevel 1 goto failed
goto done

:kopia_one
if exist "%CFG%" goto kopia_ready
if exist "%REPO%\kopia.repository.f" goto kopia_connect
if not exist "%REPO%" mkdir "%REPO%"
kopia --config-file="%CFG%" repository create filesystem --path="%REPO%"
if errorlevel 1 exit /b 1
if exist "%HERE%exclude.txt" for /f "usebackq delims=" %%L in ("%HERE%exclude.txt") do kopia --config-file="%CFG%" policy set --global --add-ignore="%%L" >nul
goto kopia_ready
:kopia_connect
kopia --config-file="%CFG%" repository connect filesystem --path="%REPO%"
if errorlevel 1 exit /b 1
:kopia_ready
if /i "%ACTION%"=="verify" goto kopia_verify
kopia --config-file="%CFG%" snapshot create "%SOURCE_DIR%"
exit /b %ERRORLEVEL%
:kopia_verify
kopia --config-file="%CFG%" snapshot verify --verify-files-percent=5
exit /b %ERRORLEVEL%

:restic
set "RESTIC_PASSWORD_FILE=%PASSWORD_FILE%"
set "REPO=%REPO1%"
call :restic_one
if errorlevel 1 goto failed
if not defined REPO2 goto done
set "REPO=%REPO2%"
call :restic_one
if errorlevel 1 goto failed
goto done

:restic_one
restic --repo "%REPO%" cat config >nul 2>nul
if errorlevel 1 restic --repo "%REPO%" init
if errorlevel 1 exit /b 1
if /i "%ACTION%"=="verify" goto restic_verify
if exist "%HERE%exclude.txt" goto restic_backup_ex
restic --repo "%REPO%" backup "%SOURCE_DIR%"
exit /b %ERRORLEVEL%
:restic_backup_ex
restic --repo "%REPO%" backup "%SOURCE_DIR%" --exclude-file="%HERE%exclude.txt"
exit /b %ERRORLEVEL%
:restic_verify
restic --repo "%REPO%" check --read-data-subset=5%%
exit /b %ERRORLEVEL%

:done
echo.
echo OK: %ACTION% finished (%TOOL%).
if /i "%ACTION%"=="backup" echo Run "backup_windows.bat verify" once a month and try to restore a file by hand.
exit /b 0

:failed
echo.
echo ERROR: %ACTION% failed. Read the messages above. Nothing was deleted.
exit /b 1
:noconfig
echo ERROR: backup_config.cmd not found next to this script.
exit /b 2
:badtool
echo ERROR: set TOOL to kopia or restic in backup_config.cmd.
exit /b 2
:notool
echo ERROR: %TOOL% not found. Install it or set TOOL_DIR in backup_config.cmd.
exit /b 2
:nosource
echo ERROR: SOURCE_DIR is not set or does not exist (backup_config.cmd).
exit /b 2
:norepo
echo ERROR: REPO1 is not set (backup_config.cmd): this is the folder on your external disk.
exit /b 2
:nopass
echo ERROR: PASSWORD_FILE is not set, does not exist or is empty (backup_config.cmd). Create a text file with the repository password on the first line.
exit /b 2
