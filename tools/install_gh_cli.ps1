# GitHub CLI Installation Script
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  Installing GitHub CLI" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Downloading GitHub CLI installer..." -ForegroundColor Yellow
$ProgressPreference = 'SilentlyContinue'
$url = "https://github.com/cli/cli/releases/latest/download/gh_windows_amd64.msi"
$output = Join-Path $env:TEMP "gh_windows_amd64.msi"

try {
    Invoke-WebRequest -Uri $url -OutFile $output
    Write-Host "Download complete!" -ForegroundColor Green
    Write-Host ""

    Write-Host "Installing GitHub CLI..." -ForegroundColor Yellow
    Start-Process msiexec.exe -ArgumentList "/i", $output, "/quiet", "/norestart" -Wait

    Write-Host ""
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host "  Installation Complete!" -ForegroundColor Green
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "NOTE: You need to restart your terminal for 'gh' to be available in PATH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Close and reopen this terminal" -ForegroundColor White
    Write-Host "2. Run: gh auth login" -ForegroundColor White
    Write-Host "3. Run: gh pr create --title 'Fix fractional orders and add cancel-open-orders preflight' --body-file PR_DESCRIPTION.md" -ForegroundColor White
    Write-Host ""

} catch {
    Write-Host "ERROR: Failed to install GitHub CLI" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
