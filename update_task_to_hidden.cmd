@echo off
echo Making AITrader-Loop task hidden...
echo.

REM Export current task
schtasks /Query /TN "AITrader-Loop" /XML > "%TEMP%\AITrader-Loop.xml"

REM Modify Hidden setting using PowerShell
powershell -NoProfile -Command "(Get-Content '%TEMP%\AITrader-Loop.xml') -replace '<Hidden>false</Hidden>', '<Hidden>true</Hidden>' | Set-Content '%TEMP%\AITrader-Loop-hidden.xml'"

REM Re-import task (requires admin)
echo Updating task (requires admin permissions)...
schtasks /Delete /TN "AITrader-Loop" /F >nul 2>&1
schtasks /Create /TN "AITrader-Loop" /XML "%TEMP%\AITrader-Loop-hidden.xml"

echo.
echo Done! Task should now be hidden.
echo.
pause
