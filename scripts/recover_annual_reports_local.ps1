param(
    [string]$SourceDir = "",
    [switch]$AllowDownload
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if (-not $SourceDir) {
    $SourceDir = Join-Path $ProjectRoot "data\companies\annual_reports"
}
$EnvironmentDir = Join-Path $ProjectRoot ".venv-data"
$Python = Join-Path $EnvironmentDir "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $EnvironmentDir
    } else {
        & python -m venv $EnvironmentDir
    }
    if ($LASTEXITCODE -ne 0) { throw "Python environment creation failed" }
}
& $Python -m pip install -r requirements-data.txt
if ($LASTEXITCODE -ne 0) { throw "PDF dependency installation failed" }
$Stamp = Get-Date -Format "yyyyMMddTHHmmssfff"
$OutputDir = Join-Path $ProjectRoot "results\runs\annual_local_$Stamp"
$RunArgs = @("-X", "utf8", "scripts/recover_and_extract_annual_reports.py", "--source-dir", $SourceDir, "--out-dir", $OutputDir)
if ($AllowDownload) { $RunArgs += "--allow-download" }
& $Python @RunArgs
$RunCode = $LASTEXITCODE
Write-Host "Saved results: $OutputDir"
exit $RunCode
