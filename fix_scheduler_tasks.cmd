@echo off
echo ================================================================
echo AI Trader - Fix Scheduled Tasks
echo ================================================================
echo.
echo This script will:
echo   1. Update AITrader-Loop to add DryRun flag (safe mode)
echo   2. Delete obsolete AI-Trader-Hourly task
echo.
echo This script requires Administrator privileges.
echo Right-click and select "Run as administrator"
echo.
pause

echo.
echo [1/2] Updating AITrader-Loop task...
echo ----------------------------------------------------------------
schtasks /Create /TN AITrader-Loop /XML "%~dp0AITrader-Loop.xml" /F

if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: AITrader-Loop task updated with DryRun flag.
) else (
    echo ERROR: Failed to update AITrader-Loop task (code: %ERRORLEVEL%)
    echo Please ensure you run this script as Administrator.
    goto :error
)

echo.
echo [2/2] Deleting obsolete AI-Trader-Hourly task...
echo ----------------------------------------------------------------
schtasks /Delete /TN AI-Trader-Hourly /F

if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: AI-Trader-Hourly task deleted.
) else (
    echo WARNING: Could not delete AI-Trader-Hourly (code: %ERRORLEVEL%)
    echo This task may already be deleted or inaccessible.
)

echo.
echo ================================================================
echo SUMMARY - Tasks Fixed Successfully
echo ================================================================
echo.
echo Current AITrader Tasks:
schtasks /Query /TN AITrader-Dashboard /FO LIST | findstr /C:"Status" /C:"Next Run"
echo.
schtasks /Query /TN AITrader-Loop /FO LIST | findstr /C:"Status" /C:"Next Run" /C:"Task To Run"
echo.
schtasks /Query /TN AITrader-Selector /FO LIST | findstr /C:"Status" /C:"Next Run"
echo.
echo ================================================================
echo.
echo AITrader-Loop will now run in DRY-RUN mode (no actual orders).
echo Next scheduled run will use the updated configuration.
echo.
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
