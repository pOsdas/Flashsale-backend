param([int]$Count = 1000)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
if ($Count -lt 1) { throw "Count must be positive." }
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "exec", "-T", "backend", "python", "manage.py",
        "create_notification_burst", "--count", "$Count"
    )) `
    -Description "Creating notification storm"
Write-Host "Created $Count real outbox events. Watch Outbox, RabbitMQ and Notification dashboards."
