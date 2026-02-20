# Disable old AITrader-Loop task (run as Administrator)

Write-Host "Disabling old AITrader-Loop task..." -ForegroundColor Cyan

try {
    Disable-ScheduledTask -TaskName "AITrader-Loop" -ErrorAction Stop
    Write-Host "[OK] Task disabled successfully!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to disable task: $_" -ForegroundColor Red
    Write-Host "Make sure to run this script as Administrator" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Current task states:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "*AITrader*" | Select-Object TaskName, State | Format-Table -AutoSize

Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  - AITrader-Loop: DISABLED (old task without market hours check)" -ForegroundColor Gray
Write-Host "  - AITrader-Loop-MarketHours: ACTIVE (smart task, only runs during market hours)" -ForegroundColor Green
