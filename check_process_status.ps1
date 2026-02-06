# Check if specific processes are still running

$pids = @(308408, 308928)

foreach ($pid in $pids) {
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[OK] Process $pid ($($proc.ProcessName)) is running" -ForegroundColor Green
        Write-Host "     CPU: $([math]::Round($proc.CPU, 2))s  Memory: $($proc.WS / 1MB -as [int]) MB  Start: $($proc.StartTime)" -ForegroundColor Gray
    } else {
        Write-Host "[DEAD] Process $pid is not running" -ForegroundColor Red
    }
}

# Check if ANY ai-trader processes are running
Write-Host "`nAll ai-trader Python processes:" -ForegroundColor Cyan
Get-Process python*,pythonw* -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*ai-trader*" } |
    Format-Table Id,ProcessName,@{Label='CPU(s)';Expression={[math]::Round($_.CPU,2)}},@{Label='Mem(MB)';Expression={$_.WS / 1MB -as [int]}},StartTime -AutoSize
