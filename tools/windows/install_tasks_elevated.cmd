@echo off
:: Batch file to install Windows scheduled tasks with automatic elevation
:: This will prompt for UAC elevation if not already running as Administrator

echo ================================================================
echo AI Trader - Windows Task Scheduler Installation
echo ================================================================
echo.
echo This script will install 3 scheduled tasks:
echo   1. AITrader-Dashboard (starts at 8:45 AM daily)
echo   2. AITrader-Selector (runs every 15 min, 8:50 AM - 4:10 PM)
echo   3. AITrader-Loop (starts at 9:00 AM daily, repeats hourly)
echo.
echo You will be prompted for Administrator privileges...
echo.
pause

:: Check if running as Administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Already running as Administrator. Proceeding...
    goto :run_install
) else (
    echo Requesting elevation...
    goto :elevate
)

:elevate
:: Request elevation using PowerShell
powershell -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0..\..\", tools\windows\install_tasks_elevated.cmd /elevated' -Verb RunAs"
exit /b

:run_install
:: We're running elevated now, execute the PowerShell script
cd /d "%~dp0..\.."
echo.
echo Current directory: %CD%
echo Running installation script...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0install_tasks.ps1"

if %errorLevel% == 0 (
    echo.
    echo ================================================================
    echo Installation completed successfully!
    echo ================================================================
    echo.
    echo Verifying installed tasks...
    schtasks /query /fo LIST | findstr /i AITrader
    echo.
) else (
    echo.
    echo ================================================================
    echo Installation failed with error code: %errorLevel%
    echo ================================================================
    echo.
)

echo Press any key to exit...
pause >nul
exit /b
