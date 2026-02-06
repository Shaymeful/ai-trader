# Update AITrader-Loop scheduled task to use runtime state interval

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -LogToFile'

Set-ScheduledTask -TaskName 'AITrader-Loop' -Action $action

Write-Host "Scheduled task updated successfully"
Write-Host "New arguments: $($action.Arguments)"
