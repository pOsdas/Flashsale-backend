param(
    [int]$VUs = 300,
    [string]$Duration = "16m"
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run", "--rm", "--service-ports",
        "-e", "CHAOS_VUS=$VUs",
        "-e", "CHAOS_DURATION=$Duration",
        "-e", "SUMMARY_FILE=/results/chaos-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/chaos-report.html",
        "k6", "run", "/scripts/chaos.js"
    )) `
    -Description "k6 chaos test"
