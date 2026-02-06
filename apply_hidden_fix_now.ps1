# Apply Hidden Task Fix - Run as Administrator
#Requires -RunAsAdministrator

$TaskName = "AITrader-Loop"
$TempXml = "$env:TEMP\$TaskName.xml"
$TempXmlHidden = "$env:TEMP\$TaskName-hidden.xml"

Write-Host "Applying Hidden setting to AITrader-Loop task..." -ForegroundColor Cyan
Write-Host ""

try {
    # Export current task
    Write-Host "1. Exporting current task..." -ForegroundColor Gray
    schtasks /Query /TN $TaskName /XML | Out-File -FilePath $TempXml -Encoding utf8

    # Modify Hidden setting
    Write-Host "2. Modifying Hidden setting to true..." -ForegroundColor Gray
    (Get-Content $TempXml) -replace '<Hidden>false</Hidden>', '<Hidden>true</Hidden>' |
        Set-Content $TempXmlHidden -Encoding UTF8

    # Delete old task
    Write-Host "3. Removing old task..." -ForegroundColor Gray
    schtasks /Delete /TN $TaskName /F | Out-Null

    # Create new task with Hidden=true
    Write-Host "4. Creating updated task..." -ForegroundColor Gray
    schtasks /Create /TN $TaskName /XML $TempXmlHidden /F | Out-Null

    Write-Host ""
    Write-Host "[SUCCESS] Task updated successfully!" -ForegroundColor Green
    Write-Host ""

    # Verify
    $Task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "Verification:" -ForegroundColor Cyan
    Write-Host "  Hidden: $($Task.Settings.Hidden)" -ForegroundColor Gray
    Write-Host "  Enabled: $($Task.Settings.Enabled)" -ForegroundColor Gray
    Write-Host "  Days: Monday-Friday (weekdays only)" -ForegroundColor Gray
    Write-Host ""

    if ($Task.Settings.Hidden) {
        Write-Host "[OK] Task will NOT show popups!" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Hidden setting may not have applied" -ForegroundColor Yellow
    }

    # Cleanup
    Remove-Item $TempXml -ErrorAction SilentlyContinue
    Remove-Item $TempXmlHidden -ErrorAction SilentlyContinue

} catch {
    Write-Host "[ERROR] Failed to update task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try running this script as Administrator:" -ForegroundColor Yellow
    Write-Host "  Right-click PowerShell -> Run as Administrator" -ForegroundColor Gray
    Write-Host "  Then run: .\apply_hidden_fix_now.ps1" -ForegroundColor Gray
    exit 1
}
