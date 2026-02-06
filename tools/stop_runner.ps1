# Stop all running AI Trader runner instances
Write-Host "Stopping AI Trader runner instances..." -ForegroundColor Yellow
Write-Host ""

# Find and stop python processes running runner
$runnerProcesses = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        $cmdLine -like '*runner*' -or $cmdLine -like '*src.app.runner*'
    } catch {
        $false
    }
}

if ($runnerProcesses) {
    Write-Host "Found $($runnerProcesses.Count) runner process(es):" -ForegroundColor Cyan
    foreach ($proc in $runnerProcesses) {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        Write-Host "  PID $($proc.Id): $($cmdLine.Substring(0, [Math]::Min(80, $cmdLine.Length)))..." -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "Stopping processes..." -ForegroundColor Yellow

    foreach ($proc in $runnerProcesses) {
        try {
            Stop-Process -Id $proc.Id -Force
            Write-Host "  Stopped PID $($proc.Id)" -ForegroundColor Green
        } catch {
            Write-Host "  Failed to stop PID $($proc.Id): $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No runner processes found" -ForegroundColor Green
}

Write-Host ""

# Remove lock file if it exists
$lockFile = "logs\paper_dryrun.lock"
if (Test-Path $lockFile) {
    try {
        Remove-Item $lockFile -Force -ErrorAction Stop
        Write-Host "Removed lock file: $lockFile" -ForegroundColor Green
    } catch {
        Write-Host "Could not remove lock file (process may still be holding it): $_" -ForegroundColor Yellow
        Write-Host "Lock file will be cleaned up when process exits" -ForegroundColor Yellow
    }
} else {
    Write-Host "Lock file not found (already clean)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done! You can now run the runner." -ForegroundColor Green
