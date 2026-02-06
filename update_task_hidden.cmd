@echo off
REM Update AITrader-Loop to run hidden with market hours check
REM Right-click this file and select "Run as administrator"

echo ================================================================================
echo Updating AITrader-Loop Task
echo ================================================================================
echo.

schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 300 -LogToFile"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo SUCCESS: Task updated!
    echo ================================================================================
    echo.
    echo New settings:
    echo   - Runs HIDDEN ^(no pop-up windows^)
    echo   - Checks every 5 MINUTES
    echo   - Only runs during MARKET HOURS ^(Mon-Fri 9:30 AM - 4:00 PM ET^)
    echo.
    echo To start the loop now, run:
    echo   schtasks /Run /TN "AITrader-Loop"
    echo.
    echo Or press any key to start it now...
    pause
    schtasks /Run /TN "AITrader-Loop"
    echo.
    echo Loop started! Check logs at: logs\loop_status.log
) else (
    echo.
    echo ================================================================================
    echo ERROR: Failed to update task
    echo ================================================================================
    echo.
    echo Make sure you ran this as Administrator:
    echo   Right-click update_task_hidden.cmd ^> Run as administrator
    echo.
)

echo.
pause
