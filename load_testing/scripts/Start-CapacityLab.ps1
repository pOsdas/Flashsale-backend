param(
    [int]$Users = 1000,
    [int]$TargetsPerUser = 5,
    [switch]$ResetData,
    [switch]$SkipBuild
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets

if ($Users -lt 1) { throw "Users must be positive." }
if ($TargetsPerUser -lt 0) { throw "TargetsPerUser cannot be negative." }

$compose = Get-LoadComposeArgs -Mode capacity

if ($ResetData) {
    Invoke-DockerChecked `
        -Arguments ($compose + @("down", "--remove-orphans")) `
        -Description "Stopping previous Capacity Lab"

    foreach ($volume in @(
        "flashsale_load_postgres_data",
        "flashsale_load_prometheus_data",
        "flashsale_load_loki_data",
        "flashsale_load_grafana_data"
    )) {
        Remove-DockerVolumeIfExists -Name $volume
    }
}

$buildFlag = @()
if (-not $SkipBuild) { $buildFlag = @("--build") }

$bootstrapServices = @(
    "postgres", "pgbouncer", "redis", "rabbitmq", "load_simulator", "migrate", "backend",
    "postgres_exporter", "redis_exporter", "cadvisor", "blackbox_exporter",
    "loki", "promtail"
)
Invoke-DockerChecked `
    -Arguments ($compose + @("up", "-d") + $buildFlag + $bootstrapServices) `
    -Description "Starting Capacity Lab bootstrap services"

Wait-LoadLabHttp `
    -Url "http://127.0.0.1:8000/api/v1/prometheus/metrics" `
    -Name "backend"

Invoke-DockerChecked `
    -Arguments ($compose + @(
        "exec", "-T", "backend", "python", "manage.py", "prepare_load_test",
        "--users", "$Users",
        "--targets-per-user", "$TargetsPerUser",
        "--popular-products", "100",
        "--medium-products", "500",
        "--due-now",
        "--output", "/load-results/users.json",
        "--reset"
    )) `
    -Description "Preparing Capacity Lab dataset"

$runtimeServices = @(
    "outbox_worker", "monitoring_scanner", "notification_consumer",
    "telegram_bot", "prometheus"
)
Invoke-DockerChecked `
    -Arguments ($compose + @("up", "-d") + $buildFlag + $runtimeServices) `
    -Description "Starting Capacity Lab runtime services"

Wait-LoadLabHttp `
    -Url "http://127.0.0.1:9090/-/ready" `
    -Name "Prometheus"
Start-Sleep -Seconds 35

Invoke-DockerChecked `
    -Arguments ($compose + @("up", "-d") + $buildFlag + @("grafana")) `
    -Description "Starting Capacity Lab Grafana"
Wait-LoadLabHttp -Url "http://127.0.0.1:3000/api/health" -Name "Grafana"

Write-Host ""
Write-Host "Capacity Load Lab is ready." -ForegroundColor Green
Write-Host "Users:      $Users"
Write-Host "Targets:    $($Users * $TargetsPerUser)"
Write-Host "Grafana:    http://127.0.0.1:3000"
Write-Host "Prometheus: http://127.0.0.1:9090"
Write-Host "Simulator:  http://127.0.0.1:8099/__control/state"
Write-Host "Run smoke:  .\load_testing\scripts\Run-Smoke.ps1"
Write-Host "Run 1000:   .\load_testing\scripts\Run-Capacity.ps1 -PeakVUs 1000"
Write-Host "Bot load:   .\load_testing\scripts\Run-TelegramBotLoad.ps1 -UpdatesPerSecond 20"
