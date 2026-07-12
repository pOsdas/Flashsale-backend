param(
    [int]$StartRate = 10,
    [int]$MaxRate = 500,
    [int]$MaxVUs = 3000
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run", "--rm", "--service-ports",
        "-e", "START_RATE=$StartRate",
        "-e", "MAX_RATE=$MaxRate",
        "-e", "MAX_VUS=$MaxVUs",
        "-e", "SUMMARY_FILE=/results/breakpoint-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/breakpoint-report.html",
        "k6", "run", "/scripts/breakpoint.js"
    )) `
    -Description "k6 breakpoint test"
