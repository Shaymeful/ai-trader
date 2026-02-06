# Start loop with 5-minute interval (no admin required)

$logFile = "logs\loop_5min_start.log"

Write-Host "================================================"
Write-Host "Starting Trading Loop - 5 Minute Interval"
Write-Host "================================================"
Write-Host ""
Write-Host "Mode: Paper Trading (LIVE)"
Write-Host "Interval: 300 seconds (5 minutes)"
Write-Host "Log: logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log"
Write-Host ""
Write-Host "This will run in the CURRENT window."
Write-Host "To run in background, use the scheduled task (requires admin)."
Write-Host ""
Write-Host "Starting in 3 seconds..."
Start-Sleep -Seconds 3

# Start the runner with 5-minute interval
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --loop --sleep-seconds 300 --cancel-open-orders 2>&1 | Tee-Object -FilePath $logFile
