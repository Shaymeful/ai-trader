# Complete restart and verification script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "STEP 1: Stopping all Python processes" -ForegroundColor Cyan
Write-Host "========================================`n"

Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Killing PID $($_.Id) - $($_.ProcessName)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "`nWaiting 10 seconds for cleanup..." -ForegroundColor Gray
Start-Sleep -Seconds 10

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "STEP 2: Starting Dashboard" -ForegroundColor Cyan
Write-Host "========================================`n"

schtasks /run /tn "AITrader-Dashboard" | Out-Null
Write-Host "Dashboard task triggered" -ForegroundColor Green
Start-Sleep -Seconds 15

# Verify dashboard is running
$dashboardRunning = $false
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health/detailed" -TimeoutSec 5
    $dashboardRunning = $true
    Write-Host "Dashboard responding on port 8000" -ForegroundColor Green
} catch {
    Write-Host "Dashboard not responding yet" -ForegroundColor Red
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "STEP 3: Starting Trading Loop" -ForegroundColor Cyan
Write-Host "========================================`n"

schtasks /run /tn "AITrader-Loop" | Out-Null
Write-Host "Loop task triggered" -ForegroundColor Green
Start-Sleep -Seconds 35

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "STEP 4: Verification" -ForegroundColor Cyan
Write-Host "========================================`n"

# Check universe_active.json
Write-Host "Checking universe_active.json..." -ForegroundColor White
$universeFile = Get-Content "out\universe_active.json" | ConvertFrom-Json
$symbolCount = $universeFile.symbols.Count
$hasEOSE = $universeFile.symbols -contains "EOSE"

Write-Host "  Timestamp: $($universeFile.timestamp)" -ForegroundColor Gray
Write-Host "  Source: $($universeFile.source)" -ForegroundColor Gray
Write-Host "  Symbol Count: $symbolCount" -ForegroundColor $(if ($symbolCount -eq 20) { "Green" } else { "Red" })

if ($symbolCount -gt 0) {
    Write-Host "`n  Symbols:" -ForegroundColor Gray
    $universeFile.symbols | Sort-Object | ForEach-Object {
        $color = if ($_ -eq "EOSE") { "Cyan" } else { "White" }
        Write-Host "    $_" -ForegroundColor $color
    }
}

Write-Host "`n  Energy sector EOSE: $(if ($hasEOSE) { 'INCLUDED' } else { 'MISSING' })" -ForegroundColor $(if ($hasEOSE) { "Green" } else { "Red" })

# Check dashboard API
if ($dashboardRunning) {
    Write-Host "`nChecking Dashboard API..." -ForegroundColor White
    try {
        $sectors = Invoke-RestMethod -Uri "http://localhost:8000/universe/sectors"
        Write-Host "  Total symbols in registry: $($sectors.total_symbols)" -ForegroundColor $(if ($sectors.total_symbols -eq 20) { "Green" } else { "Yellow" })

        Write-Host "`n  Sectors:" -ForegroundColor Gray
        $sectors.sectors | ForEach-Object {
            $status = if ($_.enabled) { "ENABLED" } else { "DISABLED" }
            $color = if ($_.enabled) { "Green" } else { "Red" }
            $symCount = $_.symbol_count
            Write-Host "    $($_.sector_name): $status with $symCount symbols" -ForegroundColor $color
        }
    } catch {
        Write-Host "  API error occurred" -ForegroundColor Red
    }
}

# Check recent loop log
Write-Host "`nChecking Loop Log..." -ForegroundColor White
$logFile = "logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log"
if (Test-Path $logFile) {
    $recentLines = Get-Content $logFile -Tail 100

    # Find most recent Universe line
    $universeLine = $recentLines | Select-String -Pattern "Universe:" | Select-Object -Last 1
    if ($universeLine) {
        Write-Host "  Latest universe:" -ForegroundColor Gray
        Write-Host "    $universeLine" -ForegroundColor White
    }

    # Check for errors
    $errors = $recentLines | Select-String -Pattern "ERROR" | Select-Object -Last 3
    if ($errors) {
        Write-Host "`n  Recent errors:" -ForegroundColor Yellow
        $errors | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "VERIFICATION SUMMARY" -ForegroundColor Cyan
Write-Host "========================================`n"

$allGood = ($symbolCount -eq 20) -and $hasEOSE -and $dashboardRunning

if ($allGood) {
    Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "  - 20 symbols loaded" -ForegroundColor Green
    Write-Host "  - Energy sector EOSE included" -ForegroundColor Green
    Write-Host "  - Dashboard responding" -ForegroundColor Green
} else {
    Write-Host "ISSUES DETECTED" -ForegroundColor Yellow
    if ($symbolCount -ne 20) {
        Write-Host "  - Expected 20 symbols but found $symbolCount" -ForegroundColor Red
    }
    if (-not $hasEOSE) {
        Write-Host "  - Energy sector EOSE not included" -ForegroundColor Red
    }
    if (-not $dashboardRunning) {
        Write-Host "  - Dashboard not responding" -ForegroundColor Red
    }
}

Write-Host ""
