#!/usr/bin/env bash
# Публикация всех автономных репозиториев на GitHub под аккаунтом Kavilucky.
# Требуется: git и GitHub CLI (gh), выполнен вход: gh auth login
# Запуск из этой папки:  bash publish_all_repos.sh
# Режим проверки без отправки:  DRY_RUN=1 bash publish_all_repos.sh
set -u
OWNER="Kavilucky"
cd "$(dirname "$0")" || exit 1

REPOS=(
  "ep01-n8n-selfhost"
  "ep02-whisper-transcribe"
  "ep03-local-doc-ai"
  "ep04-news-pipeline-n8n"
  "ep05-carplay-assistant"
  "ep06-photo-dedup"
  "ep07-immich-cloud"
  "ep08-receipt-parser"
  "ep09-backup-321"
  "ep10-obsidian-second-brain"
  "ep11-home-assistant"
  "ep12-password-leak-check"
  "ep13-voice-estimator"
  "ep14-debt-collector"
  "ep15-local-docs-parser"
  "ep16-proxy-traffic-check"
)

if [ "${DRY_RUN:-0}" != "1" ]; then
command -v gh >/dev/null || { echo "Не найден gh. Установите: https://cli.github.com"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Нет входа в GitHub. Выполните: gh auth login"; exit 1; }
fi

GHID=""; [ "${DRY_RUN:-0}" = "1" ] || GHID=$(gh api user --jq .id)
OK=0; FAIL=0
for repo in "${REPOS[@]}"; do
  echo "=== $repo"
  [ -d "$repo" ] || { echo "  пропуск: нет папки"; FAIL=$((FAIL+1)); continue; }
  if [ "${DRY_RUN:-0}" = "1" ]; then echo "  [dry-run] gh repo create $OWNER/$repo --public --source=. --push"; continue; fi
  (
    cd "$repo" || exit 1
    # нет .git или нет ни одного коммита - доделываем
    [ -d .git ] || git init -q -b main
    if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
      num="${repo#ep}"; num="${num%%-*}"
      git add -A && git -c user.name="$OWNER" -c user.email="$GHID+$OWNER@users.noreply.github.com" commit -q -m "feat: initial release for episode $num" || exit 1
    fi
    if gh repo view "$OWNER/$repo" >/dev/null 2>&1; then
      echo "  репозиторий уже есть на GitHub, отправляю изменения"
      git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$repo.git"
      git push -u origin main
    else
      gh repo create "$OWNER/$repo" --public --source=. --push
    fi
  ) && OK=$((OK+1)) || { echo "  ОШИБКА: $repo"; FAIL=$((FAIL+1)); }
  sleep 2  # пауза против rate limit API GitHub
done
echo "Готово. Успешно: $OK, с ошибками: $FAIL"
