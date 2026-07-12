param(
    [int]$VUs = 20,
    [string]$Duration = "10m"
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
$compose = Get-LoadComposeArgs -Mode integration
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run", "--rm", "--service-ports",
        "-e", "INTEGRATION_VUS=$VUs",
        "-e", "INTEGRATION_DURATION=$Duration",
        "-e", "SUMMARY_FILE=/results/integration-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/integration-report.html",
        "k6", "run", "/scripts/integration.js"
    )) `
    -Description "k6 integration test"
