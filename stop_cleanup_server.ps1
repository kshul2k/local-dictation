$ErrorActionPreference = "Stop"

$port = 8765
$lines = netstat -ano | Select-String -Pattern "127\.0\.0\.1:$port\s+.*LISTENING"
$process_ids = @(
    foreach ($line in $lines) {
        $parts = ($line.Line.Trim() -split "\s+")
        if ($parts.Length -ge 5) {
            [int]$parts[-1]
        }
    }
) | Select-Object -Unique

if (-not $process_ids) {
    Write-Host "No cleanup server is listening on port $port."
    exit 0
}

foreach ($process_id in $process_ids) {
    Stop-Process -Id $process_id -Force
    Write-Host "Stopped cleanup server pid=$process_id"
}
