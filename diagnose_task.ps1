# Diagnose why task isn't updating

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "TASK DIAGNOSTIC" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Check all AITrader tasks
Write-Host "[1] Checking for AITrader tasks..." -ForegroundColor Yellow
$Tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "*AITrader*" }
$Tasks | ForEach-Object {
    Write-Host "  Found: $($_.TaskName) | State: $($_.State)" -ForegroundColor Gray
}
Write-Host ""

# Check the main task
Write-Host "[2] Checking AITrader-Loop task details..." -ForegroundColor Yellow
$Task = Get-ScheduledTask -TaskName "AITrader-Loop" -ErrorAction SilentlyContinue

if ($Task) {
    Write-Host "  Task exists: YES" -ForegroundColor Green
    Write-Host "  State: $($Task.State)" -ForegroundColor Gray
    Write-Host "  Arguments:" -ForegroundColor Gray
    Write-Host "    $($Task.Actions.Arguments)" -ForegroundColor DarkGray
} else {
    Write-Host "  Task exists: NO" -ForegroundColor Red
}
Write-Host ""

# Check XML files
Write-Host "[3] Checking XML files..." -ForegroundColor Yellow
$XMLPath = "C:\dev\ai-trader\AITrader-Loop-Updated.xml"
if (Test-Path $XMLPath) {
    $XMLContent = Get-Content $XMLPath -Raw
    if ($XMLContent -match "SleepSeconds 300") {
        Write-Host "  Updated XML: CORRECT (has SleepSeconds 300)" -ForegroundColor Green
    } else {
        Write-Host "  Updated XML: WRONG (missing SleepSeconds 300)" -ForegroundColor Red
    }

    if ($XMLContent -match "-WindowStyle Hidden") {
        Write-Host "  Updated XML: CORRECT (has -WindowStyle Hidden)" -ForegroundColor Green
    } else {
        Write-Host "  Updated XML: WRONG (missing -WindowStyle Hidden)" -ForegroundColor Red
    }
} else {
    Write-Host "  Updated XML: NOT FOUND at $XMLPath" -ForegroundColor Red
}
Write-Host ""

# Test if we can modify the task
Write-Host "[4] Testing permissions..." -ForegroundColor Yellow
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Host "  Running as Administrator: YES" -ForegroundColor Green
} else {
    Write-Host "  Running as Administrator: NO" -ForegroundColor Red
    Write-Host "  This script MUST run as Administrator to modify tasks!" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
