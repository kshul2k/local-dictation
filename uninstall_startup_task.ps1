$ErrorActionPreference = "Stop"

$taskName = "Local Dictation Cleanup"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Uninstalled scheduled task: $taskName"
}
else {
    Write-Host "Scheduled task was not installed: $taskName"
}
