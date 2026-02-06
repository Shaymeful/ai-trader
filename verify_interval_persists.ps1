# Verify that interval change persists after iteration

Write-Host "Verifying Loop Interval Persistence"
Write-Host "====================================="
Write-Host ""

$runtime = Get-Content "state\runtime.json" | ConvertFrom-Json

Write-Host "Runtime State:"
Write-Host "  Loop Interval: $($runtime.loop_interval_seconds) seconds ($($runtime.loop_interval_seconds / 60) minutes)"
Write-Host "  Last Loop Start: $([datetime]::Parse($runtime.last_loop_start).ToLocalTime().ToString('HH:mm:ss'))"
Write-Host "  Last Loop End: $([datetime]::Parse($runtime.last_loop_end).ToLocalTime().ToString('HH:mm:ss'))"
Write-Host "  Next Loop At: $([datetime]::Parse($runtime.next_loop_at).ToLocalTime().ToString('HH:mm:ss'))"
Write-Host ""

# Calculate actual interval used
$lastStart = [datetime]::Parse($runtime.last_loop_start)
$lastEnd = [datetime]::Parse($runtime.last_loop_end)
$nextLoop = [datetime]::Parse($runtime.next_loop_at)

$actualInterval = [int](($nextLoop - $lastEnd).TotalSeconds)

Write-Host "Actual interval used: $actualInterval seconds ($($actualInterval / 60) minutes)"
Write-Host ""

Write-Host "====================================="
if ($runtime.loop_interval_seconds -eq 600 -and $actualInterval -eq 600) {
    Write-Host "SUCCESS: Interval persisted correctly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The loop is now using a 10-minute interval."
    Write-Host "UI interval changes will persist across iterations."
} elseif ($runtime.loop_interval_seconds -eq 600 -and $actualInterval -eq 300) {
    Write-Host "PARTIAL: State shows 600s but used 300s" -ForegroundColor Yellow
    Write-Host "This may be normal if iteration started before change."
} elseif ($runtime.loop_interval_seconds -eq 300) {
    Write-Host "FAILED: Interval reverted to 300s" -ForegroundColor Red
    Write-Host "The fix did not work correctly."
} else {
    Write-Host "UNEXPECTED: State shows $($runtime.loop_interval_seconds)s" -ForegroundColor Yellow
}
Write-Host "====================================="
