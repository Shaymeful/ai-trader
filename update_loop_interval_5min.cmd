@echo off
echo ================================================================
echo Update AITrader-Loop to 5-minute interval
echo ================================================================
echo.
echo Current: 1 hour (3600 seconds)
echo New:     5 minutes (300 seconds)
echo.
echo This will:
echo 1. Stop the current loop
echo 2. Update task to run every 5 minutes
echo 3. Restart the loop immediately
echo.
pause

schtasks /End /TN AITrader-Loop
schtasks /Create /TN AITrader-Loop /XML "%~dp0temp_loop_task.xml" /F
schtasks /run /tn AITrader-Loop

echo.
echo ================================================================
echo Loop interval updated to 5 minutes!
echo ================================================================
echo.
echo Next iterations will run every 5 minutes.
echo Monitor: logs\loop\loop_20260108.log
echo.
pause
