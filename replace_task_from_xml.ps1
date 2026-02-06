# Replace AITrader-Loop task using XML import
# This deletes the old task and creates a new one with updated settings
# MUST run as Administrator

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "REPLACING AITRADER-LOOP TASK" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as administrator'" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

try {
    # Step 1: Stop the task and kill old processes
    Write-Host "[1/5] Stopping old task and processes..." -ForegroundColor Yellow

    try {
        Stop-ScheduledTask -TaskName "AITrader-Loop" -ErrorAction SilentlyContinue
    } catch {
        # Task might not be running
    }

    Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "      Done" -ForegroundColor Green

    # Step 2: Unregister (delete) the old task
    Write-Host "[2/5] Deleting old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName "AITrader-Loop" -Confirm:$false -ErrorAction Stop
    Write-Host "      Done" -ForegroundColor Green

    # Step 3: Register new task from XML
    Write-Host "[3/5] Creating new task from XML..." -ForegroundColor Yellow
    $XmlPath = "C:\dev\ai-trader\AITrader-Loop-Updated.xml"

    if (-not (Test-Path $XmlPath)) {
        Write-Host "      ERROR: XML file not found: $XmlPath" -ForegroundColor Red
        exit 1
    }

    Register-ScheduledTask -Xml (Get-Content $XmlPath | Out-String) -TaskName "AITrader-Loop" -Force
    Write-Host "      Done" -ForegroundColor Green

    # Step 4: Verify the new task settings
    Write-Host "[4/5] Verifying new task settings..." -ForegroundColor Yellow
    $NewTask = Get-ScheduledTask -TaskName "AITrader-Loop"
    $Args = $NewTask.Actions.Arguments

    Write-Host "      Arguments: $Args" -ForegroundColor Gray

    $HasHidden = $Args -match "-WindowStyle Hidden"
    $Has5Min = $Args -match "SleepSeconds 300"

    if ($HasHidden) {
        Write-Host "      [OK] Hidden mode enabled" -ForegroundColor Green
    } else {
        Write-Host "      [ERROR] Hidden mode missing!" -ForegroundColor Red
    }

    if ($Has5Min) {
        Write-Host "      [OK] 5-minute interval configured" -ForegroundColor Green
    } else {
        Write-Host "      [ERROR] Still wrong interval!" -ForegroundColor Red
    }

    if (-not ($HasHidden -and $Has5Min)) {
        Write-Host ""
        Write-Host "ERROR: Task settings are still incorrect!" -ForegroundColor Red
        exit 1
    }

    # Step 5: Start the new task
    Write-Host "[5/5] Starting new task..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName "AITrader-Loop"
    Start-Sleep -Seconds 3
    Write-Host "      Done" -ForegroundColor Green

    # Final verification
    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor Green
    Write-Host "SUCCESS! TASK UPDATED AND RUNNING" -ForegroundColor Green
    Write-Host "=" * 80 -ForegroundColor Green
    Write-Host ""

    Write-Host "New configuration:" -ForegroundColor Cyan
    Write-Host "  - Runs HIDDEN (no pop-up windows)" -ForegroundColor Gray
    Write-Host "  - Checks every 5 MINUTES" -ForegroundColor Gray
    Write-Host "  - Only runs during MARKET HOURS (Mon-Fri 9:30 AM - 4:00 PM ET)" -ForegroundColor Gray
    Write-Host ""

    $RunningPython = Get-Process -Name python -ErrorAction SilentlyContinue
    if ($RunningPython) {
        Write-Host "Running processes:" -ForegroundColor Cyan
        $RunningPython | ForEach-Object {
            Write-Host "  PID: $($_.Id)" -ForegroundColor Gray
        }
    } else {
        Write-Host "WARNING: No python processes detected. Check logs." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Since market is closed now, the loop should log:" -ForegroundColor Yellow
    Write-Host "  'MARKET CLOSED - Next market open in: XX hours'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Check logs at: logs\loop_status.log" -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Read-Host "Press Enter to close"
