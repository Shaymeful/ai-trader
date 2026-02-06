# Start loop with 5-minute interval in background (no admin required)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = "logs\loop"
$logFile = "$logDir\loop_5min_$timestamp.log"

# Ensure log directory exists
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Host "================================================"
Write-Host "Starting Trading Loop - 5 Minute Interval"
Write-Host "================================================"
Write-Host ""
Write-Host "Mode: Paper Trading (LIVE)"
Write-Host "Interval: 300 seconds (5 minutes)"
Write-Host "Log: $logFile"
Write-Host ""

# Build command
$pythonExe = ".\.venv\Scripts\python.exe"
$args = "-m", "src.app.runner", "--mode", "paper", "--loop", "--sleep-seconds", "300", "--cancel-open-orders"

# Start as background process
$process = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err" -PassThru

Write-Host "✅ Loop started in background" -ForegroundColor Green
Write-Host "   Process ID: $($process.Id)"
Write-Host "   Log: $logFile"
Write-Host ""
Write-Host "To stop:"
Write-Host "   taskkill /PID $($process.Id) /F"
Write-Host ""
Write-Host "To monitor:"
Write-Host "   Get-Content $logFile -Tail 20 -Wait"
Write-Host ""

# Save PID to file for later reference
$process.Id | Out-File "logs\loop_5min.pid" -Encoding ASCII
Write-Host "PID saved to: logs\loop_5min.pid"
