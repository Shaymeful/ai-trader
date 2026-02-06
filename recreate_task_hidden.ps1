#Requires -RunAsAdministrator
# Recreate AITrader-Loop task with Hidden=true

$ErrorActionPreference = "Stop"

$TaskName = "AITrader-Loop"
$RepoRoot = "C:\dev\ai-trader"
$Mode = "paper"
$SleepSeconds = 600

Write-Host "Recreating AITrader-Loop task with Hidden=true..." -ForegroundColor Cyan
Write-Host ""

try {
    # Remove any existing task
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Existing) {
        Write-Host "Removing existing task..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Create action
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RepoRoot\tools\windows\start_loop.ps1`" -Mode $Mode -SleepSeconds $SleepSeconds -LogToFile" `
        -WorkingDirectory $RepoRoot

    # Create trigger (weekdays at 9:30 AM)
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At "9:30AM"

    # Create settings with Hidden=true
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 7) `
        -Priority 7 `
        -Hidden

    # Create principal (run as current user)
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    # Register task
    Write-Host "Registering task..." -ForegroundColor Gray
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "AI Trader loop runner - Runs during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)" `
        | Out-Null

    Write-Host ""
    Write-Host "[SUCCESS] Task created successfully!" -ForegroundColor Green
    Write-Host ""

    # Verify
    $Task = Get-ScheduledTask -TaskName $TaskName
    $TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName

    Write-Host "Task Configuration:" -ForegroundColor Cyan
    Write-Host "  Name: $($Task.TaskName)" -ForegroundColor Gray
    Write-Host "  Hidden: $($Task.Settings.Hidden)" -ForegroundColor Gray
    Write-Host "  Enabled: $($Task.Settings.Enabled)" -ForegroundColor Gray
    Write-Host "  Days: Monday-Friday (weekdays only)" -ForegroundColor Gray
    Write-Host "  Start Time: 9:30 AM ET" -ForegroundColor Gray
    Write-Host "  Next Run: $($TaskInfo.NextRunTime)" -ForegroundColor Gray
    Write-Host ""

    if ($Task.Settings.Hidden) {
        Write-Host "[OK] Task is HIDDEN - No popups will appear!" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Hidden setting not applied correctly" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Weekend protection is also active (script exits on Sat/Sun)" -ForegroundColor Cyan

} catch {
    Write-Host "[ERROR] Failed to create task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Stack trace:" -ForegroundColor Gray
    Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    exit 1
}
