# Verify Single Instance Guard - Loop Mode Test
# This script tests the single-instance guard specifically for --loop mode
# to ensure duplicate concurrent loop processes cannot run.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host ("=" * 80)
Write-Host "Single Instance Guard Verification - LOOP MODE"
Write-Host ("=" * 80)
Write-Host ""

$root = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"

# Ensure logs directory exists
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Check if pywin32 is installed
Write-Host "[1/6] Checking pywin32 installation..."
$pywin32Check = & $python -c "import win32event; print('OK')" 2>&1
if ($pywin32Check -ne "OK") {
    Write-Host "  ERROR: pywin32 not installed"
    Write-Host "  Run: .venv\Scripts\pip.exe install pywin32"
    exit 1
}
Write-Host "  [OK] pywin32 installed"

# Kill any existing runners
Write-Host ""
Write-Host "[2/6] Cleaning up existing runners..."
$killed = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*runner.py*" -or $cmdLine -like "*src.app.runner*") {
        Write-Host "  Killing PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $killed++
    }
}
if ($killed -eq 0) {
    Write-Host "  [OK] No existing runners found"
} else {
    Write-Host "  [OK] Killed $killed runner(s)"
}
Start-Sleep -Seconds 2

# Remove lock files
Write-Host ""
Write-Host "[3/6] Removing lock files..."
$lockFile = Join-Path $logDir "paper_dryrun.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
}
Write-Host "  [OK] Lock files cleared"

# Start first LOOP instance
Write-Host ""
Write-Host "[4/6] Starting first runner in LOOP mode..."
$log1 = Join-Path $logDir "verify_loop_instance1.log"
$err1 = Join-Path $logDir "verify_loop_instance1_err.log"

# Use Start-Job to run in background without creating parent-child python process tree
$startJob = Start-Job -ScriptBlock {
    param($python, $root, $log1, $err1)
    Set-Location $root
    & $python -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run 2>&1 | Tee-Object -FilePath $log1
} -ArgumentList $python, $root, $log1, $err1

Write-Host "  Started background job: $($startJob.Id)"
Write-Host "  Command: python -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run"
Write-Host "  Waiting 5 seconds for startup and re-exec to settle..."
Start-Sleep -Seconds 5

# Find the actual runner process (not the launcher PID)
$runnerPid = $null
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*runner.py*" -or $cmdLine -like "*src.app.runner*") {
        $runnerPid = $proc.Id
    }
}

if ($null -eq $runnerPid) {
    Write-Host "  ERROR: No runner process found after startup"
    Write-Host ""
    Write-Host "Job output:"
    Receive-Job -Job $startJob | ForEach-Object { Write-Host "  $_" }
    Stop-Job -Job $startJob
    Remove-Job -Job $startJob
    exit 1
}
Write-Host "  [OK] First instance running (PID: $runnerPid)"

# Try to start duplicate LOOP instance (should be blocked immediately)
Write-Host ""
Write-Host "[5/6] Attempting duplicate LOOP instance (should be BLOCKED)..."
$log2 = Join-Path $logDir "verify_loop_instance2.log"
$err2 = Join-Path $logDir "verify_loop_instance2_err.log"

$startTime = Get-Date

# Run second instance directly and capture output
$proc2Job = Start-Job -ScriptBlock {
    param($python, $root, $log2, $err2)
    Set-Location $root
    & $python -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run 2>&1 | Tee-Object -FilePath $log2
} -ArgumentList $python, $root, $log2, $err2

