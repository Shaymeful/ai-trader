@echo off
echo ================================================================
echo AI Trader - Revert to DRY-RUN Mode
echo ================================================================
echo.
echo This will revert to DRY-RUN mode (simulated trades only).
echo No real orders will be placed on Alpaca.
echo.
echo This script requires Administrator privileges.
echo Right-click and select "Run as administrator"
echo.
pause

echo.
echo Stopping current loop task...
schtasks /End /TN AITrader-Loop

echo.
echo Updating AITrader-Loop task to DRY-RUN mode...
schtasks /Create /TN AITrader-Loop /XML "%~dp0AITrader-Loop.xml" /F

if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: AITrader-Loop task reverted to DRY-RUN mode.
    echo.
    echo Starting updated task...
    schtasks /run /tn AITrader-Loop
    echo.
    echo ================================================================
    echo DRY-RUN MODE RESTORED
    echo ================================================================
    echo.
    echo The loop will now simulate trades without placing real orders.
    echo Monitor at: http://localhost:8000
    echo.
) else (
    echo ERROR: Failed to update task (code: %ERRORLEVEL%)
    echo Please ensure you run this script as Administrator.
    goto :error
)

goto :end

:error
echo.
echo ================================================================
echo FAILED - Please run as Administrator
echo ================================================================
echo.
echo Right-click this file and select "Run as administrator"
echo.

:end
pause
