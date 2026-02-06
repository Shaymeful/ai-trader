# Fix AITrader-Loop Task to Run Completely Hidden
# Must be run as Administrator

$ErrorActionPreference = "Stop"

Write-Host "Configuring AITrader-Loop task for hidden mode..." -ForegroundColor Cyan

# Get the task
$task = Get-ScheduledTask -TaskName "AITrader-Loop" -ErrorAction SilentlyContinue

if (-not $task) {
    Write-Host "ERROR: AITrader-Loop task not found!" -ForegroundColor Red
    exit 1
}

# Update settings to run hidden
$task.Settings.Hidden = $true
$task.Settings.Priority = 4  # Normal priority

# Update the task
$task | Set-ScheduledTask

Write-Host "✓ Task configured to run hidden" -ForegroundColor Green

# Verify the configuration
$task = Get-ScheduledTask -TaskName "AITrader-Loop"
Write-Host "`nTask Configuration:" -ForegroundColor Yellow
Write-Host "  Hidden: $($task.Settings.Hidden)"
Write-Host "  State: $($task.State)"
Write-Host "  Action: $($task.Actions[0].Execute) $($task.Actions[0].Arguments)"

Write-Host "`nTask is now configured to run hidden." -ForegroundColor Green
Write-Host "To restart the task with new settings:" -ForegroundColor Cyan
Write-Host "  schtasks /End /TN `"AITrader-Loop`""
Write-Host "  schtasks /Run /TN `"AITrader-Loop`""
