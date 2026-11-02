param(
    [string]$Root = "$env:USERPROFILE\BuscaInstaRadar",
    [int]$Port = 8766,
    [switch]$RefreshMetaOnAccess,
    [int]$RefreshInterval = 1800
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Configure .venv first (see scripts/setup-windows.ps1)"
}
if ($RefreshMetaOnAccess -and (-not $env:RADAR_META_TOKEN -or -not $env:RADAR_META_IG_USER_ID)) {
    throw "Official Meta refresh requires RADAR_META_TOKEN and RADAR_META_IG_USER_ID"
}
$arguments = @("-m", "buscainsta.radar.server", "--root", $Root, "--port", [string]$Port)
if ($RefreshMetaOnAccess) {
    $arguments += @("--refresh-meta-on-access", "--refresh-interval", [string]$RefreshInterval)
}
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Radar exited with an error" }
