param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RagArgs
)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $env:USERPROFILE '.cache\xiaolun-gpu-bench-20261014\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Isolated CUDA Python not found: $taskPython"
}
$taskRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8 = '1'
Push-Location $taskRoot
try {
    & $taskPython -c 'import torch; assert torch.cuda.is_available(), "CUDA unavailable; CPU fallback disabled"; print(torch.cuda.get_device_name(0))'
    if ($LASTEXITCODE -ne 0) { throw 'CUDA preflight failed' }
    & $taskPython (Join-Path $PSScriptRoot 'dual_corpus_rag.py') --require-cuda @RagArgs
    if ($LASTEXITCODE -ne 0) { throw "GPU RAG failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
