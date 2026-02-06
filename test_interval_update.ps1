$body = @{loop_interval_seconds=300} | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/runtime/loop_interval -Method POST -Body $body -ContentType 'application/json' | ConvertTo-Json
