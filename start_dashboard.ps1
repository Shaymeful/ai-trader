# Start Dashboard
$RepoRoot = "C:\dev\ai-trader"
Set-Location $RepoRoot

Write-Host "Starting AI Trader Dashboard..." -ForegroundColor Cyan
Write-Host "URL: http://localhost:8001" -ForegroundColor Green
Write-Host ""

$LogFile = "logs\dashboard_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "src.ui_api.app:app", "--host", "0.0.0.0", "--port", "8001" `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "$LogFile.err" `
    -NoNewWindow `
    -PassThru

Write-Host "Dashboard started! Check $LogFile for output"
Write-Host "Access at: http://localhost:8001"
