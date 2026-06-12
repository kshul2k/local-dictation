param(
    [string]$OutputDir = "diagnostics\npu_diagnostics",
    [switch]$RetryQnnLoad,
    [int]$CommandTimeoutSeconds = 20
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $root "$OutputDir\$stamp"
New-Item -ItemType Directory -Force -Path $target | Out-Null

function Invoke-Capture {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    $path = Join-Path $target "$Name.txt"
    "### $Name" | Out-File -FilePath $path -Encoding utf8
    "### $(Get-Date -Format o)" | Out-File -FilePath $path -Encoding utf8 -Append
    "" | Out-File -FilePath $path -Encoding utf8 -Append

    try {
        & $Command 2>&1 | Out-File -FilePath $path -Encoding utf8 -Append
    }
    catch {
        $_ | Out-File -FilePath $path -Encoding utf8 -Append
    }
}

function Invoke-CaptureNative {
    param(
        [string]$Name,
        [string]$FileName,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = $CommandTimeoutSeconds
    )

    $path = Join-Path $target "$Name.txt"
    $stdout = Join-Path $target "$Name.stdout.tmp"
    $stderr = Join-Path $target "$Name.stderr.tmp"

    "### $Name" | Out-File -FilePath $path -Encoding utf8
    "### $(Get-Date -Format o)" | Out-File -FilePath $path -Encoding utf8 -Append
    "### command: $FileName $($Arguments -join ' ')" | Out-File -FilePath $path -Encoding utf8 -Append
    "" | Out-File -FilePath $path -Encoding utf8 -Append

    try {
        $process = Start-Process -FilePath $FileName -ArgumentList $Arguments -NoNewWindow -Wait:$false -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $finished = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $finished) {
            Stop-Process -Id $process.Id -Force
            "Timed out after $TimeoutSeconds seconds." | Out-File -FilePath $path -Encoding utf8 -Append
        }
        $process.Refresh()
        "ExitCode: $($process.ExitCode)" | Out-File -FilePath $path -Encoding utf8 -Append
        "" | Out-File -FilePath $path -Encoding utf8 -Append
        if (Test-Path $stdout) {
            Get-Content -Path $stdout | Out-File -FilePath $path -Encoding utf8 -Append
        }
        if (Test-Path $stderr) {
            "" | Out-File -FilePath $path -Encoding utf8 -Append
            "### stderr" | Out-File -FilePath $path -Encoding utf8 -Append
            Get-Content -Path $stderr | Out-File -FilePath $path -Encoding utf8 -Append
        }
    }
    catch {
        $_ | Out-File -FilePath $path -Encoding utf8 -Append
    }
    finally {
        Remove-Item -Path $stdout, $stderr -ErrorAction SilentlyContinue
    }
}

Invoke-Capture "system" {
    Get-ComputerInfo | Select-Object OsName, OsDisplayVersion, OsVersion, OsBuildNumber, WindowsVersion
    Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, SystemType, TotalPhysicalMemory
    Get-CimInstance Win32_ComputerSystemProduct | Select-Object Vendor, Name, Version, IdentifyingNumber
}

Invoke-Capture "npu_driver_cim" {
    Get-CimInstance Win32_PnPSignedDriver |
        Where-Object {
            $_.DeviceName -match "Hexagon|NPU|Neural|Qualcomm|QNN|AI" -or
            $_.Manufacturer -match "Qualcomm"
        } |
        Sort-Object DeviceName |
        Format-List DeviceName, Manufacturer, DriverProviderName, DriverVersion, DriverDate, InfName, DeviceID
}

Invoke-Capture "npu_driver_pnputil" {
    pnputil /enum-drivers |
        Select-String -Pattern "Qualcomm|Hexagon|NPU|Neural|QNN" -Context 4,6
}

Invoke-CaptureNative "foundry_version" "foundry" @("--version") 10
Invoke-CaptureNative "foundry_status" "foundry" @("status") 15
Invoke-CaptureNative "foundry_cache_ls" "foundry" @("cache", "ls") 15

if ($RetryQnnLoad) {
    Invoke-CaptureNative "foundry_qnn_load_retry" "foundry" @("model", "load", "qwen2.5-0.5b-instruct-qnn-npu:1") 90
    Invoke-CaptureNative "foundry_status_after_load" "foundry" @("status") 15
}

$logDir = Join-Path $env:USERPROFILE ".foundry\logs"
if (Test-Path $logDir) {
    $logTarget = Join-Path $target "foundry_logs"
    New-Item -ItemType Directory -Force -Path $logTarget | Out-Null
    Get-ChildItem -Path $logDir -Filter "foundry*.log" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 5 |
        Copy-Item -Destination $logTarget -Force
}

Write-Host "Diagnostics written to $target"
if (-not $RetryQnnLoad) {
    Write-Host "No QNN model load was retried. Add -RetryQnnLoad after changing driver/CLI state."
}
