# Restart loop with hidden window fix applied

Write-Host "Checking for running Python processes..." -ForegroundColor Cyan

# Find ai-trader Python processes
$processes = Get-Process python*,pythonw* -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*ai-trader*"
}

if ($processes) {
    Write-Host "Found $($processes.Count) running process(es):" -ForegroundColor Yellow
    $processes | ForEach-Object {
        Write-Host "  PID $($_.Id): $($_.ProcessName) - $($_.Path)" -ForegroundColor Gray
    }

    Write-Host "`nStopping processes..." -ForegroundColor Yellow
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "Processes stopped." -ForegroundColor Green
} else {
    Write-Host "No running processes found." -ForegroundColor Gray
}

Write-Host "`nRestarting AITrader-Loop task..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName 'AITrader-Loop'

Write-Host "`nTask started! Windows should now be hidden." -ForegroundColor Green
Write-Host "Check logs/loop/loop_$(Get-Date -Format 'yyyyMMdd').log for output" -ForegroundColor Gray
