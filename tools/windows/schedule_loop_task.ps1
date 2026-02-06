# Schedule AI Trader Loop to Run During Market Hours
$TaskName = "AITrader-Loop-MarketHours"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $RepoRoot "tools\start_loop_market_hours.py"

Write-Host "============================================================"
Write-Host "AI Trader - Schedule Loop Task"
Write-Host "============================================================"
Write-Host ""
Write-Host "Task Name: $TaskName"
Write-Host "Python: $PythonExe"
Write-Host "Script: $ScriptPath"
Write-Host ""

# Remove existing task if exists
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "[!] Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Action: Run Python script
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ScriptPath `
    -WorkingDirectory $RepoRoot

# Trigger: Weekly on weekdays, with 15-minute repetition
$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At "6:00 AM" `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

# Add repetition pattern
$Trigger.Repetition = (New-ScheduledTaskTrigger `
    -Once `
    -At "6:00 AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Hours 18)).Repetition

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "AI Trader loop starter - runs during market hours on weekdays" `
    -Force | Out-Null

Write-Host "[OK] Task created successfully!"
Write-Host ""
Write-Host "Schedule:"
Write-Host "  Every 15 minutes on weekdays (Monday-Friday)"
Write-Host "  Starting at 6:00 AM, running until midnight"
Write-Host "  Script checks if market is open before starting loop"
Write-Host ""
Write-Host "To view: Open Task Scheduler (taskschd.msc)"
Write-Host "To test: Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
