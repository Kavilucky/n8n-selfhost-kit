#!/usr/bin/env bash
# Backup by the 3-2-1 rule with Kopia or Restic (Linux, macOS, Git Bash). Settings are in backup_config.sh next to this file.
# Usage: ./backup_linux.sh [backup|verify]   (no argument means backup)
#   backup  makes a snapshot of SOURCE_DIR into REPO1 (and into REPO2 if it is set). Nothing is deleted.
#   verify  checks the repositories (a random 5 percent of data is read back), run it once a month.
set -u
ACTION="${1:-backup}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/backup_config.sh" ] || { echo "ERROR: backup_config.sh not found next to this script."; exit 2; }
# shellcheck disable=SC1091
. "$HERE/backup_config.sh"
[ -n "${TOOL_DIR:-}" ] && PATH="$TOOL_DIR:$PATH"
case "${TOOL:-}" in kopia|restic) ;; *) echo "ERROR: set TOOL to kopia or restic in backup_config.sh."; exit 2;; esac
command -v "$TOOL" >/dev/null 2>&1 || { echo "ERROR: $TOOL not found. Install it or set TOOL_DIR in backup_config.sh."; exit 2; }
[ -n "${SOURCE_DIR:-}" ] && [ -d "$SOURCE_DIR" ] || { echo "ERROR: SOURCE_DIR is not set or does not exist (backup_config.sh)."; exit 2; }
[ -n "${REPO1:-}" ] || { echo "ERROR: REPO1 is not set (backup_config.sh): this is the folder on your external disk."; exit 2; }
[ -n "${PASSWORD_FILE:-}" ] && [ -s "$PASSWORD_FILE" ] || { echo "ERROR: PASSWORD_FILE is not set, does not exist or is empty (backup_config.sh). Create a text file with the repository password on the first line."; exit 2; }

kopia_one() {
  local repo="$1" cfg="$2"
  if [ ! -f "$cfg" ]; then
    if [ -f "$repo/kopia.repository.f" ]; then
      kopia --config-file="$cfg" repository connect filesystem --path="$repo" || return 1
    else
      mkdir -p "$repo"
      kopia --config-file="$cfg" repository create filesystem --path="$repo" || return 1
      if [ -f "$HERE/exclude.txt" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
          line="${line%$'\r'}"
          [ -n "$line" ] && kopia --config-file="$cfg" policy set --global --add-ignore="$line" >/dev/null
        done < "$HERE/exclude.txt"
      fi
    fi
  fi
  if [ "$ACTION" = "verify" ]; then
    kopia --config-file="$cfg" snapshot verify --verify-files-percent=5
  else
    kopia --config-file="$cfg" snapshot create "$SOURCE_DIR"
  fi
}

restic_one() {
  local repo="$1"
  restic --repo "$repo" cat config >/dev/null 2>&1 || restic --repo "$repo" init || return 1
  if [ "$ACTION" = "verify" ]; then
    restic --repo "$repo" check --read-data-subset=5%
  elif [ -f "$HERE/exclude.txt" ]; then
    restic --repo "$repo" backup "$SOURCE_DIR" --exclude-file="$HERE/exclude.txt"
  else
    restic --repo "$repo" backup "$SOURCE_DIR"
  fi
}

failed() { echo; echo "ERROR: $ACTION failed. Read the messages above. Nothing was deleted."; exit 1; }

if [ "$TOOL" = "kopia" ]; then
  KOPIA_PASSWORD="$(head -n 1 "$PASSWORD_FILE" | tr -d '\r')"; export KOPIA_PASSWORD
  kopia_one "$REPO1" "$HERE/kopia_repo1.config" || failed
  [ -n "${REPO2:-}" ] && { kopia_one "$REPO2" "$HERE/kopia_repo2.config" || failed; }
else
  export RESTIC_PASSWORD_FILE="$PASSWORD_FILE"
  restic_one "$REPO1" || failed
  [ -n "${REPO2:-}" ] && { restic_one "$REPO2" || failed; }
fi
echo
echo "OK: $ACTION finished ($TOOL)."
[ "$ACTION" = "backup" ] && echo "Run \"./backup_linux.sh verify\" once a month and try to restore a file by hand."
exit 0
