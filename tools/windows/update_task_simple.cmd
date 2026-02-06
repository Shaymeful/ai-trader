@echo off
REM Update AITrader-Loop task to run hidden
REM Run this as Administrator

echo Updating AITrader-Loop task to run hidden...
echo.

schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 300 -LogToFile"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: Task updated to run hidden with 5-minute intervals
    echo.
    echo The loop will now:
    echo   1. Run hidden without pop-up windows
    echo   2. Check every 5 minutes during market hours
    echo   3. Skip iterations when market is closed
    echo.
) else (
    echo.
    echo ERROR: Failed to update task. Make sure to run as Administrator.
    echo.
    pause
    exit /b 1
)

echo To start the loop now, run:
echo   schtasks /Run /TN "AITrader-Loop"
echo.
pause
