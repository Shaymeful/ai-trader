@echo off
REM FINAL FIX - Update AITrader-Loop Task
REM Right-click and Run as Administrator

echo.
echo ================================================================================
echo FINAL FIX: Updating AITrader-Loop Task
echo ================================================================================
echo.

echo [1/4] Stopping task and killing all Python processes...
schtasks /End /TN "AITrader-Loop" 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
echo       Done

echo [2/4] Deleting old task...
schtasks /Delete /TN "AITrader-Loop" /F
if %ERRORLEVEL% NEQ 0 (
    echo       ERROR: Failed to delete task. Make sure you ran as Administrator!
    pause
    exit /b 1
)
echo       Done

echo [3/4] Creating new task from XML...
schtasks /Create /TN "AITrader-Loop" /XML "C:\dev\ai-trader\AITrader-Loop-Updated.xml" /F
if %ERRORLEVEL% NEQ 0 (
    echo       ERROR: Failed to create task!
    pause
    exit /b 1
)
echo       Done

echo [4/4] Starting new task...
schtasks /Run /TN "AITrader-Loop"
timeout /t 3 /nobreak >nul
echo       Done

echo.
echo ================================================================================
echo SUCCESS! Task has been updated
echo ================================================================================
echo.
echo New settings:
echo   - Hidden mode: YES (no pop-ups)
echo   - Interval: 5 minutes (300 seconds)
echo   - Market hours check: YES (Mon-Fri 9:30 AM - 4:00 PM ET)
echo.
echo Since market is closed now, the loop should show:
echo   "MARKET CLOSED - Next market open in: XX hours"
echo.
echo Verifying...
echo.

REM Verify the task
schtasks /Query /TN "AITrader-Loop" /V /FO LIST | findstr /C:"Task To Run"

echo.
echo Check logs at: logs\loop_status.log
echo.
pause
