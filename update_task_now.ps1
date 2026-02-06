# Update AITrader-Loop task to run hidden
# This script updates the task and shows the result

Write-Host "Updating AITrader-Loop task..." -ForegroundColor Cyan
Write-Host ""

$Command = 'PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -SleepSeconds 300 -LogToFile'

try {
    schtasks /Change /TN "AITrader-Loop" /TR $Command

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Task updated to run hidden!" -ForegroundColor Green
        Write-Host ""
        Write-Host "New configuration:" -ForegroundColor Yellow
        Write-Host "  - Runs hidden (no pop-ups)" -ForegroundColor Gray
        Write-Host "  - 5-minute check intervals" -ForegroundColor Gray
        Write-Host "  - Only runs during market hours (9:30 AM - 4:00 PM ET)" -ForegroundColor Gray
        Write-Host ""

        # Show current task info
        $Task = Get-ScheduledTask -TaskName "AITrader-Loop"
        Write-Host "Task status: $($Task.State)" -ForegroundColor Cyan
        Write-Host ""

        Write-Host "To start the loop now, run:" -ForegroundColor Yellow
        Write-Host "  schtasks /Run /TN 'AITrader-Loop'" -ForegroundColor Gray
    } else {
        Write-Host "ERROR: Failed to update task (exit code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "Make sure you're running as Administrator" -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to close"
