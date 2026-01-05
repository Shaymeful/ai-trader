@echo off
REM AI Trader - Start Loop Mode (Hourly Execution)
REM Run this to start the trading bot in continuous hourly loop mode

echo ================================================================================
echo AI TRADER - LOOP MODE (Hourly)
echo ================================================================================
echo.
echo Mode: Paper Trading (with registry-based allocation)
echo Interval: 3600 seconds (1 hour)
echo.
echo Press Ctrl+C to stop the loop at any time
echo.
echo ================================================================================
echo.

cd /d "%~dp0"

REM Run in loop mode
.venv\Scripts\python.exe -m src.app.runner --mode paper --loop --sleep-seconds 3600

pause
