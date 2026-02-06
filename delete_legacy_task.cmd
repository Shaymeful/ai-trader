@echo off
echo ================================================================
echo Deleting Obsolete AI-Trader-Hourly Task
echo ================================================================
echo.
echo This script requires Administrator privileges.
echo.
echo The AI-Trader-Hourly task is obsolete and has been replaced by
echo the AITrader-Loop task. It is currently disabled but should be
echo removed to avoid confusion.
echo.
pause

schtasks /Delete /TN AI-Trader-Hourly /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: AI-Trader-Hourly task deleted successfully!
) else (
    echo.
    echo ERROR: Failed to delete task. Error code: %ERRORLEVEL%
    echo Please ensure you run this script as Administrator.
)

echo.
pause
