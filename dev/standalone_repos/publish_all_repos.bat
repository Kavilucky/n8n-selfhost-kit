@echo off
chcp 65001 >nul
rem Публикация всех автономных репозиториев на GitHub под аккаунтом Kavilucky.
rem Требуется: git и GitHub CLI (gh). Установка:  winget install --id GitHub.cli
rem Вход (один раз):  gh auth login
rem Запуск: двойной щелчок или  publish_all_repos.bat  в cmd. Повторный запуск безопасен.
setlocal enabledelayedexpansion
set "OWNER=Kavilucky"
cd /d "%~dp0"

where git >nul 2>nul || goto :no_git
where gh >nul 2>nul || goto :no_gh
gh auth status >nul 2>nul || goto :no_auth

rem автор коммитов: GitHub noreply-адрес (личная почта в публичные коммиты не попадает)
for /f "delims=" %%i in ('gh api user --jq .id') do set "GHID=%%i"
set OK=0
set FAIL=0
for %%R in (ep01-n8n-selfhost ep02-whisper-transcribe ep03-local-doc-ai ep04-news-pipeline-n8n ep05-carplay-assistant ep06-photo-dedup ep07-immich-cloud ep08-receipt-parser ep09-backup-321 ep10-obsidian-second-brain ep11-home-assistant ep12-password-leak-check ep13-voice-estimator ep14-debt-collector ep15-local-docs-parser ep16-proxy-traffic-check) do call :publish %%R
echo.
echo Готово. Успешно: !OK!, с ошибками: !FAIL!
pause
exit /b 0

:publish
set "REPO=%~1"
set "CR="
echo === !REPO!
if not exist "!REPO!\" (
  echo   пропуск: нет папки !REPO!
  set /a FAIL+=1
  goto :eof
)
pushd "!REPO!"
rem нет .git или нет ни одного коммита (например, после прошлой неудачной попытки) - доделываем
if not exist ".git" git init -q -b main
git rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  set "N=!REPO:~2,2!"
  git add -A
  git -c user.name=%OWNER% -c user.email=!GHID!+%OWNER%@users.noreply.github.com commit -q -m "feat: initial release for episode !N!"
  if errorlevel 1 (
    echo   ОШИБКА: не удалось создать коммит в !REPO!
    set /a FAIL+=1
    popd
    goto :eof
  )
)
gh repo view %OWNER%/!REPO! >nul 2>nul
if not errorlevel 1 (
  echo   репозиторий уже есть на GitHub, отправляю изменения
  git remote get-url origin >nul 2>nul || git remote add origin https://github.com/%OWNER%/!REPO!.git
  git push -u origin main
) else (
  set "CR=1"
  gh repo create %OWNER%/!REPO! --public --source=. --push
)
if errorlevel 1 (
  echo   ОШИБКА: !REPO!
  set /a FAIL+=1
) else (
  set /a OK+=1
)
popd
rem пауза против лимита GitHub на создание репозиториев (после создания - длинная)
if defined CR (timeout /t 20 /nobreak >nul) else (timeout /t 2 /nobreak >nul)
goto :eof

:no_git
echo ОШИБКА: git не найден в PATH. Установите: winget install --id Git.Git  и откройте новое окно терминала.
pause
exit /b 1

:no_gh
echo ОШИБКА: GitHub CLI (gh) не найден в PATH.
echo Установите:  winget install --id GitHub.cli
echo Затем закройте и откройте терминал заново и выполните:  gh auth login
pause
exit /b 1

:no_auth
echo ОШИБКА: вход в GitHub не выполнен. Выполните один раз:  gh auth login
pause
exit /b 1
