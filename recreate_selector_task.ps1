#Requires -RunAsAdministrator
# Recreate AITrader-Selector task with proper weekday scheduling

$ErrorActionPreference = "Stop"

$TaskName = "AITrader-Selector"
$RepoRoot = "C:\dev\ai-trader"

Write-Host "Recreating AITrader-Selector task..." -ForegroundColor Cyan
Write-Host ""

try {
    # Remove if exists
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # Create action with -WindowStyle Hidden
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RepoRoot\tools\windows\run_selector.ps1`" -LogToFile" `
        -WorkingDirectory $RepoRoot

    # Create multiple triggers for weekdays (workaround for DaysOfWeek issue)
    # Trigger: Weekdays at 8:50 AM, repeat every 15 min for 7.5 hours
    $Trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "8:50AM"
    $Trigger1.Repetition = $(New-ScheduledTaskTrigger -Once -At "8:50AM" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Hours 7.5)).Repetition

    $Trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At "8:50AM"
    $Trigger2.Repetition = $Trigger1.Repetition

    $Trigger3 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At "8:50AM"
    $Trigger3.Repetition = $Trigger1.Repetition

    $Trigger4 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At "8:50AM"
    $Trigger4.Repetition = $Trigger1.Repetition

    $Trigger5 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "8:50AM"
    $Trigger5.Repetition = $Trigger1.Repetition

    # Create settings with Hidden=true
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -Hidden

    # Create principal
    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive

    # Register task with all triggers
    $Task = New-ScheduledTask -Action $Action -Trigger @($Trigger1, $Trigger2, $Trigger3, $Trigger4, $Trigger5) -Settings $Settings -Principal $Principal
    Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

    Write-Host "[SUCCESS] Task recreated!" -ForegroundColor Green
    Write-Host ""

    # Verify
    $VerifyTask = Get-ScheduledTask -TaskName $TaskName
    $VerifyAction = $VerifyTask.Actions[0]
    $HasWindowStyle = $VerifyAction.Arguments -match '-WindowStyle Hidden'

    Write-Host "Verification:" -ForegroundColor Cyan
    Write-Host "  Hidden: $($VerifyTask.Settings.Hidden)" -ForegroundColor Gray
    Write-Host "  WindowStyle Hidden: $HasWindowStyle" -ForegroundColor Gray
    Write-Host "  Triggers: $($VerifyTask.Triggers.Count) (Mon-Fri)" -ForegroundColor Gray
    Write-Host "  Repetition: Every 15 min for 7.5 hours" -ForegroundColor Gray
    Write-Host ""

    if ($VerifyTask.Settings.Hidden -and $HasWindowStyle) {
        Write-Host "[OK] No popups should appear!" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Task may still show popups" -ForegroundColor Yellow
    }

} catch {
    Write-Host "[ERROR] Failed to create task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Stack trace:" -ForegroundColor Gray
    Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    exit 1
}
