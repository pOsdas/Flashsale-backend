param(
    [switch]$ConfirmDestructiveChaos,
    [int]$FailureSeconds = 30
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets

if (-not $ConfirmDestructiveChaos) {
    throw "This script intentionally interrupts isolated Load Lab services. Re-run with -ConfirmDestructiveChaos."
}
if ($FailureSeconds -lt 5 -or $FailureSeconds -gt 300) {
    throw "FailureSeconds must be between 5 and 300."
}

$compose = Get-LoadComposeArgs -Mode capacity

Write-Host "Redis outage for $FailureSeconds seconds" -ForegroundColor Yellow
Invoke-DockerChecked -Arguments ($compose + @("stop", "redis")) -Description "Stopping Redis"
Start-Sleep -Seconds $FailureSeconds
Invoke-DockerChecked -Arguments ($compose + @("start", "redis")) -Description "Starting Redis"
Start-Sleep -Seconds 30

Write-Host "Notification consumer outage for $FailureSeconds seconds" -ForegroundColor Yellow
Invoke-DockerChecked -Arguments ($compose + @("stop", "notification_consumer")) -Description "Stopping notification consumer"
Start-Sleep -Seconds $FailureSeconds
Invoke-DockerChecked -Arguments ($compose + @("start", "notification_consumer")) -Description "Starting notification consumer"
Start-Sleep -Seconds 30

Write-Host "RabbitMQ restart" -ForegroundColor Yellow
Invoke-DockerChecked -Arguments ($compose + @("restart", "rabbitmq")) -Description "Restarting RabbitMQ"
Start-Sleep -Seconds 45

Write-Host "PostgreSQL pause for $FailureSeconds seconds" -ForegroundColor Yellow
$postgresId = & docker @compose ps -q postgres
if ($LASTEXITCODE -ne 0 -or -not $postgresId) {
    throw "Could not resolve the Capacity Lab PostgreSQL container."
}
Invoke-DockerChecked -Arguments @("pause", $postgresId.Trim()) -Description "Pausing PostgreSQL"
try {
    Start-Sleep -Seconds $FailureSeconds
}
finally {
    Invoke-DockerChecked -Arguments @("unpause", $postgresId.Trim()) -Description "Unpausing PostgreSQL"
}

Write-Host "Infrastructure chaos sequence completed. Check recovery, queue drain, losses and duplicates." -ForegroundColor Green
