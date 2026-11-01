# Windows bootstrap. Idempotent; supports offline reruns after dependencies installed.
param([switch]$SkipInstall)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        if ($SkipInstall) { throw "Missing venv. Run setup-windows.ps1 without -SkipInstall first." }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        } else {
            throw "Python not found. Install Python 3.11+ and ensure it is on PATH."
        }
        if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
    }
    & $python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ required." }
    if (-not $SkipInstall) {
        & $python -m pip install -e ".[test]"
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Confirm pip/network access." }
    }
    & (Join-Path $PSScriptRoot "verify-windows.ps1") -Python $python
    if ($LASTEXITCODE -ne 0) { throw "Verification failed." }
    Write-Output "PASS: setup complete. Repeat safely; use -SkipInstall after dependencies are installed."
} finally {
    Pop-Location
}
