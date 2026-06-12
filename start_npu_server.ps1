param(
    [string]$Model = "qwen2.5-0.5b"
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$env:DICTATION_CLEANUP_MODEL = $Model
$env:DICTATION_CLEANUP_REGISTER_EPS = "QNNExecutionProvider"
$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot "cache\pycache"

& "$PSScriptRoot\.venv\Scripts\python.exe" -u "$PSScriptRoot\src\cleanup_server.py"
