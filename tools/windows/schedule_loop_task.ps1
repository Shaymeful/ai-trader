# Schedule AI Trader Loop to Run During Market Hours
# This script creates a Windows Task Scheduler task that runs the loop starter
# every 15 minutes on weekdays. The loop starter checks if market is open.

$TaskName = "AITrader-Loop-MarketHours"
$ScriptPath = Join-Path $PSScriptRoot "..\start_loop_market_hours.py"
$RepoRoot = Join-Path $PSScriptRoot "..\..\" | Resolve-Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $RepoRoot "logs\scheduler"

# Create log directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "=" * 60
Write-Host "AI Trader - Schedule Loop Task"
Write-Host "=" * 60
Write-Host ""
Write-Host "This will create a Windows Task Scheduler task that:"
Write-Host "  1. Runs every 15 minutes on weekdays (Monday-Friday)"
Write-Host "  2. Checks if market is open (9:30 AM - 4:00 PM ET)"
Write-Host "  3. Starts the loop if not already running"
Write-Host ""
Write-Host "Task Name: $TaskName"
Write-Host "Script: $ScriptPath"
Write-Host "Python: $PythonExe"
Write-Host ""

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "⚠ Task already exists!"
    $Response = Read-Host "Do you want to replace it? (y/N)"
    if ($Response -ne 'y' -and $Response -ne 'Y') {
        Write-Host "Cancelled."
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task."
}

# Create the scheduled task
Write-Host ""
Write-Host "Creating scheduled task..."

# Action: Run Python script
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "$ScriptPath" `
    -WorkingDirectory $RepoRoot

# Trigger: Every 15 minutes on weekdays
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At "6:00 AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 1) `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

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
    -User $env:USERNAME `
    -RunLevel Highest

Write-Host "✓ Task created successfully!"
Write-Host ""
Write-Host "Task Details:"
Write-Host "  Schedule: Every 15 minutes, Monday-Friday, 6:00 AM - 11:59 PM"
Write-Host "  The script will check market hours and only start loop if open"
Write-Host ""
Write-Host "To view the task:"
Write-Host "  taskschd.msc  (Task Scheduler)"
Write-Host "  Look for: $TaskName"
Write-Host ""
Write-Host "To manually run the task:"
Write-Host "  schtasks /run /tn `"$TaskName`""
Write-Host ""
Write-Host "To disable the task:"
Write-Host "  schtasks /change /tn `"$TaskName`" /disable"
Write-Host ""
Write-Host "To remove the task:"
Write-Host "  schtasks /delete /tn `"$TaskName`" /f"
Write-Host ""
