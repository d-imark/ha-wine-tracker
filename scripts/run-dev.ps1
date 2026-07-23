# run-dev.ps1 - Windows dev launcher for Wine Tracker (PowerShell twin of run-dev.sh)
#
# Usage (from anywhere):
#   .\scripts\run-dev.ps1
#   .\scripts\run-dev.ps1 -DevAuth "admin:admin"      # enable login locally
#
# Serves the app via waitress on http://localhost:5050

param(
    [string]$DevAuth = ""
)

$ErrorActionPreference = "Stop"

# Repo root = one level up from this script
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "No virtualenv found at .venv\. Create it first: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r wine-tracker\requirements.txt"
}

if ($DevAuth) { $env:DEV_AUTH = $DevAuth }

Write-Host "Starting Wine Tracker on http://localhost:5050 (Ctrl+C to stop)" -ForegroundColor Cyan
& $venvPython "wine-tracker\app\app.py"
