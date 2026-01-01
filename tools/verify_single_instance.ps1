# Verify Single Instance Guard - Quick Test
# This script performs a simple verification that the single-instance guard works

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Single Instance Guard Verification" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

$root = "C:\dev\ai-trader"
$python = Join-Path $root ".venv\Scripts\python.exe"

# Check if pywin32 is installed
Write-Host "[1/5] Checking pywin32 installation..." -ForegroundColor Yellow
$pywin32Check = & $python -c "import win32event; print('OK')" 2>&1
if ($pywin32Check -ne "OK") {
    Write-Host "  ERROR: pywin32 not installed" -ForegroundColor Red
    Write-Host "  Run: .venv\Scripts\pip.exe install pywin32" -ForegroundColor Yellow
    exit 1
}
Write-Host "  ✓ pywin32 installed" -ForegroundColor Green

# Kill any existing runners
Write-Host ""
Write-Host "[2/5] Cleaning up existing runners..." -ForegroundColor Yellow
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
    Write-Host "  No existing runners" -ForegroundColor Green
}
Start-Sleep -Seconds 2

# Remove lock files
Write-Host ""
Write-Host "[3/5] Removing lock files..." -ForegroundColor Yellow
Remove-Item "$root\logs\paper_dryrun.lock" -Force -ErrorAction SilentlyContinue
Write-Host "  ✓ Lock files cleared" -ForegroundColor Green

# Start first instance
Write-Host ""
Write-Host "[4/5] Starting first runner instance..." -ForegroundColor Yellow
$proc1 = Start-Process -FilePath $python `
    -ArgumentList "-m", "src.app.runner", "--mode", "paper", "--once", "--dry-run" `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput "$root\logs\verify_instance1.log" `
    -RedirectStandardError "$root\logs\verify_instance1_err.log"

Write-Host "  Started PID: $($proc1.Id)" -ForegroundColor Green
Start-Sleep -Seconds 2

# Try to start duplicate (should be blocked)
Write-Host ""
Write-Host "[5/5] Attempting duplicate instance (should be BLOCKED)..." -ForegroundColor Yellow
$startTime = Get-Date
$proc2Output = & $python -m src.app.runner --mode paper --once --dry-run 2>&1
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host ""
Write-Host "Second instance output:" -ForegroundColor Cyan
Write-Host "-" * 80
$proc2Output | ForEach-Object { Write-Host $_ }
Write-Host "-" * 80

# Check results
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Results" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

$passed = $true

# Check if blocked
if ($proc2Output -like "*SINGLE INSTANCE GUARD*") {
    Write-Host "✓ Guard blocked duplicate instance" -ForegroundColor Green
} else {
    Write-Host "✗ Guard did NOT block duplicate" -ForegroundColor Red
    $passed = $false
}

# Check duration (< 5 seconds means fast-fail)
if ($duration -lt 5) {
    Write-Host "✓ Blocked quickly: $([math]::Round($duration, 2))s" -ForegroundColor Green
} else {
    Write-Host "✗ Took too long: $([math]::Round($duration, 2))s (expected < 5s)" -ForegroundColor Red
    $passed = $false
}

# Check process count
$runnerCount = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*src.app.runner*") {
        $runnerCount++
    }
}

if ($runnerCount -eq 1) {
    Write-Host "✓ Exactly 1 runner process exists" -ForegroundColor Green
} elseif ($runnerCount -eq 0) {
    Write-Host "⚠ No runners (first may have finished)" -ForegroundColor Yellow
} else {
    Write-Host "✗ Found $runnerCount runners (expected 1)" -ForegroundColor Red
    $passed = $false
}

# Clean up
Write-Host ""
Write-Host "Cleaning up..." -ForegroundColor Gray
if (!$proc1.HasExited) {
    Stop-Process -Id $proc1.Id -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($passed) {
    Write-Host "=" * 80 -ForegroundColor Green
    Write-Host "✓ VERIFICATION PASSED" -ForegroundColor Green
    Write-Host "=" * 80 -ForegroundColor Green
    exit 0
} else {
    Write-Host "=" * 80 -ForegroundColor Red
    Write-Host "✗ VERIFICATION FAILED" -ForegroundColor Red
    Write-Host "=" * 80 -ForegroundColor Red
    exit 1
}
