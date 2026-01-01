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

$proc1 = Start-Process -FilePath $python `
    -ArgumentList "-m", "src.app.runner", "--mode", "paper", "--loop", "--sleep-seconds", "3600", "--dry-run" `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $log1 `
    -RedirectStandardError $err1

Write-Host "  Started PID: $($proc1.Id)"
Write-Host "  Command: python -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run"
Write-Host "  Waiting 3 seconds for startup..."
Start-Sleep -Seconds 3

# Check if first instance is still running
if ($proc1.HasExited) {
    Write-Host "  ERROR: First instance exited unexpectedly (exit code: $($proc1.ExitCode))"
    Write-Host ""
    Write-Host "Output:"
    Get-Content $log1 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
    Write-Host "Errors:"
    Get-Content $err1 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    exit 1
}
Write-Host "  [OK] First instance running (PID: $($proc1.Id))"

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

# Check 1: Guard message present
$guardMsg = $proc2Output | Select-String -Pattern "SINGLE INSTANCE GUARD|DETECTED RUNNER CHILD PROCESS" -Quiet
if ($guardMsg) {
    Write-Host "  [PASS] Guard blocked duplicate instance"
} else {
    Write-Host "  [FAIL] Guard did NOT block duplicate"
    $issues += "No guard block message found"
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

# Check 3: Exactly 1 runner process
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

if ($runnerCount -eq 1) {
    Write-Host "  [PASS] Exactly 1 runner process running (PID: $runnerPids)"
} elseif ($runnerCount -eq 0) {
    Write-Host "  [WARN] No runners found (first instance may have crashed)"
    $issues += "First instance not running"
    $passed = $false
} else {
    Write-Host "  [FAIL] Found $runnerCount runners (expected 1): PIDs $runnerPids"
    $issues += "Multiple runners detected"
    $passed = $false
}

# Clean up
Write-Host ""
Write-Host "Cleaning up..."
if (!$proc1.HasExited) {
    Stop-Process -Id $proc1.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  Stopped first instance (PID: $($proc1.Id))"
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
