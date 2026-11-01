$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher (py) not found. Install Python 3.11+ and retry."
}
py -3 -m venv .venv
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[test]"
& $python -m pytest -q
& $python -m buscainsta.cli sample --out data/synthetic.csv --count 100
& $python -m buscainsta.cli validate --input data/synthetic.csv --synthetic
Write-Host "Local offline POC installed. No Instagram login or CRM connection performed."
