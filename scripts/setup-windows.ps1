# Idempotent Windows bootstrap, no CRM or Instagram calls.
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher (py) not found. Install Python 3.11+." }
    & py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ not available." }
    & py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
    $python = Join-Path $root ".venv\Scripts\python.exe"
    & $python -m pip install -e ".[test]"
    if ($LASTEXITCODE -ne 0) { throw "Package installation failed." }
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
    $tempCsv = Join-Path ([System.IO.Path]::GetTempPath()) ("buscainsta-synthetic-" + [guid]::NewGuid().ToString("N") + ".csv")
    try {
        & $python -m buscainsta.cli sample --out $tempCsv --count 100
        if ($LASTEXITCODE -ne 0) { throw "Synthetic generation failed." }
        & $python -m buscainsta.cli validate --input $tempCsv --synthetic
        if ($LASTEXITCODE -ne 0) { throw "Synthetic CSV validation failed." }
    } finally {
        if (Test-Path -LiteralPath $tempCsv) { Remove-Item -LiteralPath $tempCsv -Force }
    }
    Write-Host "PASS: Windows offline POC; zero CRM/Instagram integrations. Safe to rerun."
} finally {
    Pop-Location
}
