$ErrorActionPreference = "Stop"

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "Local Dictation Cleanup.lnk"

if (Test-Path $shortcutPath) {
    Remove-Item -Path $shortcutPath -Force
    Write-Host "Removed startup shortcut: $shortcutPath"
}
else {
    Write-Host "Startup shortcut was not installed: $shortcutPath"
}
