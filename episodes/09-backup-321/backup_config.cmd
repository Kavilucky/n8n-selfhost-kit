@echo off
rem Settings for backup_windows.bat. Edit the values between the quotes. Do not add extra quotes around paths.

rem Which tool to use: kopia (main, has a window and a command line) or restic (command line only).
set "TOOL=kopia"

rem Folder you want to protect (photos, documents). Example: C:\Users\Name\Pictures
set "SOURCE_DIR=C:\Users\Name\Pictures"

rem Copy 1 and medium 2: a folder on your EXTERNAL DISK. The repository is created here on first run. Example: E:\backup\repo
set "REPO1=E:\backup\repo"

rem Copy 2, outside your home (optional but needed for 3-2-1). Leave empty to skip.
rem Kopia: a folder on another disk or network drive (for cloud use the KopiaUI window, see the guide).
rem Restic: any Restic repository address, for example a folder or sftp:user@host:/path (cloud addresses: see the guide).
set "REPO2="

rem A text file with the repository password on the first line. Keep a copy of the password in a safe place:
rem without it the data cannot be restored. Do not keep this file on the same disk as the backup.
set "PASSWORD_FILE=C:\backup-secret\repo_password.txt"

rem Folder with kopia.exe or restic.exe if they are not in PATH (leave empty otherwise).
set "TOOL_DIR="
