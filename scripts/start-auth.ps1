# Start Poruta Auth Service
# Usage:
#   .\scripts\start-auth.ps1            # runs with defaults (port 8050)
#   .\scripts\start-auth.ps1 -Port 8051 # specify different port

param(
    [int]$Port = 8050
)

# Get the auth_services directory (parent of scripts/)
$AUTH_DIR = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Poruta Auth Service..." -ForegroundColor Green
Write-Host "  Directory: $AUTH_DIR" -ForegroundColor Gray
Write-Host "  Port: $Port" -ForegroundColor Gray
Write-Host ""

# Set PYTHONPATH and change to directory
$env:PYTHONPATH = $AUTH_DIR
Set-Location $AUTH_DIR

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found. Copy .env.example to .env and configure it." -ForegroundColor Red
    exit 1
}

# Run with uvicorn (reload for development)
python -m uvicorn src.main:app --host 0.0.0.0 --port $Port --reload
