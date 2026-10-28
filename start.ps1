# ClipDock local launcher for Windows PowerShell.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
  python -m venv .venv
}

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
& ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt

if (-not (Test-Path "frontend\node_modules")) {
  Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
  Push-Location frontend
  npm.cmd install
  Pop-Location
}

if (-not (Test-Path "frontend\dist\index.html")) {
  Write-Host "Building frontend..." -ForegroundColor Cyan
  Push-Location frontend
  npm.cmd run build
  Pop-Location
}

Write-Host ""
Write-Host "ClipDock: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Private tool. AI summary is optional; configure SUMMARY_API_KEY in .env." -ForegroundColor Yellow
Write-Host ""

& ".venv\Scripts\python.exe" -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
