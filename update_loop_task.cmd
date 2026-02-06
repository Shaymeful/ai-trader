@echo off
echo ================================================================
echo Updating AITrader-Loop Task to Add DryRun Flag
echo ================================================================
echo.
echo This script requires Administrator privileges.
echo.
echo Current task will be updated to run in DRY-RUN mode (no actual orders).
echo.
pause

schtasks /Create /TN AITrader-Loop /XML "%~dp0AITrader-Loop.xml" /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: AITrader-Loop task updated successfully!
    echo The loop will now run in DRY-RUN mode.
    echo.
    schtasks /Query /TN AITrader-Loop /V /FO LIST | findstr /C:"Task To Run"
) else (
    echo.
    echo ERROR: Failed to update task. Error code: %ERRORLEVEL%
    echo Please ensure you run this script as Administrator.
)

echo.
pause
