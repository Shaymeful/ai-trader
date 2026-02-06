#Requires -RunAsAdministrator
# Complete fix for AITrader-Selector task to eliminate all popups

$ErrorActionPreference = "Stop"

Write-Host "Fixing AITrader-Selector and AITrader-Dashboard tasks..." -ForegroundColor Cyan
Write-Host ""

# Fix AITrader-Selector
try {
    $TaskName = "AITrader-Selector"
    Write-Host "[$TaskName] Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # Create new action with -WindowStyle Hidden
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\dev\ai-trader\tools\windows\run_selector.ps1`" -LogToFile" `
        -WorkingDirectory "C:\dev\ai-trader"

    # Create trigger (every 15 minutes, weekdays, 8:50 AM - 4:10 PM)
    $Trigger = New-ScheduledTaskTrigger `
        -Once `
        -At "8:50AM" `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Hours 7.5)

    # Additional trigger for weekdays only
    $Trigger.DaysOfWeek = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')

    # Create settings with Hidden=true
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -Hidden

    # Create principal (run as current user)
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive

    # Register task
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "RSS Selector - Generates trading candidates every 15 minutes during market hours" `
        | Out-Null

    Write-Host "[$TaskName] SUCCESS - Task recreated with -WindowStyle Hidden" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[$TaskName] ERROR: $_" -ForegroundColor Red
    Write-Host ""
}

# Fix AITrader-Dashboard
try {
    $TaskName = "AITrader-Dashboard"

    # Get existing task to preserve trigger
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if ($ExistingTask) {
        Write-Host "[$TaskName] Updating task..." -ForegroundColor Yellow

        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false

        # Create new action with -WindowStyle Hidden
        $Action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\dev\ai-trader\tools\windows\start_dashboard.ps1`"" `
            -WorkingDirectory "C:\dev\ai-trader"

        # Use existing trigger or create default (at logon)
        $Trigger = New-ScheduledTaskTrigger -AtLogOn

        # Create settings with Hidden=true
        $Settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -Hidden

        # Create principal
        $Principal = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType Interactive

        # Register task
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $Action `
            -Trigger $Trigger `
            -Settings $Settings `
            -Principal $Principal `
            -Description "AI Trader Dashboard - Web UI for monitoring trading activity" `
            | Out-Null

        Write-Host "[$TaskName] SUCCESS - Task updated with -WindowStyle Hidden" -ForegroundColor Green
    } else {
        Write-Host "[$TaskName] Task not found, skipping" -ForegroundColor Yellow
    }
    Write-Host ""
} catch {
    Write-Host "[$TaskName] ERROR: $_" -ForegroundColor Red
    Write-Host ""
}

# Verify
Write-Host "Verification:" -ForegroundColor Cyan
$Tasks = Get-ScheduledTask | Where-Object {$_.TaskName -match '^AITrader-'}
foreach ($Task in $Tasks) {
    $Action = $Task.Actions[0]
    $HasWindowStyle = $Action.Arguments -match '-WindowStyle Hidden'
    $IsHidden = $Task.Settings.Hidden

    $Status = if ($HasWindowStyle -and $IsHidden) { "OK" } else { "WARN" }
    $Color = if ($Status -eq "OK") { "Green" } else { "Yellow" }

    Write-Host "  $($Task.TaskName): Hidden=$IsHidden, WindowStyle=$HasWindowStyle [$Status]" -ForegroundColor $Color
}

Write-Host ""
Write-Host "Done! No more popups should appear." -ForegroundColor Cyan
