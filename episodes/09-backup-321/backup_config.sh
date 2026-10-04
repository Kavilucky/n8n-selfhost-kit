#!/usr/bin/env bash
# Settings for backup_linux.sh. Edit the values between the quotes.

# Which tool to use: kopia (main, has a window and a command line) or restic (command line only).
TOOL="kopia"

# Folder you want to protect (photos, documents). Example: /home/name/Pictures
SOURCE_DIR="/home/name/Pictures"

# Copy 1 and medium 2: a folder on your EXTERNAL DISK. The repository is created here on first run. Example: /mnt/backup/repo
REPO1="/mnt/backup/repo"

# Copy 2, outside your home (optional but needed for 3-2-1). Leave empty to skip.
# Kopia: a folder on another disk or network drive (for cloud use the KopiaUI window, see the guide).
# Restic: any Restic repository address, for example a folder or sftp:user@host:/path (cloud addresses: see the guide).
REPO2=""

# A text file with the repository password on the first line. Keep a copy of the password in a safe place:
# without it the data cannot be restored. Do not keep this file on the same disk as the backup.
PASSWORD_FILE="$HOME/.backup-secret/repo_password.txt"

# Folder with the kopia or restic binary if it is not in PATH (leave empty otherwise).
TOOL_DIR=""
