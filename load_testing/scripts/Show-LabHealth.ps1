param(
    [ValidateSet("capacity", "integration")]
    [string]$Mode = "capacity"
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
$compose = Get-LoadComposeArgs -Mode $Mode

Write-Host "=== Containers ==="
Invoke-DockerChecked -Arguments ($compose + @("ps")) -Description "Reading container status"

Write-Host "`n=== DOWN Prometheus targets ==="
$targets = (Invoke-RestMethod http://127.0.0.1:9090/api/v1/targets).data.activeTargets
$down = $targets | Where-Object { $_.health -ne "up" } | Select-Object `
    @{Name="job";Expression={$_.labels.job}}, `
    @{Name="instance";Expression={$_.labels.instance}}, health, lastError
if ($down) {
    $down | Format-Table -AutoSize
}
else {
    Write-Host "All targets are UP" -ForegroundColor Green
}

Write-Host "`n=== Dataset / pipeline status ==="
Invoke-DockerChecked `
    -Arguments ($compose + @(
        "exec", "-T", "backend", "python", "manage.py", "load_test_status"
    )) `
    -Description "Reading Load Lab status"

if ($Mode -eq "capacity") {
    Write-Host "`n=== Simulator ==="
    Invoke-RestMethod http://127.0.0.1:8099/__control/state | ConvertTo-Json -Depth 6
}
