. "$PSScriptRoot\Common.ps1"
Assert-LoadLabPrerequisites
Assert-LoadLabSecrets

$capacity = Get-LoadComposeArgs -Mode capacity
$integration = Get-LoadComposeArgs -Mode integration

Write-Host "Checking Capacity compose..."
Invoke-DockerChecked `
    -Arguments ($capacity + @("config", "--quiet")) `
    -Description "Capacity Compose validation"

Write-Host "Checking Integration compose..."
Invoke-DockerChecked `
    -Arguments ($integration + @("config", "--quiet")) `
    -Description "Integration Compose validation"

Write-Host "Checking Python syntax..."
& python -m compileall -q `
    (Join-Path $script:LoadLabRoot "backend\app\api\v1\load_testing") `
    (Join-Path $script:LoadLabRoot "load_testing\scripts\generate_report.py")
if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed." }

Write-Host "Checking dashboard JSON..."
Get-ChildItem (Join-Path $script:LoadLabRoot "grafana\dashboards\*.json") | ForEach-Object {
    & python -m json.tool $_.FullName *> $null
    if ($LASTEXITCODE -ne 0) { throw "Invalid dashboard JSON: $($_.FullName)" }
}

Write-Host "Checking YAML..."
$yamlValidator = Join-Path $PSScriptRoot "validate_yaml.py"
& python $yamlValidator $script:LoadLabRoot
if ($LASTEXITCODE -ne 0) { throw "YAML validation failed." }

if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Checking k6 JavaScript syntax..."
    Get-ChildItem (Join-Path $script:LoadLabRoot "load_testing\k6") -Recurse -Filter *.js | ForEach-Object {
        & node --check $_.FullName *> $null
        if ($LASTEXITCODE -ne 0) { throw "Invalid JavaScript: $($_.FullName)" }
    }
}
else {
    Write-Warning "Node.js is not installed; JavaScript syntax check skipped. Docker k6 will still run the scripts."
}

if (Get-Command go -ErrorAction SilentlyContinue) {
    Write-Host "Checking simulator..."
    Push-Location (Join-Path $script:LoadLabRoot "load_testing\simulator")
    try {
        & go test ./...
        if ($LASTEXITCODE -ne 0) { throw "Simulator tests failed." }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Warning "Go is not installed; simulator unit tests skipped. Docker will build it during startup."
}

Write-Host "Load Lab configuration is valid." -ForegroundColor Green
