@echo off
REM AI Trader - Remove Paper Trading Task (Admin Required)
REM This will remove the Windows Task Scheduler task

powershell -Command "Start-Process PowerShell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup_paper_trading_task.ps1\" -Remove' -Verb RunAs"
