@echo off
:: Simple batch file to install Windows scheduled tasks
:: Double-click this file to install the 3 scheduled tasks
:: You will be prompted for Administrator privileges

echo ================================================================
echo AI Trader - Task Scheduler Installation
echo ================================================================
echo.
echo This will install 3 scheduled tasks for automated trading:
echo.
echo   AITrader-Dashboard
echo     - Starts at 8:45 AM daily
echo     - Runs FastAPI dashboard on port 8000
echo.
echo   AITrader-Selector
echo     - Runs every 15 minutes from 8:50 AM to 4:10 PM
echo     - Fetches RSS feeds and generates candidates
echo.
echo   AITrader-Loop
echo     - Starts at 9:00 AM daily, repeats hourly
echo     - Executes trading logic in paper mode
echo.
echo ================================================================
echo.

:: Request elevation via PowerShell
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -NoProfile -File \"%~dp0tools\windows\install_tasks.ps1\"' -Verb RunAs -Wait"

echo.
echo ================================================================
echo Installation attempt completed
echo ================================================================
echo.
echo Checking for installed tasks...
echo.

:: Check if tasks were created
schtasks /query /tn "AITrader-Dashboard" >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] AITrader-Dashboard installed
) else (
    echo [MISSING] AITrader-Dashboard
)

schtasks /query /tn "AITrader-Selector" >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] AITrader-Selector installed
) else (
    echo [MISSING] AITrader-Selector
)

schtasks /query /tn "AITrader-Loop" >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] AITrader-Loop installed
) else (
    echo [MISSING] AITrader-Loop
)

echo.
echo To view task details, run:
echo   schtasks /query /tn "AITrader-Dashboard" /v /fo LIST
echo   schtasks /query /tn "AITrader-Selector" /v /fo LIST
echo   schtasks /query /tn "AITrader-Loop" /v /fo LIST
echo.
echo To uninstall, run:
echo   powershell -ExecutionPolicy Bypass -File tools\windows\install_tasks.ps1 -Remove
echo.
pause
