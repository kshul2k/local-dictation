param(
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot "cache\pycache"

$pythonwPath = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonwPath)) {
    $pythonwPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}

$arguments = @((Join-Path $PSScriptRoot "src\tray_monitor.py"))
if ($NoStart) {
    $arguments += "--no-start"
}

Start-Process `
    -FilePath $pythonwPath `
    -ArgumentList $arguments `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden

Write-Host "Local Dictation tray monitor launch requested."
