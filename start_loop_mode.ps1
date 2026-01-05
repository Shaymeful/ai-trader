# AI Trader - Start Loop Mode (Hourly Execution)
# Enhanced PowerShell version with better logging

param(
    [Parameter(Mandatory=$false)]
    [int]$SleepSeconds = 3600,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [switch]$Background
)

# Get project root
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Change to project directory
Set-Location $ProjectRoot

# Ensure logs directory exists
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Display configuration
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  AI TRADER - LOOP MODE (Hourly Paper Trading)" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Mode:              Paper Trading"
Write-Host "  Registry:          Equity-based allocation ENABLED"
Write-Host "  Sleep Interval:    $SleepSeconds seconds ($([math]::Round($SleepSeconds/3600, 2)) hours)"
Write-Host "  Dry-Run:           $DryRun"
Write-Host "  Project Root:      $ProjectRoot"
Write-Host ""
Write-Host "Output Logs:" -ForegroundColor Yellow
Write-Host "  Loop status:       logs\loop_status.log"
Write-Host "  Loop errors:       logs\loop_errors.log"
Write-Host "  Trade results:     logs\paper_run_*.jsonl"
Write-Host ""

if ($Background) {
    Write-Host "Mode:                BACKGROUND (detached process)" -ForegroundColor Green
} else {
    Write-Host "Mode:                FOREGROUND (press Ctrl+C to stop)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

# Build command arguments
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Args = @(
    "-m", "src.app.runner",
    "--mode", "paper",
    "--loop",
    "--sleep-seconds", $SleepSeconds
)

if ($DryRun) {
    $Args += "--dry-run"
}

# Run in foreground or background
if ($Background) {
    Write-Host "Starting loop mode in background..." -ForegroundColor Green
    Write-Host ""

    $Process = Start-Process -FilePath $PythonExe `
                            -ArgumentList $Args `
                            -WorkingDirectory $ProjectRoot `
                            -NoNewWindow `
                            -PassThru

    Write-Host "[OK] Loop mode started successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Process ID: $($Process.Id)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To monitor:" -ForegroundColor Yellow
    Write-Host "  Get-Content logs\loop_status.log -Tail 20 -Wait"
    Write-Host ""
    Write-Host "To stop:" -ForegroundColor Yellow
    Write-Host "  Stop-Process -Id $($Process.Id)"
    Write-Host ""

} else {
    Write-Host "Starting loop mode in foreground (press Ctrl+C to stop)..." -ForegroundColor Yellow
    Write-Host ""

    # Run in foreground
    & $PythonExe @Args

    Write-Host ""
    Write-Host "Loop mode stopped." -ForegroundColor Yellow
}
