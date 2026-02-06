# Check when next iteration will run

$runtime = Get-Content "state\runtime.json" | ConvertFrom-Json
$nextLoop = [datetime]::Parse($runtime.next_loop_at)
$now = Get-Date
$secondsUntil = [int](($nextLoop - $now).TotalSeconds)

Write-Host "Next Iteration Check"
Write-Host "===================="
Write-Host "Current time: $($now.ToString('HH:mm:ss'))"
Write-Host "Next loop at: $($nextLoop.ToLocalTime().ToString('HH:mm:ss'))"
Write-Host "Seconds until next iteration: $secondsUntil"
Write-Host ""
Write-Host "Current interval in state: $($runtime.loop_interval_seconds) seconds"
Write-Host ""

if ($secondsUntil -gt 0) {
    Write-Host "Waiting for iteration to start..." -ForegroundColor Yellow
} else {
    Write-Host "Iteration should have started!" -ForegroundColor Green
}
