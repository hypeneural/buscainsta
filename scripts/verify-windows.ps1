# Reproducible offline smoke test. No personal data persisted.
param([string]$Python = "")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    if (-not $Python) { $Python = Join-Path $root ".venv\Scripts\python.exe" }
    if (-not (Test-Path -LiteralPath $Python)) { throw "Python venv is missing; run setup-windows.ps1 first." }
    & $Python -m buscainsta.cli doctor
    if ($LASTEXITCODE -ne 0) { throw "Runtime doctor failed." }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
    $tempCsv = Join-Path ([System.IO.Path]::GetTempPath()) ("buscainsta-" + [guid]::NewGuid().ToString("N") + ".csv")
    try {
        & $Python -m buscainsta.cli sample --out $tempCsv --count 100 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Synthetic generation failed." }
        $output = & $Python -m buscainsta.cli validate --input $tempCsv --synthetic
        if ($LASTEXITCODE -ne 0) { throw "Synthetic validation failed." }
        $summary = $output | ConvertFrom-Json
        if ($summary.total -ne 100 -or $summary.valid -ne 100 -or $summary.invalid -ne 0) {
            throw "Expected 100/100 valid synthetic contacts."
        }
        if ($summary.network_calls -ne 0 -or $summary.external_uploads -ne 0) {
            throw "Network/upload reporting invariant failed."
        }
    } finally {
        if (Test-Path -LiteralPath $tempCsv) { Remove-Item -LiteralPath $tempCsv -Force }
    }
    Write-Output "PASS: synthetic 100/100, aggregated output, no Instagram or CRM integration."
} finally {
    Pop-Location
}
