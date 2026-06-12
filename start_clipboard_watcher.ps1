param(
    [switch]$NoPaste,
    [string]$SourceProcess = "OpenWhispr.exe"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
$runDir = Join-Path $PSScriptRoot "run"
New-Item -ItemType Directory -Force -Path $logDir, $runDir | Out-Null
$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot "cache\pycache"

$watcherScript = Join-Path $PSScriptRoot "src\clipboard_cleanup_watcher.py"
$argsList = @($watcherScript)
if ($NoPaste) {
    $argsList += "--no-paste"
}
if ($SourceProcess) {
    $argsList += "--source-process"
    $argsList += $SourceProcess
}

Remove-Item -Path (Join-Path $runDir "clipboard_watcher.stop") -ErrorAction SilentlyContinue

$processLog = Join-Path $logDir "clipboard_watcher.process.log"
$watcherArgs = ""
if ($NoPaste) {
    $watcherArgs = " --no-paste"
}
if ($SourceProcess) {
    $watcherArgs += " --source-process '$SourceProcess'"
}

$command = @"
Set-Location '$PSScriptRoot'
`$env:PYTHONPYCACHEPREFIX = '$PSScriptRoot\cache\pycache'
& '$PSScriptRoot\.venv\Scripts\python.exe' '$watcherScript'$watcherArgs *>> '$processLog'
"@

$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$processInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
$processInfo.WorkingDirectory = $PSScriptRoot
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $processInfo
$null = $process.Start()

Write-Host "Clipboard cleanup watcher started. PID $($process.Id)"
