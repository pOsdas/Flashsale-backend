param([switch]$DeleteData)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
$compose = Get-LoadComposeArgs -Mode capacity
Invoke-DockerChecked `
    -Arguments ($compose + @("down", "--remove-orphans")) `
    -Description "Stopping Capacity Lab"
if ($DeleteData) {
    foreach ($volume in @(
        "flashsale_load_postgres_data",
        "flashsale_load_prometheus_data",
        "flashsale_load_loki_data",
        "flashsale_load_grafana_data"
    )) {
        Remove-DockerVolumeIfExists -Name $volume
    }
}
