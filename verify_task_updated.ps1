# Verify that AITrader-Loop task was updated correctly
# Run this AFTER updating as Administrator

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "VERIFYING TASK SCHEDULER UPDATE" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Check task exists
try {
    $Task = Get-ScheduledTask -TaskName "AITrader-Loop" -ErrorAction Stop
    Write-Host "[OK] Task exists" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Task not found!" -ForegroundColor Red
    exit 1
}

# Check task state
Write-Host "[INFO] Task state: $($Task.State)" -ForegroundColor Yellow

# Check task arguments
$Args = $Task.Actions.Arguments
Write-Host ""
Write-Host "Task arguments:" -ForegroundColor Cyan
Write-Host $Args -ForegroundColor Gray
Write-Host ""

# Verify specific settings
$HasHidden = $Args -match "-WindowStyle Hidden"
$Has5Min = $Args -match "SleepSeconds 300"
$HasLogToFile = $Args -match "-LogToFile"

Write-Host "Checking required settings:" -ForegroundColor Cyan
if ($HasHidden) {
    Write-Host "  [OK] Hidden mode enabled (-WindowStyle Hidden)" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] Hidden mode flag not found!" -ForegroundColor Red
}

if ($Has5Min) {
    Write-Host "  [OK] 5-minute interval (SleepSeconds 300)" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] Still using old interval!" -ForegroundColor Red
}

if ($HasLogToFile) {
    Write-Host "  [OK] Logging to file enabled" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] Log to file flag not found!" -ForegroundColor Red
}

Write-Host ""

# Check if running
$RunningPython = Get-Process -Name python -ErrorAction SilentlyContinue
if ($RunningPython) {
    Write-Host "[INFO] Python processes running:" -ForegroundColor Yellow
    $RunningPython | ForEach-Object {
        Write-Host "  PID: $($_.Id) | Memory: $([math]::Round($_.WorkingSet64/1MB, 2)) MB" -ForegroundColor Gray
    }
} else {
    Write-Host "[WARN] No python processes running" -ForegroundColor Yellow
}

Write-Host ""

# Check recent logs
$LogFile = "logs\loop_status.log"
if (Test-Path $LogFile) {
    Write-Host "Recent log entries (last 5 lines):" -ForegroundColor Cyan
    Get-Content $LogFile -Tail 5 | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
} else {
    Write-Host "[WARN] Log file not found: $LogFile" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan

# Summary
if ($HasHidden -and $Has5Min -and $HasLogToFile) {
    Write-Host "STATUS: Task is configured correctly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The loop should now:" -ForegroundColor Cyan
    Write-Host "  - Run hidden (no pop-ups)" -ForegroundColor Gray
    Write-Host "  - Check every 5 minutes" -ForegroundColor Gray
    Write-Host "  - Only run during market hours (Mon-Fri 9:30 AM - 4:00 PM ET)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Since market is closed now, you should see 'MARKET CLOSED' messages in logs." -ForegroundColor Yellow
} else {
    Write-Host "STATUS: Task needs to be updated!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run update_task_hidden.cmd as Administrator to fix this." -ForegroundColor Yellow
}

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
