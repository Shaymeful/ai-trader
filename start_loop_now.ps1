# Start AI Trader Loop
$logFile = "logs\loop_restart_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "-m", "src.app.runner", "--mode", "paper", "--loop", "--sleep-seconds", "660" `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError "$logFile.err" `
    -NoNewWindow `
    -PassThru

Write-Host "Loop started. Check $logFile for output."
