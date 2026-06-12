$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$runDir = Join-Path $PSScriptRoot "run"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType File -Path (Join-Path $runDir "openwhispr_db_watcher.stop") -Force | Out-Null
Start-Sleep -Milliseconds 500

try {
    $watchers = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.CommandLine -match "run_openwhispr_db_watcher.py|openwhispr_db_cleanup_watcher.py" -and
            $_.ExecutablePath -match "\\pythonw?(\.exe)?$"
        }

    foreach ($watcher in $watchers) {
        Stop-Process -Id $watcher.ProcessId -Force
        Write-Host "Stopped OpenWhispr DB watcher PID $($watcher.ProcessId)."
    }

    if (-not $watchers) {
        Write-Host "No OpenWhispr DB watcher process found."
    }
}
catch {
    Write-Host "Stop signal written. Process query was not available in this shell."
}
