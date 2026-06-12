param(
    [switch]$NoPaste,
    [switch]$NoReplaceRawPaste
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot "cache\pycache"

$runner = Join-Path $PSScriptRoot "src\run_openwhispr_db_watcher.py"
$command = "start `"`" `"%LocalAppData%\Programs\Python\Python312-arm64\pythonw.exe`" `"$runner`""

if ($NoPaste) {
    $command += " --no-paste"
}
if (-not $NoReplaceRawPaste) {
    $command += " --replace-raw-paste"
}

& "$env:SystemRoot\System32\cmd.exe" /c $command
Write-Host "OpenWhispr DB cleanup watcher launch requested."
