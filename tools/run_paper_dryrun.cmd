@echo off
setlocal

cd /d C:\dev\ai-trader

REM --- Single instance lock ---
set LOCK=C:\dev\ai-trader\logs\paper_dryrun.lock
if exist "%LOCK%" (
  echo [%date% %time%] Lock exists, exiting. >> C:\dev\ai-trader\logs\task_scheduler.log
  exit /b 0
)
echo %random% > "%LOCK%"

REM --- Run ---
"C:\dev\ai-trader\.venv\Scripts\python.exe" -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run

REM --- Cleanup lock ---
del "%LOCK%" >nul 2>&1
endlocal
