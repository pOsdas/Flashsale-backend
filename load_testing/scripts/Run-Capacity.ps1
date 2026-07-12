param(
    [int]$PeakVUs = 1000,
    [string]$RampUp = "5m",
    [string]$Hold = "15m",
    [string]$RampDown = "3m",
    [string]$SimulatorProfile = "normal"
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run", "--rm", "--service-ports",
        "-e", "PEAK_VUS=$PeakVUs",
        "-e", "RAMP_UP=$RampUp",
        "-e", "HOLD=$Hold",
        "-e", "RAMP_DOWN=$RampDown",
        "-e", "SIMULATOR_PROFILE=$SimulatorProfile",
        "-e", "SUMMARY_FILE=/results/capacity-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/capacity-report.html",
        "k6", "run", "/scripts/capacity.js"
    )) `
    -Description "k6 capacity test"
