# Test runtime endpoint
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/runtime" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "SUCCESS: Runtime endpoint is working"
    Write-Host ""
    Write-Host "Loop Interval: $($response.loop_interval_seconds) seconds"
    Write-Host "Last Loop Start: $($response.last_loop_start)"
    Write-Host "Last Loop End: $($response.last_loop_end)"
    Write-Host "Next Loop At: $($response.next_loop_at)"
    Write-Host "Seconds Until Next: $($response.seconds_until_next_loop)"
} catch {
    Write-Host "ERROR: Failed to call /runtime endpoint"
    Write-Host "Error: $_"
    Write-Host ""
    Write-Host "Testing /health endpoint..."
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
        Write-Host "Health endpoint is working: $($health.status)"
    } catch {
        Write-Host "Health endpoint also failed: $_"
    }
}
