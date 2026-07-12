$ErrorActionPreference = "Stop"

$script:LoadLabRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..")
)

function Assert-LoadLabPrerequisites {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI was not found in PATH."
    }

    $composeFile = Join-Path $script:LoadLabRoot "docker-compose.yml"
    if (-not (Test-Path $composeFile)) {
        throw "Run the script from the extracted Flashsale repository. Missing: $composeFile"
    }
}

function Get-LoadComposeArgs {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("capacity", "integration")]
        [string]$Mode
    )

    $args = @(
        "compose",
        "--project-directory", $script:LoadLabRoot,
        "--project-name", "flashsale-backend"
    )

    $envFile = Join-Path `
        $script:LoadLabRoot `
        "load_testing\.env.load"

    if (Test-Path $envFile) {
        $args += @(
            "--env-file",
            $envFile
        )
    }

    $args += @(
        "-f",
        (Join-Path $script:LoadLabRoot "docker-compose.yml")
    )

    if ($Mode -eq "capacity") {
        $args += @(
            "-f",
            (Join-Path $script:LoadLabRoot "docker-compose.load.yml")
        )
    }
    else {
        $args += @(
            "-f",
            (Join-Path $script:LoadLabRoot "docker-compose.integration.yml")
        )
    }

    return $args
}

function Invoke-DockerChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$Description = "Docker command"
    )

    & docker @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Description failed with exit code $exitCode."
    }
}

function Remove-DockerVolumeIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    # `docker volume inspect <missing-volume>` writes to stderr. With
    # `$ErrorActionPreference = "Stop"`, PowerShell treats that expected
    # result as a terminating error before we can inspect `$LASTEXITCODE`.
    # Listing volumes always exits successfully and lets us check existence
    # without using an error as normal control flow.
    $volumeNames = @(& docker volume ls --format "{{.Name}}")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list Docker volumes."
    }

    if ($volumeNames -contains $Name) {
        Invoke-DockerChecked `
            -Arguments @("volume", "rm", $Name) `
            -Description "Removing volume $Name"
    }
    else {
        Write-Host "Volume does not exist, skipping: $Name" -ForegroundColor DarkGray
    }
}

function Wait-LoadLabHttp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$Attempts = 90,
        [int]$DelaySeconds = 2,
        [string]$Name = "service"
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -TimeoutSec 3 `
                -Uri $Url
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            # The service is still starting.
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "$Name did not become ready: $Url"
}

function Assert-LoadLabSecrets {
    $envFile = Join-Path $script:LoadLabRoot "load_testing\.env.load"
    if (-not (Test-Path $envFile)) {
        throw "Create load_testing/.env.load from .env.load.example before running the lab."
    }

    $content = Get-Content $envFile -Raw
    if ($content -match "replace-with-at-least" -or $content -match "replace-with-another") {
        throw "Replace the example keys in load_testing/.env.load with random local values."
    }
}
