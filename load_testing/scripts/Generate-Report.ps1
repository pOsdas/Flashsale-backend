param(
    [string]$Summary = ".\load_testing\results\capacity-summary.json",
    [string]$Output = ".\load_testing\results\capacity-report.md",
    [string]$Window = "1h"
)
. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites

$summaryPath = [System.IO.Path]::GetFullPath((Join-Path $script:LoadLabRoot $Summary))
$outputPath = [System.IO.Path]::GetFullPath((Join-Path $script:LoadLabRoot $Output))
$generator = Join-Path $script:LoadLabRoot "load_testing\scripts\generate_report.py"

& python $generator `
    --summary $summaryPath `
    --output $outputPath `
    --window $Window
if ($LASTEXITCODE -ne 0) {
    throw "Report generation failed with exit code $LASTEXITCODE."
}
Write-Host "Report created: $outputPath" -ForegroundColor Green
