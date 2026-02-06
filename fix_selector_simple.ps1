#Requires -RunAsAdministrator
$Task = Get-ScheduledTask -TaskName "AITrader-Selector"
$Task.Settings.Hidden = $true
$Task | Set-ScheduledTask

Write-Host "AITrader-Selector Hidden setting updated to: $($Task.Settings.Hidden)" -ForegroundColor Green

$Task2 = Get-ScheduledTask -TaskName "AITrader-Dashboard"
$Task2.Settings.Hidden = $true
$Task2 | Set-ScheduledTask

Write-Host "AITrader-Dashboard Hidden setting updated to: $($Task2.Settings.Hidden)" -ForegroundColor Green
