. "$PSScriptRoot\Common.ps1"

Assert-LoadLabPrerequisites
Assert-LoadLabSecrets

$compose = Get-LoadComposeArgs -Mode capacity

Write-Host "Ensuring smoke-test dependencies are running..." -ForegroundColor Cyan

Invoke-DockerChecked `
    -Arguments ($compose + @(
        "up",
        "-d",
        "backend",
        "load_simulator"
    )) `
    -Description "Starting smoke-test dependencies"

Write-Host "Waiting for backend readiness..." -ForegroundColor Cyan

Wait-LoadLabHttp `
    -Url "http://127.0.0.1:8000/api/v1/prometheus/metrics" `
    -Attempts 90 `
    -DelaySeconds 2 `
    -Name "backend"

Write-Host "Backend is ready." -ForegroundColor Green

Write-Host "Waiting for load simulator readiness..." -ForegroundColor Cyan

Wait-LoadLabHttp `
    -Url "http://127.0.0.1:8099/__control/state" `
    -Attempts 90 `
    -DelaySeconds 2 `
    -Name "load simulator"

Write-Host "Load simulator is ready." -ForegroundColor Green
Write-Host "Starting k6 smoke test..." -ForegroundColor Cyan

Invoke-DockerChecked `
    -Arguments ($compose + @(
        "run",
        "--rm",
        "--service-ports",
        "-e", "SUMMARY_FILE=/results/smoke-summary.json",
        "-e", "K6_WEB_DASHBOARD_EXPORT=/results/smoke-report.html",
        "k6",
        "run",
        "/scripts/smoke.js"
    )) `
    -Description "k6 smoke test"