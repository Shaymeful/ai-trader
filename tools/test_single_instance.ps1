# Test Single Instance Guard
# Run this script as Administrator to verify the single-instance protection

$ErrorActionPreference = "Stop"

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Single Instance Guard Test" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

$root = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"
$lockFile = Join-Path $root "logs\runner.lock"
$testLog = Join-Path $root "logs\single_instance_test.log"

# Initialize test log
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting single instance test" | Out-File $testLog

# Step 1: Kill any existing runner processes
Write-Host "[1/7] Killing existing runner processes..." -ForegroundColor Yellow
$killed = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*src.app.runner*") {
        Write-Host "  Killing PID $($proc.Id)" -ForegroundColor Red
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $killed++
    }
}
if ($killed -eq 0) {
    Write-Host "  No existing processes found" -ForegroundColor Green
}
Start-Sleep -Seconds 2

# Step 2: Remove lock file
Write-Host ""
Write-Host "[2/7] Removing lock file..." -ForegroundColor Yellow
if (Test-Path $lockFile) {
    try {
        Remove-Item $lockFile -Force -ErrorAction Stop
        Write-Host "  Lock file removed: $lockFile" -ForegroundColor Green
    } catch {
        Write-Host "  WARNING: Could not remove lock file (may be held)" -ForegroundColor Red
        Write-Host "  This might indicate a process is still running" -ForegroundColor Red
    }
} else {
    Write-Host "  Lock file doesn't exist (OK)" -ForegroundColor Green
}

# Step 3: Start first instance in background
Write-Host ""
Write-Host "[3/7] Starting FIRST runner instance..." -ForegroundColor Yellow
$proc1 = Start-Process -FilePath $python `
    -ArgumentList "-m", "src.app.runner", "--mode", "paper", "--once", "--dry-run" `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput "$root\logs\test_instance1_stdout.log" `
    -RedirectStandardError "$root\logs\test_instance1_stderr.log"

Write-Host "  Started PID: $($proc1.Id)" -ForegroundColor Green
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] First instance started: PID $($proc1.Id)" | Out-File $testLog -Append

# Wait for it to acquire lock
Start-Sleep -Seconds 2

# Step 4: Try to start SECOND instance (should be blocked)
Write-Host ""
Write-Host "[4/7] Attempting to start SECOND instance (should be BLOCKED)..." -ForegroundColor Yellow

$startTime = Get-Date
$proc2Output = & $python -m src.app.runner --mode paper --once --dry-run 2>&1
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host ""
Write-Host "Second instance output:" -ForegroundColor Cyan
Write-Host "-" * 80
$proc2Output | ForEach-Object { Write-Host $_ }
Write-Host "-" * 80
Write-Host "Duration: $([math]::Round($duration, 2)) seconds" -ForegroundColor Cyan

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Second instance blocked in $duration seconds" | Out-File $testLog -Append

# Step 5: Check if guard worked
Write-Host ""
Write-Host "[5/7] Verifying guard blocked duplicate..." -ForegroundColor Yellow
$blocked = $false
if ($proc2Output -like "*SINGLE INSTANCE GUARD*") {
    Write-Host "  ✓ SUCCESS: Guard detected and blocked duplicate!" -ForegroundColor Green
    $blocked = $true
} else {
    Write-Host "  ✗ FAILED: Guard did NOT block duplicate!" -ForegroundColor Red
}

# Check that it exited quickly (< 5 seconds means it was blocked before heavy work)
if ($duration -lt 5) {
    Write-Host "  ✓ SUCCESS: Blocked quickly ($([math]::Round($duration, 2))s < 5s)" -ForegroundColor Green
} else {
    Write-Host "  ✗ WARNING: Took too long ($([math]::Round($duration, 2))s), may not have blocked early" -ForegroundColor Red
}

# Step 6: Verify process count
Write-Host ""
Write-Host "[6/7] Verifying only ONE runner process exists..." -ForegroundColor Yellow
$runnerCount = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*src.app.runner*") {
        Write-Host "  Found runner PID: $($proc.Id)" -ForegroundColor Cyan
        $runnerCount++
    }
}

if ($runnerCount -eq 1) {
    Write-Host "  ✓ SUCCESS: Exactly 1 runner process exists" -ForegroundColor Green
} elseif ($runnerCount -eq 0) {
    Write-Host "  ⚠ INFO: No runner processes (first instance may have exited)" -ForegroundColor Yellow
} else {
    Write-Host "  ✗ FAILED: Found $runnerCount runner processes (expected 1)" -ForegroundColor Red
}

# Step 7: Wait for first instance to complete and clean up
Write-Host ""
Write-Host "[7/7] Waiting for first instance to complete..." -ForegroundColor Yellow
$waited = 0
while (!$proc1.HasExited -and $waited -lt 120) {
    Start-Sleep -Seconds 1
    $waited++
    if ($waited % 10 -eq 0) {
        Write-Host "  Waiting... ($waited seconds)" -ForegroundColor Gray
    }
}

if ($proc1.HasExited) {
    Write-Host "  First instance completed with exit code: $($proc1.ExitCode)" -ForegroundColor Green
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] First instance completed: exit code $($proc1.ExitCode)" | Out-File $testLog -Append
} else {
    Write-Host "  First instance still running after 120s, killing..." -ForegroundColor Yellow
    Stop-Process -Id $proc1.Id -Force -ErrorAction SilentlyContinue
}

# Check the first instance logs
Write-Host ""
Write-Host "First instance stdout (last 10 lines):" -ForegroundColor Cyan
Write-Host "-" * 80
Get-Content "$root\logs\test_instance1_stdout.log" -Tail 10 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
Write-Host "-" * 80

# Final summary
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

if ($blocked -and $runnerCount -le 1 -and $duration -lt 5) {
    Write-Host "✓ ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "  - Guard blocked duplicate instance" -ForegroundColor Green
    Write-Host "  - Blocked quickly (fast-fail)" -ForegroundColor Green
    Write-Host "  - Only one process ran" -ForegroundColor Green
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] TEST PASSED" | Out-File $testLog -Append
} else {
    Write-Host "✗ SOME CHECKS FAILED" -ForegroundColor Red
    Write-Host "  - Guard blocked: $blocked" -ForegroundColor $(if ($blocked) { "Green" } else { "Red" })
    Write-Host "  - Process count: $runnerCount (expected 0-1)" -ForegroundColor $(if ($runnerCount -le 1) { "Green" } else { "Red" })
    Write-Host "  - Block duration: $([math]::Round($duration, 2))s (expected < 5s)" -ForegroundColor $(if ($duration -lt 5) { "Green" } else { "Red" })
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] TEST FAILED" | Out-File $testLog -Append
}

Write-Host ""
Write-Host "Test log saved to: $testLog" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
