param([int]$Count = 1)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets
if ($Count -lt 1 -or $Count -gt 20) {
    throw "Integration notification count must be between 1 and 20."
}
$compose = Get-LoadComposeArgs -Mode integration
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "exec", "-T", "backend", "python", "manage.py",
        "create_notification_burst", "--count", "$Count"
    )) `
    -Description "Creating real integration notification"
Write-Host "Created $Count notification event(s) for the configured integration test chat."
