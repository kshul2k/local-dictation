param(
    [switch]$SkipDownload
)

$ErrorActionPreference = "Continue"

$models = @(
    "qwen2.5-0.5b-instruct-qnn-npu:1",
    "qwen2.5-coder-0.5b-instruct-qnn-npu:1"
)

Write-Host "Smallest Foundry NPU text/chat variants currently seen in the catalog:"
Write-Host "  qwen2.5-0.5b-instruct-qnn-npu:1        442 MB"
Write-Host "  qwen2.5-coder-0.5b-instruct-qnn-npu:1  442 MB"
Write-Host ""

foundry --version
foundry status
foundry cache ls

foreach ($model in $models) {
    Write-Host ""
    Write-Host "=== $model ==="
    foundry server stop
    foundry server start

    if (-not $SkipDownload) {
        foundry model download $model
    }

    foundry model load $model
    foundry status
    foundry model unload $model
}
