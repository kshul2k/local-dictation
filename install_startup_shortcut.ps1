$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "Local Dictation Cleanup.lnk"
$scriptPath = Join-Path $PSScriptRoot "start_local_dictation_stack.ps1"
$powershellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Starts local dictation cleanup server and OpenWhispr DB watcher."
$shortcut.Save()

Write-Host "Installed startup shortcut: $shortcutPath"