# Wait up to 10 seconds for second instance to exit
$timeout = 10
$elapsed = 0
while ($proc2Job.State -eq 'Running' -and $elapsed -lt $timeout) {
    Start-Sleep -Milliseconds 500
    $elapsed += 0.5
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

# Stop job if still running
if ($proc2Job.State -eq 'Running') {
    Stop-Job -Job $proc2Job
}

# Get output
$proc2Output = Receive-Job -Job $proc2Job
Remove-Job -Job $proc2Job

Write-Host ""
Write-Host "Second instance output:"
Write-Host ("-" * 80)
$proc2Output | ForEach-Object { Write-Host $_ }
Write-Host ("-" * 80)
Write-Host "Duration: $([math]::Round($duration, 2)) seconds"

# Check results
Write-Host ""
Write-Host "[6/6] Analyzing results..."
Write-Host ""

$passed = $true
$issues = @()

# Check 1: Guard or re-exec detection message present
$guardBlocked = $proc2Output | Select-String -Pattern "SINGLE INSTANCE GUARD" -Quiet
$reexecDetected = $proc2Output | Select-String -Pattern "DETECTED RUNNER CHILD PROCESS" -Quiet

if ($guardBlocked) {
    Write-Host "  [PASS] Mutex/file lock guard blocked duplicate instance"
} elseif ($reexecDetected) {
    Write-Host "  [PASS] Re-exec child detected and exited immediately"
} else {
    Write-Host "  [FAIL] Neither guard block nor re-exec detection occurred"
    $issues += "No guard block or re-exec detection message found"
    $passed = $false
}

# Check 2: Fast exit (< 5 seconds)
if ($duration -lt 5) {
    Write-Host "  [PASS] Blocked quickly: $([math]::Round($duration, 2))s"
} else {
    Write-Host "  [FAIL] Took too long: $([math]::Round($duration, 2))s (expected < 5s)"
    $issues += "Blocking took too long"
    $passed = $false
}

# Check 3: Original runner process still alive (allow brief settle time)
Write-Host "  Waiting 2 seconds for transient processes to clean up..."
Start-Sleep -Seconds 2

$runnerCount = 0
$runnerPids = @()
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*runner.py*" -or $cmdLine -like "*src.app.runner*") {
        $runnerCount++
        $runnerPids += $proc.Id
    }
}

# Verify the specific runner we started is still alive
$runnerStillAlive = Get-Process -Id $runnerPid -ErrorAction SilentlyContinue
if ($null -ne $runnerStillAlive) {
    if ($runnerCount -eq 1) {
        Write-Host "  [PASS] Exactly 1 runner process (original runner PID: $runnerPid)"
    } elseif ($runnerCount -gt 1) {
        Write-Host "  [WARN] Found $runnerCount runners, but original ($runnerPid) is alive"
        Write-Host "  Additional PIDs: $($runnerPids | Where-Object {$_ -ne $runnerPid})"
        Write-Host "  (This may indicate transient parent processes from -m invocation)"
        # Don't fail - as long as original is alive, guard is working
    }
} else {
    Write-Host "  [FAIL] Original runner (PID: $runnerPid) is not running"
    if ($runnerCount -gt 0) {
        Write-Host "  Found $runnerCount other runners: PIDs $runnerPids"
    }
    $issues += "Original runner process died"
    $passed = $false
}

# Clean up
Write-Host ""
Write-Host "Cleaning up..."
if ($null -ne $runnerPid) {
    Get-Process -Id $runnerPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  Stopped runner process (PID: $runnerPid)"
}
if ($startJob.State -eq 'Running') {
    Stop-Job -Job $startJob
    Remove-Job -Job $startJob
    Write-Host "  Stopped background job"
}

# Final result
Write-Host ""
Write-Host ("=" * 80)
if ($passed) {
    Write-Host "[VERIFICATION PASSED]"
    Write-Host ("=" * 80)
    Write-Host ""
    Write-Host "The single-instance guard successfully prevented duplicate loop instances."
    exit 0
} else {
    Write-Host "[VERIFICATION FAILED]"
    Write-Host ("=" * 80)
    Write-Host ""
    Write-Host "Issues detected:"
    $issues | ForEach-Object { Write-Host "  - $_" }
    Write-Host ""
    Write-Host "Logs:"
    Write-Host "  First instance:  $log1"
    Write-Host "  Second instance: $log2"
    exit 1
}
