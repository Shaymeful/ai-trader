# Check if dashboard is running

Write-Host "Checking for dashboard process..." -ForegroundColor Cyan

$dashboardProcs = Get-Process python*,pythonw* -ErrorAction SilentlyContinue | Where-Object {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmdLine -like "*ui_api*" -or $cmdLine -like "*app.py*" -or $cmdLine -like "*8001*"
}

if ($dashboardProcs) {
    Write-Host "Found dashboard process(es):" -ForegroundColor Green
    $dashboardProcs | Format-Table Id,ProcessName,StartTime -AutoSize
} else {
    Write-Host "Dashboard is NOT running" -ForegroundColor Red
    Write-Host ""
    Write-Host "To start dashboard:" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\python.exe src\ui_api\app.py" -ForegroundColor Gray
}

# Check if port 8001 is listening
Write-Host ""
Write-Host "Checking port 8001..." -ForegroundColor Cyan
$port8001 = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
if ($port8001) {
    Write-Host "Port 8001 is open - Dashboard should be accessible at http://localhost:8001" -ForegroundColor Green
} else {
    Write-Host "Port 8001 is not listening - Dashboard is not running" -ForegroundColor Red
}
