param([string]$Root = "$env:USERPROFILE\BuscaInstaRadar", [int]$Port = 8766)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Configure .venv first (see scripts/setup-windows.ps1)" }
& $python -m buscainsta.radar.server --root $Root --port $Port
if ($LASTEXITCODE -ne 0) { throw "Radar exited with an error" }
