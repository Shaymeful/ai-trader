@echo off
REM AI Trader - Paper Trading Task Setup (Admin Required)
REM This will create a Windows Task Scheduler task for hourly paper trading

powershell -Command "Start-Process PowerShell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup_paper_trading_task.ps1\"' -Verb RunAs"
