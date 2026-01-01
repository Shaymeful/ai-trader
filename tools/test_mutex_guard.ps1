# Test Mutex Guard - Run as Administrator
# This script tests the single-instance guard protection

$ErrorActionPreference = "Stop"

Write-Host "=" * 80
Write-Host "Testing Single-Instance Guard Protection"
Write-Host "=" * 80
Write-Host ""

# Step 1: Kill any existing runner processes
Write-Host "[Step 1] Killing existing python runner processes..."
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*src.app.runner*") {
        Write-Host "  Killing PID $($_.Id): $cmdLine"
        Stop-Process -Id $_.Id -Force
    }
}
Start-Sleep -Seconds 2

# Step 2: Clean up lock file
Write-Host ""
Write-Host "[Step 2] Cleaning up lock file..."
$lockFile = "C:\dev\ai-trader\logs\paper_dryrun.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
    Write-Host "  Lock file removed: $lockFile"
} else {
    Write-Host "  No lock file found (OK)"
}

# Step 3: Clear old logs
Write-Host ""
Write-Host "[Step 3] Clearing old test logs..."
$tsLog = "C:\dev\ai-trader\logs\task_scheduler.log"
if (Test-Path $tsLog) {
    Clear-Content $tsLog
    Write-Host "  Cleared: $tsLog"
}

# Step 4: Start first runner instance (should succeed)
Write-Host ""
Write-Host "[Step 4] Starting FIRST runner instance (should succeed)..."
$proc1 = Start-Process -FilePath "C:\dev\ai-trader\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "src.app.runner", "--mode", "paper", "--loop", "--sleep-seconds", "3600", "--dry-run" `
    -WorkingDirectory "C:\dev\ai-trader" `
    -NoNewWindow `
    -PassThru
Write-Host "  Started PID: $($proc1.Id)" -ForegroundColor Green
Start-Sleep -Seconds 3

# Step 5: Try to start second instance (should be BLOCKED by mutex)
Write-Host ""
Write-Host "[Step 5] Attempting to start SECOND instance (should be BLOCKED by mutex)..."
$output = & "C:\dev\ai-trader\.venv\Scripts\python.exe" -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run 2>&1
Write-Host ""
Write-Host "Output from second instance attempt:"
Write-Host "-" * 80
Write-Host $output
Write-Host "-" * 80

# Step 6: Check if mutex guard worked
if ($output -like "*SINGLE INSTANCE GUARD*") {
    Write-Host ""
    Write-Host "✓ SUCCESS: Mutex guard BLOCKED the duplicate instance!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ FAILED: Mutex guard did NOT block the duplicate instance!" -ForegroundColor Red
}

# Step 7: Try PowerShell script lock (should also be BLOCKED)
Write-Host ""
Write-Host "[Step 6] Testing PowerShell script lock..."
$scriptOutput = & powershell -ExecutionPolicy Bypass -File "C:\dev\ai-trader\tools\run_paper_dryrun.ps1" 2>&1
Start-Sleep -Seconds 2

# Check task_scheduler.log
$tsLogContent = Get-Content $tsLog -Tail 5
Write-Host ""
Write-Host "Recent task_scheduler.log entries:"
Write-Host "-" * 80
$tsLogContent | ForEach-Object { Write-Host $_ }
Write-Host "-" * 80

if ($tsLogContent -like "*BLOCKED*") {
    Write-Host ""
    Write-Host "✓ SUCCESS: PowerShell lock BLOCKED the duplicate script!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ FAILED: PowerShell lock did NOT block properly!" -ForegroundColor Red
}

# Step 8: Verify only ONE python runner process exists
Write-Host ""
Write-Host "[Step 7] Verifying only ONE runner process exists..."
$runnerProcs = @()
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*src.app.runner*") {
        $runnerProcs += $_.Id
        Write-Host "  Runner PID: $($_.Id)" -ForegroundColor Yellow
    }
}

if ($runnerProcs.Count -eq 1) {
    Write-Host ""
    Write-Host "✓ SUCCESS: Exactly ONE runner process exists!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ FAILED: Found $($runnerProcs.Count) runner processes (expected 1)!" -ForegroundColor Red
}

# Step 9: Clean up - kill the test runner
Write-Host ""
Write-Host "[Step 8] Cleaning up - killing test runner..."
if ($proc1.Id) {
    Stop-Process -Id $proc1.Id -Force
    Write-Host "  Killed PID: $($proc1.Id)"
}

Write-Host ""
Write-Host "=" * 80
Write-Host "Test Complete"
Write-Host "=" * 80
