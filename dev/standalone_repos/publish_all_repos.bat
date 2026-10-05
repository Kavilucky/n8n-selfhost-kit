@echo off
rem Публикация всех автономных репозиториев на GitHub под аккаунтом Kavilucky.
rem Требуется: git и GitHub CLI (gh), вход выполнен: gh auth login
rem Запуск двойным щелчком или из cmd в этой папке: publish_all_repos.bat
chcp 65001 >nul
setlocal enabledelayedexpansion
set OWNER=Kavilucky
cd /d "%~dp0"

where gh >nul 2>nul || (echo Не найден gh. Установите: https://cli.github.com & pause & exit /b 1)
gh auth status >nul 2>nul || (echo Нет входа в GitHub. Выполните: gh auth login & pause & exit /b 1)

set OK=0
set FAIL=0
for %%R in (ep01-n8n-selfhost ep02-whisper-transcribe ep03-local-doc-ai ep04-news-pipeline-n8n ep05-carplay-assistant ep06-photo-dedup ep07-immich-cloud ep08-receipt-parser ep09-backup-321 ep10-obsidian-second-brain ep11-home-assistant ep12-password-leak-check ep13-voice-estimator ep14-debt-collector ep15-local-docs-parser ep16-proxy-traffic-check) do (
  echo === %%R
  if not exist "%%R" (
    echo   пропуск: нет папки
    set /a FAIL+=1
  ) else (
    pushd "%%R"
    rem если папка без .git - создаём репозиторий и коммит
    if not exist ".git" (
      git init -q -b main
      git add -A
      set "N=%%R"
      git commit -q -m "feat: initial release for episode !N:~2,2!"
    )
    gh repo create %OWNER%/%%R --public --source=. --push
    if errorlevel 1 (set /a FAIL+=1) else (set /a OK+=1)
    popd
  )
)
echo Готово. Успешно: !OK!, с ошибками: !FAIL!
pause
