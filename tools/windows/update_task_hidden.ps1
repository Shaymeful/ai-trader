#Requires -Version 5.1 -RunAsAdministrator
<#
.SYNOPSIS
    Update AITrader-Loop task to run hidden (no pop-ups).

.DESCRIPTION
    Updates the existing AITrader-Loop scheduled task to:
    1. Run hidden without showing windows
    2. Use the new start_loop_hidden.ps1 script
    3. Preserve all other settings (triggers, intervals, etc.)

.EXAMPLE
    .\update_task_hidden.ps1
    Update the task to run hidden
#>

$ErrorActionPreference = "Stop"

$TaskName = "AITrader-Loop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ScriptPath = Join-Path $RepoRoot "tools\windows\start_loop_hidden.ps1"

Write-Host "Updating AITrader-Loop task to run hidden..." -ForegroundColor Cyan
Write-Host ""

# Check if task exists
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $Task) {
    Write-Host "ERROR: Task '$TaskName' not found" -ForegroundColor Red
    Write-Host "Please create the task first using Task Scheduler" -ForegroundColor Yellow
    exit 1
}

Write-Host "Current task configuration:" -ForegroundColor Yellow
$Task.Actions | ForEach-Object {
    Write-Host "  Command: $($_.Execute)"
    Write-Host "  Arguments: $($_.Arguments)"
    Write-Host "  WorkingDir: $($_.WorkingDirectory)"
}
Write-Host ""

# Get current sleep seconds from arguments
$CurrentArgs = $Task.Actions[0].Arguments
if ($CurrentArgs -match '-SleepSeconds\s+(\d+)') {
    $SleepSeconds = $Matches[1]
} else {
    $SleepSeconds = 3600  # Default
}

# Build new action
$Action = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -Mode paper -SleepSeconds $SleepSeconds" `
    -WorkingDirectory $RepoRoot

# Update the task with new action
Set-ScheduledTask -TaskName $TaskName -Action $Action | Out-Null

Write-Host "✓ Task updated successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "New configuration:" -ForegroundColor Yellow
$UpdatedTask = Get-ScheduledTask -TaskName $TaskName
$UpdatedTask.Actions | ForEach-Object {
    Write-Host "  Command: $($_.Execute)"
    Write-Host "  Arguments: $($_.Arguments)"
    Write-Host "  WorkingDir: $($_.WorkingDirectory)"
}
Write-Host ""
Write-Host "The task will now run hidden without pop-up windows." -ForegroundColor Green
Write-Host ""
Write-Host "To test, run:" -ForegroundColor Cyan
Write-Host "  schtasks /Run /TN '$TaskName'" -ForegroundColor Gray
