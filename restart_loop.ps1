# Kill old loop processes
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.StartTime -and $_.StartTime -lt (Get-Date).AddHours(-1)
} | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "Killed old processes"
Start-Sleep -Seconds 5

# Start fresh loop
schtasks /run /tn "AITrader-Loop"
Write-Host "Started fresh loop"
Start-Sleep -Seconds 30

# Check results
Write-Host "`nChecking universe_active.json:"
Get-Content "out\universe_active.json" | ConvertFrom-Json | Select-Object -ExpandProperty symbols | Measure-Object | Select-Object -ExpandProperty Count
Write-Host "symbols loaded"

Write-Host "`nRecent log entries:"
Get-Content "logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log" -Tail 50 | Select-String -Pattern "Created sector|energy|EOSE|Universe:"
