#!/usr/bin/env bash
# Copies new and changed files from the Immich library to a backup folder. Deletes nothing.
# Usage: backup_linux.sh [SOURCE_FOLDER BACKUP_FOLDER]  (without arguments the script asks for the paths)
set -u
echo "Immich library backup: copies new and changed files, never deletes anything."
SRC="${1:-}"; DST="${2:-}"
[ -n "$SRC" ] || read -r -p "Path to the Immich library folder (UPLOAD_LOCATION), e.g. /srv/immich-app/library: " SRC
[ -n "$DST" ] || read -r -p "Path to the backup folder on the external drive, e.g. /mnt/backup/immich-library: " DST
if [ ! -d "$SRC" ]; then echo "Source folder not found: $SRC"; exit 1; fi
mkdir -p "$DST"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --info=progress2 "$SRC"/ "$DST"/ || { echo "Backup finished with errors."; exit 1; }
else
  cp -a -u "$SRC"/. "$DST"/ || { echo "Backup finished with errors."; exit 1; }
fi
echo
echo "Done. Check that the copy opens before you delete anything from your phone or from cloud storage."
echo "Do not forget to copy the database folder (DB_DATA_LOCATION) the same way."
