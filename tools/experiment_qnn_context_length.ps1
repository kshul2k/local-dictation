param(
    [ValidateSet(
        "qwen2.5-0.5b-instruct-qnn-npu:1",
        "qwen2.5-coder-0.5b-instruct-qnn-npu:1"
    )]
    [string]$Model = "qwen2.5-0.5b-instruct-qnn-npu:1",
    [int]$ContextLength = 4096,
    [string]$CacheRoot = "$env:USERPROFILE\.foundry\cache\models",
    [switch]$Restore
)

$ErrorActionPreference = "Stop"

if ($ContextLength -lt 512 -or $ContextLength -gt 32768) {
    throw "ContextLength must be between 512 and 32768."
}

$modelName, $modelVersion = $Model -split ":", 2
$modelDirName = "$modelName-$modelVersion"
$modelDir = Join-Path $CacheRoot "Microsoft\$modelDirName\v$modelVersion"

if (-not (Test-Path $modelDir)) {
    throw "Model cache directory not found: $modelDir"
}

$files = @(
    @{
        Path = Join-Path $modelDir "genai_config.json"
        Updates = @{
            "model.context_length" = $ContextLength
            "search.max_length" = $ContextLength
        }
    },
    @{
        Path = Join-Path $modelDir "config.json"
        Updates = @{
            "max_position_embeddings" = $ContextLength
        }
    }
)

foreach ($file in $files) {
    $path = $file.Path
    $backup = "$path.context-length-backup"

    if ($Restore) {
        if (Test-Path $backup) {
            Copy-Item -LiteralPath $backup -Destination $path -Force
            Write-Host "Restored $path"
        }
        else {
            Write-Host "No backup found for $path"
        }
        continue
    }

    if (-not (Test-Path $backup)) {
        Copy-Item -LiteralPath $path -Destination $backup
        Write-Host "Backed up $path"
    }

    $json = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    foreach ($entry in $file.Updates.GetEnumerator()) {
        $parts = $entry.Key -split "\."
        $target = $json
        for ($i = 0; $i -lt $parts.Length - 1; $i++) {
            $target = $target.($parts[$i])
        }
        $target.($parts[-1]) = $entry.Value
        Write-Host "Set $($entry.Key)=$($entry.Value) in $path"
    }

    $jsonText = $json | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $jsonText, $utf8NoBom)
}

if ($Restore) {
    Write-Host "Restore complete."
    exit 0
}

Write-Host ""
Write-Host "Patched $Model to ContextLength=$ContextLength in:"
Write-Host "  $modelDir"
Write-Host ""
Write-Host "Now run:"
Write-Host "  foundry server stop"
Write-Host "  foundry server start"
Write-Host "  foundry model load $Model"
Write-Host ""
Write-Host "To restore:"
Write-Host "  .\tools\experiment_qnn_context_length.ps1 -Model `"$Model`" -Restore"
