param([switch]$DeleteData)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
$compose = Get-LoadComposeArgs -Mode integration
Invoke-DockerChecked `
    -Arguments ($compose + @("down", "--remove-orphans")) `
    -Description "Stopping Integration Lab"
if ($DeleteData) {
    foreach ($volume in @(
        "flashsale_integration_postgres_data",
        "flashsale_integration_prometheus_data",
        "flashsale_integration_loki_data",
        "flashsale_integration_grafana_data"
    )) {
        Remove-DockerVolumeIfExists -Name $volume
    }
}
