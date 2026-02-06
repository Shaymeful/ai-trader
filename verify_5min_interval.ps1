# Verify 5-minute interval is active

Write-Host "================================================"
Write-Host "Verifying 5-Minute Loop Interval"
Write-Host "================================================"
Write-Host ""

# Check runtime.json
$runtimeJson = Get-Content "state\runtime.json" | ConvertFrom-Json

Write-Host "✅ Runtime State:" -ForegroundColor Green
Write-Host "   Interval: $($runtimeJson.loop_interval_seconds) seconds ($($runtimeJson.loop_interval_seconds / 60) minutes)"

$lastLoop = [datetime]::Parse($runtimeJson.last_loop_start)
$nextLoop = [datetime]::Parse($runtimeJson.next_loop_at)
$now = Get-Date

Write-Host "   Last Loop: $($lastLoop.ToLocalTime().ToString('HH:mm:ss'))"
Write-Host "   Next Loop: $($nextLoop.ToLocalTime().ToString('HH:mm:ss'))"

$secondsUntil = [int](($nextLoop - $now).TotalSeconds)
Write-Host "   Countdown: $secondsUntil seconds" -ForegroundColor Cyan

# Check process
$pid = Get-Content "logs\loop_5min.pid" -ErrorAction SilentlyContinue
if ($pid) {
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host ""
        Write-Host "✅ Loop Process Running:" -ForegroundColor Green
        Write-Host "   PID: $pid"
        Write-Host "   Running time: $(((Get-Date) - $process.StartTime).ToString('hh\:mm\:ss'))"
    } else {
        Write-Host ""
        Write-Host "❌ Loop process not found (PID: $pid)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "================================================"

if ($runtimeJson.loop_interval_seconds -eq 300) {
    Write-Host "✅ SUCCESS: Loop is running every 5 minutes!" -ForegroundColor Green
} else {
    Write-Host "❌ FAILED: Loop interval is $($runtimeJson.loop_interval_seconds)s, not 300s" -ForegroundColor Red
}

Write-Host "================================================"
