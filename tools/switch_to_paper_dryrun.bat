@echo off
REM AI Trader - Switch to Paper Mode with Dry-Run
REM Right-click this file and select "Run as administrator"

echo.
echo ================================================================================
echo   AI Trader - Switch to Paper Mode with Dry-Run
echo ================================================================================
echo.
echo This will:
echo   1. Remove the current scheduled task (if exists)
echo   2. Create a new task configured for paper mode with dry-run
echo   3. Start the task immediately
echo.
echo IMPORTANT: This window must be running as Administrator!
echo.
echo Press any key to continue, or close this window to cancel...
pause >nul

cd /d "%~dp0\.."

echo.
echo Step 1: Removing old task...
echo.

PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0\setup_task_scheduler.ps1" -Remove

if %ERRORLEVEL% EQU 0 (
    echo [OK] Old task removed successfully
) else (
    echo [WARNING] Task may not exist or removal failed - continuing anyway
)

echo.
echo Step 2: Creating new task with paper mode + dry-run...
echo.

PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0\setup_task_scheduler.ps1" -Mode paper -DryRun

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task created successfully!
    echo.
    echo Step 3: Starting task...
    echo.

    PowerShell.exe -Command "Start-ScheduledTask -TaskName 'AI-Trader-Hourly'"

    echo.
    echo ================================================================================
    echo   Setup Complete!
    echo ================================================================================
    echo.
    echo Task: AI-Trader-Hourly
    echo Mode: paper
    echo Dry-Run: True (orders printed but NOT placed)
    echo.
    echo To verify it's working:
    echo   PowerShell:  Get-Content logs\loop_status.log -Tail 10 -Wait
    echo   Command:     tail -f logs\loop_status.log
    echo.
    echo Expected log format:
    echo   [timestamp] SUCCESS ^| mode=paper ^| dry_run=True ^| orders_placed=7 ^| ...
    echo.
) else (
    echo.
    echo ================================================================================
    echo   Setup Failed
    echo ================================================================================
    echo.
    echo Please check the error messages above and try again.
    echo.
)

echo Press any key to exit...
pause >nul
