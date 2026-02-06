# Restart AI Trader Loop with Reconciliation
# This script stops the current loop and starts it with the new reconciliation code

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Restarting Loop with Reconciliation  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop current loop
Write-Host "[Step 1/3] Stopping current loop..." -ForegroundColor Yellow
Write-Host ""

& ".\tools\stop_runner.ps1"

Write-Host ""
Write-Host "Waiting 3 seconds for cleanup..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# Step 2: Verify we're on the right branch
Write-Host ""
Write-Host "[Step 2/3] Verifying branch..." -ForegroundColor Yellow
$currentBranch = git branch --show-current
Write-Host "Current branch: $currentBranch" -ForegroundColor Cyan

if ($currentBranch -ne "feature/sell-reconcile-and-universe-rotation") {
    Write-Host ""
    Write-Host "WARNING: Not on feature/sell-reconcile-and-universe-rotation branch!" -ForegroundColor Red
    Write-Host "Reconciliation code is on: feature/sell-reconcile-and-universe-rotation" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Continue anyway? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Aborted. Switch branch first: git checkout feature/sell-reconcile-and-universe-rotation" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""

# Step 3: Start loop with reconciliation
Write-Host "[Step 3/3] Starting loop with reconciliation..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Starting loop in background..." -ForegroundColor Cyan
Write-Host "Look for these lines in the output:" -ForegroundColor Gray
Write-Host "  - 'Initializing ticker exclusion manager...'" -ForegroundColor Gray
Write-Host "  - 'Running portfolio reconciliation...'" -ForegroundColor Gray
Write-Host "  - 'Reconciliation complete: ...'" -ForegroundColor Gray
Write-Host ""

# Start the loop
& ".\tools\windows\start_loop.ps1"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Loop Restarted Successfully!         " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Check logs for reconciliation output" -ForegroundColor White
Write-Host "  2. Verify current exposure: python check_exposure.py" -ForegroundColor White
Write-Host "  3. Monitor for sell orders when positions accumulate" -ForegroundColor White
Write-Host ""
