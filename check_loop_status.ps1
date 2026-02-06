# Check loop status

Write-Host "`nChecking for running pythonw.exe processes..." -ForegroundColor Cyan

$processes = Get-Process pythonw* -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*ai-trader*"
}

if ($processes) {
    Write-Host "Found $($processes.Count) pythonw.exe process(es) running:" -ForegroundColor Green
    $processes | Format-Table Id,ProcessName,StartTime,@{Label='Memory(MB)';Expression={$_.WS / 1MB -as [int]}} -AutoSize
    Write-Host "No windows should be visible (pythonw.exe runs hidden)." -ForegroundColor Green
} else {
    Write-Host "No pythonw.exe processes found. Loop may not be running." -ForegroundColor Yellow

    Write-Host "`nChecking for python.exe processes..." -ForegroundColor Cyan
    $pythonProcs = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like "*ai-trader*"
    }

    if ($pythonProcs) {
        Write-Host "Found $($pythonProcs.Count) python.exe process(es) instead:" -ForegroundColor Yellow
        $pythonProcs | Format-Table Id,ProcessName,StartTime,@{Label='Memory(MB)';Expression={$_.WS / 1MB -as [int]}} -AutoSize
        Write-Host "These may show windows! Should be using pythonw.exe." -ForegroundColor Yellow
    } else {
        Write-Host "No Python processes found at all." -ForegroundColor Red
    }
}

Write-Host "`nTask Status:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'AITrader-Loop' | Get-ScheduledTaskInfo |
    Select-Object LastRunTime,LastTaskResult,NextRunTime | Format-List

Write-Host "`nRecent log entries:" -ForegroundColor Cyan
$logFile = "logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log"
if (Test-Path $logFile) {
    Write-Host "Last 10 lines from $logFile" -ForegroundColor Gray
    Get-Content $logFile -Tail 10 -Encoding Unicode | ForEach-Object { "  $_" }
} else {
    Write-Host "Log file not found: $logFile" -ForegroundColor Yellow
}
