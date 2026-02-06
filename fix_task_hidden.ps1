#Requires -RunAsAdministrator

$TaskName = "AITrader-Loop"

Write-Host "Making AITrader-Loop task hidden..." -ForegroundColor Cyan

# Export current task
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop

# Get the settings
$Settings = $Task.Settings
$Settings.Hidden = $true

# Update the task with new settings
Set-ScheduledTask -TaskName $TaskName -Settings $Settings

Write-Host "Task is now hidden!" -ForegroundColor Green
Write-Host ""

# Verify
$UpdatedTask = Get-ScheduledTask -TaskName $TaskName
Write-Host "Hidden setting: $($UpdatedTask.Settings.Hidden)" -ForegroundColor Gray

if ($UpdatedTask.Settings.Hidden) {
    Write-Host "[OK] Task will not show popups" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Hidden setting did not apply" -ForegroundColor Red
}
