@echo off
echo ===============================================================================
echo AI Trader Instance Audit - Quick Check
echo ===============================================================================
echo.

echo [1/5] Checking for Python processes...
powershell -Command "Get-Process python* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName | Format-Table -AutoSize"
if errorlevel 1 echo   OK - No Python processes running
echo.

echo [2/5] Checking Task Scheduler for trader tasks...
schtasks /query /fo LIST | findstr /i "AI-Trader"
if errorlevel 1 echo   OK - No AI-Trader tasks found
echo.

echo [3/5] Checking for ALPACA environment variables...
set | findstr /i "ALPACA"
if errorlevel 1 echo   OK - No ALPACA environment variables
echo.

echo [4/5] Checking for .env files in ai-trader...
dir /s /b .env 2>nul
if errorlevel 1 echo   OK - No .env files found in current directory
echo.

echo [5/5] Checking Docker...
docker ps 2>nul
if errorlevel 1 echo   OK - Docker not running or not installed
echo.

echo ===============================================================================
echo Audit complete!
echo.
echo For comprehensive audit including cloud servers, see:
echo   docs/AUDIT_CHECKLIST.md
echo.
echo To check Alpaca order history:
echo   powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
echo ===============================================================================
pause
