@echo off
REM AI Trader - Task Scheduler Setup (Run as Administrator)
REM Right-click this file and select "Run as administrator"

echo.
echo ================================================================================
echo   AI Trader - Task Scheduler Setup
echo ================================================================================
echo.
echo This script will set up the AI Trader to run automatically every hour.
echo.
echo IMPORTANT: This window must be running as Administrator!
echo.
echo Press any key to continue, or close this window to cancel...
pause >nul

cd /d "%~dp0\.."

echo.
echo Running setup script...
echo.

PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0\setup_task_scheduler.ps1"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo   Setup completed successfully!
    echo ================================================================================
    echo.
    echo To test the task, run these commands in PowerShell:
    echo   Start-ScheduledTask -TaskName "AI-Trader-Hourly"
    echo   Get-Content logs\loop_status.log -Tail 10 -Wait
    echo.
) else (
    echo.
    echo ================================================================================
    echo   Setup failed or was cancelled
    echo ================================================================================
    echo.
)

echo Press any key to exit...
pause >nul
