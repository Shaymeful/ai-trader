# Restart both dashboard and loop with new code

Write-Host "Stopping all Python processes..."
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

Write-Host "Starting dashboard..."
schtasks /run /tn "AITrader-Dashboard"
Start-Sleep -Seconds 10

Write-Host "Starting loop..."
schtasks /run /tn "AITrader-Loop"
Start-Sleep -Seconds 30

Write-Host "`n=== Checking Results ===`n"

Write-Host "Dashboard sectors status:"
$result = Invoke-RestMethod -Uri "http://localhost:8000/universe/sectors"
$result.sectors | ForEach-Object {
    Write-Host "  $($_.sector_name): enabled=$($_.enabled), symbols=$($_.symbol_count)"
}

Write-Host "`nTotal symbols: $($result.total_symbols)"

Write-Host "`nLoop log (last 30 lines):"
Get-Content "logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log" -Tail 30 | Select-String -Pattern "Universe:|Created sector|energy|EOSE" | ForEach-Object { Write-Host "  $_" }
