param(
    [int]$UpdatesPerSecond = 20,
    [string]$Duration = "10m",
    [int]$MaxVUs = 500
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run", "--rm", "--service-ports",
        "-e", "TELEGRAM_UPDATE_RATE=$UpdatesPerSecond",
        "-e", "TELEGRAM_DURATION=$Duration",
        "-e", "TELEGRAM_MAX_VUS=$MaxVUs",
        "-e", "SUMMARY_FILE=/results/telegram-bot-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/telegram-bot-report.html",
        "k6", "run", "/scripts/telegram-bot.js"
    )) `
    -Description "k6 Telegram bot ingress test"
