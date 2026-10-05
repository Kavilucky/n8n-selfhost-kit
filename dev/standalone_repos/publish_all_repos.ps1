# Публикация всех автономных репозиториев на GitHub под аккаунтом Kavilucky.
# Требуется: git и GitHub CLI (gh). Установка:  winget install --id GitHub.cli
# Вход (один раз):  gh auth login
# Запуск в PowerShell:  powershell -ExecutionPolicy Bypass -File .\publish_all_repos.ps1
# Проверка без отправки:  .\publish_all_repos.ps1 -DryRun
# Повторный запуск безопасен: существующие репозитории только дополняются через git push.
param([switch]$DryRun)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Owner = "Kavilucky"
$Repos = @(
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

Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ОШИБКА: git не найден в PATH. Установите: winget install --id Git.Git и откройте новое окно PowerShell." -ForegroundColor Red
    exit 1
}
if (-not $DryRun) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "ОШИБКА: GitHub CLI (gh) не найден в PATH." -ForegroundColor Red
        Write-Host "Установите:  winget install --id GitHub.cli"
        Write-Host "Затем откройте PowerShell заново и выполните:  gh auth login"
        exit 1
    }
    gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ОШИБКА: вход в GitHub не выполнен. Выполните один раз:  gh auth login" -ForegroundColor Red
        exit 1
    }
}

# Автор коммитов: GitHub noreply-адрес (личная почта в публичные коммиты не попадает).
# Берётся только для этих репозиториев, глобальные настройки git не меняются.
$GitId = ""
if (-not $DryRun) {
    $GitId = (gh api user --jq .id).Trim()
}
$IdArgs = @("-c", "user.name=$Owner", "-c", "user.email=$GitId+$Owner@users.noreply.github.com")

$ok = 0; $fail = 0
foreach ($repo in $Repos) {
    Write-Host "=== $repo"
    $dir = Join-Path $PSScriptRoot $repo
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        Write-Host "  пропуск: нет папки $repo" -ForegroundColor Yellow
        $fail++; continue
    }
    if ($DryRun) { Write-Host "  [dry-run] gh repo create $Owner/$repo --public --source=. --push"; continue }

    Push-Location -LiteralPath $dir
    try {
        # нет .git или нет ни одного коммита (например, после прошлой неудачной попытки) - доделываем
        if (-not (Test-Path -LiteralPath ".git")) { git init -q -b main }
        git rev-parse --verify HEAD *> $null
        if ($LASTEXITCODE -ne 0) {
            $num = $repo.Substring(2, 2)
            git add -A
            git @IdArgs commit -q -m "feat: initial release for episode $num"
            if ($LASTEXITCODE -ne 0) { Write-Host "  ОШИБКА: не удалось создать коммит в $repo" -ForegroundColor Red; $fail++; continue }
        }
        gh repo view "$Owner/$repo" *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  репозиторий уже есть на GitHub, отправляю изменения"
            git remote get-url origin *> $null
            if ($LASTEXITCODE -ne 0) { git remote add origin "https://github.com/$Owner/$repo.git" }
            git push -u origin main
        } else {
            gh repo create "$Owner/$repo" --public --source=. --push
        }
        if ($LASTEXITCODE -eq 0) { $ok++ } else { Write-Host "  ОШИБКА: $repo" -ForegroundColor Red; $fail++ }
    } finally {
        Pop-Location
    }
    # пауза против rate limit API GitHub
    Start-Sleep -Seconds 2
}
Write-Host ""
Write-Host "Готово. Успешно: $ok, с ошибками: $fail"
