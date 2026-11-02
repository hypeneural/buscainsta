# Start BuscaInsta local dashboard on Windows.
# No credentials are printed; no auto-DM. Ctrl+C stops the local server.
param(
    [string]$Db = "C:\BuscaInstaPrivado\buscainsta.db",
    [string]$Contacts = "",
    [string]$Review = "",
    [string]$LegacyPanel = "",
    [string]$Account = "estudio_teste",
    [switch]$EnableInstagram,
    [switch]$EnableDirect,
    [string]$MessageFile = "",
    [int]$Port = 8765
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($EnableDirect -and -not $EnableInstagram) { throw "-EnableDirect requires -EnableInstagram" }
if ($EnableDirect -and -not $MessageFile) { throw "-EnableDirect requires -MessageFile" }
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = if ($EnableInstagram) { ".venv-live" } else { ".venv" }
$python = Join-Path $root "$venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment $venv missing. See docs/DASHBOARD.md."
}
$arguments = @("-m", "buscainsta.dashboard", "--db", $Db, "--account", $Account, "--port", [string]$Port)
if ($Contacts) { $arguments += @("--contacts", $Contacts) }
if ($Review) { $arguments += @("--review", $Review) }
if ($LegacyPanel) { $arguments += @("--legacy-panel", $LegacyPanel) }
if ($EnableInstagram) { $arguments += "--enable-instagram" }
if ($EnableDirect) { $arguments += "--enable-dm" }
if ($MessageFile) { $arguments += @("--message-file", $MessageFile) }
Push-Location $root
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "BuscaInsta dashboard exited with an error." }
} finally {
    Pop-Location
}
