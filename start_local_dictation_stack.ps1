param(
    [string]$Model = "qwen2.5-1.5b-instruct-generic-cpu:4"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot "cache\pycache"

$logPath = Join-Path $logDir "local_dictation_startup.log"
$serverLogPath = Join-Path $logDir "cleanup_server.startup.log"

function Write-StartupLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logPath -Value "$timestamp $Message"
}

function Test-CleanupServerListening {
    $lines = netstat -ano | Select-String -Pattern "127\.0\.0\.1:8765\s+.*LISTENING"
    return [bool]$lines
}

Write-StartupLog "startup_begin model=$Model"

try {
    powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "start_openwhispr_db_watcher.ps1")
    Write-StartupLog "watcher_launch_requested"
}
catch {
    Write-StartupLog "watcher_launch_failed error=$($_.Exception.Message)"
}

if (Test-CleanupServerListening) {
    Write-StartupLog "cleanup_server_already_listening"
    exit 0
}

$env:DICTATION_CLEANUP_MODEL = $Model
$env:DICTATION_CLEANUP_REGISTER_EPS = "skip"

Write-StartupLog "cleanup_server_starting"
try {
    & "$PSScriptRoot\.venv\Scripts\python.exe" -u "$PSScriptRoot\src\cleanup_server.py" *>> $serverLogPath
}
finally {
    Write-StartupLog "cleanup_server_exited"
}
