$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$runDir = Join-Path $PSScriptRoot "run"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType File -Path (Join-Path $runDir "clipboard_watcher.stop") -Force | Out-Null
Start-Sleep -Milliseconds 500

try {
    $watchers = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.CommandLine -match "clipboard_cleanup_watcher.py" -and
            $_.ExecutablePath -match "\\python(\.exe)?$"
        }

    foreach ($watcher in $watchers) {
        Stop-Process -Id $watcher.ProcessId -Force
        Write-Host "Stopped clipboard watcher PID $($watcher.ProcessId)."
    }

    if (-not $watchers) {
        Write-Host "No clipboard watcher process found."
    }
}
catch {
    Write-Host "Stop signal written. Process query was not available in this shell."
}
