# Update AITrader-Loop task using PowerShell cmdlets
# This uses a different method than schtasks

Write-Host "Updating AITrader-Loop task using PowerShell cmdlets..." -ForegroundColor Cyan
Write-Host ""

try {
    # Get the existing task
    $Task = Get-ScheduledTask -TaskName "AITrader-Loop"

    # Create new action with updated parameters
    $Action = New-ScheduledTaskAction `
        -Execute "PowerShell.exe" `
        -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -SleepSeconds 300 -LogToFile' `
        -WorkingDirectory "C:\dev\ai-trader"

    # Update the task with the new action
    Set-ScheduledTask -TaskName "AITrader-Loop" -Action $Action

    Write-Host "SUCCESS: Task updated!" -ForegroundColor Green
    Write-Host ""

    # Verify the update
    $UpdatedTask = Get-ScheduledTask -TaskName "AITrader-Loop"
    Write-Host "New task arguments:" -ForegroundColor Yellow
    Write-Host $UpdatedTask.Actions.Arguments -ForegroundColor Gray
    Write-Host ""

    # Check for required flags
    $Args = $UpdatedTask.Actions.Arguments
    $HasHidden = $Args -match "-WindowStyle Hidden"
    $Has5Min = $Args -match "SleepSeconds 300"

    if ($HasHidden -and $Has5Min) {
        Write-Host "Verification: All settings correct!" -ForegroundColor Green
        Write-Host ""

        # Kill old processes
        Write-Host "Stopping old loop processes..." -ForegroundColor Yellow
        Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 1

        # Start the updated task
        Write-Host "Starting updated loop..." -ForegroundColor Yellow
        Start-ScheduledTask -TaskName "AITrader-Loop"
        Start-Sleep -Seconds 3

        # Check if it's running
        $RunningPython = Get-Process -Name python -ErrorAction SilentlyContinue
        if ($RunningPython) {
            Write-Host ""
            Write-Host "SUCCESS: Loop is running!" -ForegroundColor Green
            Write-Host "PID(s): $($RunningPython.Id -join ', ')" -ForegroundColor Gray
        } else {
            Write-Host ""
            Write-Host "WARNING: Loop may not have started. Check logs." -ForegroundColor Yellow
        }

    } else {
        Write-Host "WARNING: Some settings may not have updated correctly" -ForegroundColor Yellow
    }

} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure you're running this as Administrator!" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press Enter to close..."
Read-Host
