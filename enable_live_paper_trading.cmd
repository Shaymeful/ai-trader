@echo off
echo ================================================================
echo AI Trader - Enable LIVE Paper Trading
echo ================================================================
echo.
echo WARNING: This will enable REAL order placement on your Alpaca
echo paper trading account. Trades will be executed using real paper
echo account money (simulated, but tracked by Alpaca).
echo.
echo Current mode: DRY-RUN (simulated only)
echo After this: LIVE PAPER (real orders on paper account)
echo.
echo This script requires Administrator privileges.
echo Right-click and select "Run as administrator"
echo.
pause

echo.
echo Stopping current loop task...
schtasks /End /TN AITrader-Loop

echo.
echo Updating AITrader-Loop task to LIVE mode...
schtasks /Create /TN AITrader-Loop /XML "%~dp0AITrader-Loop-Live.xml" /F

if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: AITrader-Loop task updated to LIVE paper trading mode.
    echo.
    echo Starting updated task...
    schtasks /run /tn AITrader-Loop
    echo.
    echo ================================================================
    echo LIVE PAPER TRADING ENABLED
    echo ================================================================
    echo.
    echo The loop will now place REAL orders on your Alpaca paper account.
    echo Monitor at: http://localhost:8000
    echo.
    echo To revert to DRY-RUN mode, run: revert_to_dryrun.cmd
    echo.
) else (
    echo ERROR: Failed to update task (code: %ERRORLEVEL%)
    echo Please ensure you run this script as Administrator.
    goto :error
)

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
