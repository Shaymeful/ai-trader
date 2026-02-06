# ABSOLUTE FINAL FIX - Shows output at each step
# Run as Administrator

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "ABSOLUTE FINAL FIX - Task Update with Diagnostics" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: You MUST run this as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell > Run as administrator" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Running as Administrator" -ForegroundColor Green
Write-Host ""

# Step 1: Stop task
Write-Host "[STEP 1] Stopping task..." -ForegroundColor Yellow
try {
    $result = schtasks /End /TN "AITrader-Loop" 2>&1
    Write-Host "  Output: $result" -ForegroundColor Gray
} catch {
    Write-Host "  Could not stop (may not be running)" -ForegroundColor Gray
}
Write-Host ""

# Step 2: Kill processes
Write-Host "[STEP 2] Killing Python processes..." -ForegroundColor Yellow
$pythonProcs = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcs) {
    Write-Host "  Found $($pythonProcs.Count) Python processes" -ForegroundColor Gray
    $pythonProcs | Stop-Process -Force
    Write-Host "  Killed Python processes" -ForegroundColor Gray
} else {
    Write-Host "  No Python processes running" -ForegroundColor Gray
}
Start-Sleep -Seconds 2
Write-Host ""

# Step 3: Delete old task
Write-Host "[STEP 3] Deleting old task..." -ForegroundColor Yellow
$deleteResult = schtasks /Delete /TN "AITrader-Loop" /F 2>&1
Write-Host "  Output: $deleteResult" -ForegroundColor Gray

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [SUCCESS] Task deleted" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Delete failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Step 4: Verify XML file
Write-Host "[STEP 4] Verifying XML file..." -ForegroundColor Yellow
$XMLPath = "C:\dev\ai-trader\AITrader-Loop-Updated.xml"
if (Test-Path $XMLPath) {
    Write-Host "  [OK] XML file exists" -ForegroundColor Green
    $xmlContent = Get-Content $XMLPath -Raw
    if ($xmlContent -match "SleepSeconds 300" -and $xmlContent -match "-WindowStyle Hidden") {
        Write-Host "  [OK] XML has correct settings" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] XML file has wrong settings!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  [ERROR] XML file not found!" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Create new task from XML
Write-Host "[STEP 5] Creating new task from XML..." -ForegroundColor Yellow
$createResult = schtasks /Create /TN "AITrader-Loop" /XML $XMLPath /F 2>&1
Write-Host "  Output: $createResult" -ForegroundColor Gray

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [SUCCESS] Task created" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Create failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host "  This is the problem! The XML import is failing." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Step 6: Verify new task
Write-Host "[STEP 6] Verifying new task..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
$newTask = Get-ScheduledTask -TaskName "AITrader-Loop"
$newArgs = $newTask.Actions.Arguments

Write-Host "  New task arguments:" -ForegroundColor Gray
Write-Host "  $newArgs" -ForegroundColor DarkGray
Write-Host ""

if ($newArgs -match "-WindowStyle Hidden") {
    Write-Host "  [OK] Has -WindowStyle Hidden" -ForegroundColor Green
} else {
    Write-Host "  [FAILED] Missing -WindowStyle Hidden!" -ForegroundColor Red
}

if ($newArgs -match "SleepSeconds 300") {
    Write-Host "  [OK] Has SleepSeconds 300" -ForegroundColor Green
} else {
    Write-Host "  [FAILED] Still has wrong SleepSeconds!" -ForegroundColor Red
}
Write-Host ""

# Step 7: Start the task
if ($newArgs -match "-WindowStyle Hidden" -and $newArgs -match "SleepSeconds 300") {
    Write-Host "[STEP 7] Starting new task..." -ForegroundColor Yellow
    $runResult = schtasks /Run /TN "AITrader-Loop" 2>&1
    Write-Host "  Output: $runResult" -ForegroundColor Gray
    Write-Host ""

    Start-Sleep -Seconds 3

    # Check if running
    $pythonProcs = Get-Process -Name python -ErrorAction SilentlyContinue
    if ($pythonProcs) {
        Write-Host "  [SUCCESS] Python processes running:" -ForegroundColor Green
        $pythonProcs | ForEach-Object {
            Write-Host "    PID: $($_.Id)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  [WARN] No Python processes detected yet" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor Green
    Write-Host "SUCCESS! TASK HAS BEEN UPDATED!" -ForegroundColor Green
    Write-Host "=" * 80 -ForegroundColor Green
    Write-Host ""
    Write-Host "The loop is now configured to:" -ForegroundColor Cyan
    Write-Host "  - Run HIDDEN (no pop-ups)" -ForegroundColor Gray
    Write-Host "  - Check every 5 MINUTES" -ForegroundColor Gray
    Write-Host "  - Only run during MARKET HOURS (Mon-Fri 9:30 AM - 4:00 PM ET)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Since market is closed, check logs for 'MARKET CLOSED' messages:" -ForegroundColor Yellow
    Write-Host "  logs\loop_status.log" -ForegroundColor Gray

} else {
    Write-Host "[STEP 7] SKIPPED - Task verification failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "The task was created but doesn't have the correct settings." -ForegroundColor Yellow
    Write-Host "This is very unusual. There may be a Windows policy preventing the changes." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Read-Host "Press Enter to close"
