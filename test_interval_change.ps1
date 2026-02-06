# Test changing loop interval via API

Write-Host "Testing Loop Interval Change via API"
Write-Host "======================================"
Write-Host ""

# Step 1: Get current interval
Write-Host "[1] Current interval:"
$current = Invoke-RestMethod -Uri "http://localhost:8000/runtime"
Write-Host "    $($current.loop_interval_seconds) seconds ($($current.loop_interval_seconds / 60) minutes)"
Write-Host ""

# Step 2: Change to 10 minutes (600 seconds)
Write-Host "[2] Changing interval to 10 minutes (600 seconds)..."
$body = @{loop_interval_seconds=600} | ConvertTo-Json
$response = Invoke-RestMethod -Uri "http://localhost:8000/runtime/loop_interval" -Method POST -Body $body -ContentType "application/json"
Write-Host "    Response: $($response.message)"
Write-Host ""

# Step 3: Wait 2 seconds
Write-Host "[3] Waiting 2 seconds..."
Start-Sleep -Seconds 2
Write-Host ""

# Step 4: Verify change in API
Write-Host "[4] Verifying via API:"
$updated = Invoke-RestMethod -Uri "http://localhost:8000/runtime"
Write-Host "    $($updated.loop_interval_seconds) seconds ($($updated.loop_interval_seconds / 60) minutes)"
Write-Host ""

# Step 5: Verify change in file
Write-Host "[5] Verifying in runtime.json:"
$file = Get-Content "state\runtime.json" | ConvertFrom-Json
Write-Host "    $($file.loop_interval_seconds) seconds ($($file.loop_interval_seconds / 60) minutes)"
Write-Host ""

# Step 6: Result
Write-Host "======================================"
if ($updated.loop_interval_seconds -eq 600 -and $file.loop_interval_seconds -eq 600) {
    Write-Host "SUCCESS: Interval changed to 600 seconds!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next step: Wait for the loop to complete current sleep"
    Write-Host "and verify it uses the new 600-second interval."
} else {
    Write-Host "FAILED: Interval not updated correctly" -ForegroundColor Red
    Write-Host "  API: $($updated.loop_interval_seconds)"
    Write-Host "  File: $($file.loop_interval_seconds)"
}
Write-Host "======================================"
