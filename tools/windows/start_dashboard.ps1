#Requires -Version 5.1
<#
.SYNOPSIS
    Start AI Trader dashboard for morning trading session.

.DESCRIPTION
    Starts the FastAPI dashboard at 8:45 AM ET. The dashboard provides:
    - Real-time bot status monitoring
    - Selector status and candidate counts
    - Loop mode controls
    - Trading pause controls

.PARAMETER Port
    Port to run the dashboard on (default: 8000)

.EXAMPLE
    .\start_dashboard.ps1
    Start dashboard on default port 8000

.EXAMPLE
    .\start_dashboard.ps1 -Port 8080
    Start dashboard on port 8080
#>

param(
    [Parameter(Mandatory=$false)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# Get repository root (2 levels up from tools/windows)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

Write-Host "AI Trader Dashboard Startup" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Port: $Port"
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# Check if virtual environment exists
$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Host "ERROR: Virtual environment not found at $VenvPath" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv && .venv\Scripts\pip.exe install -e ." -ForegroundColor Yellow
    exit 1
}

# Check if dashboard script exists
$DashboardScript = Join-Path $RepoRoot "src\ui_api\app.py"
if (-not (Test-Path $DashboardScript)) {
    Write-Host "ERROR: Dashboard script not found: $DashboardScript" -ForegroundColor Red
    exit 1
}

Write-Host "Starting dashboard..." -ForegroundColor Green
Write-Host "Access at: http://localhost:$Port" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start dashboard using uvicorn
& "$VenvPath\Scripts\python.exe" -m uvicorn src.ui_api.app:app --host 0.0.0.0 --port $Port

Write-Host ""
Write-Host "Dashboard stopped." -ForegroundColor Yellow
