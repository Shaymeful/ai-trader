# Comprehensive Dashboard Verification Script

Write-Host "================================================"
Write-Host "Dashboard Verification Test"
Write-Host "================================================"
Write-Host ""

# Test 1: Check if dashboard is running
Write-Host "[1/6] Checking if dashboard is running..."
$port = netstat -ano | Select-String ":8000.*LISTENING"
if ($port) {
    Write-Host "✅ Dashboard is running on port 8000" -ForegroundColor Green
} else {
    Write-Host "❌ Dashboard is NOT running" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 2: Test /health endpoint
Write-Host "[2/6] Testing /health endpoint..."
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
    Write-Host "✅ Health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Health endpoint failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 3: Test /runtime endpoint
Write-Host "[3/6] Testing /runtime endpoint..."
try {
    $runtime = Invoke-RestMethod -Uri "http://localhost:8000/runtime" -TimeoutSec 5
    Write-Host "✅ Runtime endpoint working" -ForegroundColor Green
    Write-Host "   Loop Interval: $($runtime.loop_interval_seconds)s"
    Write-Host "   Next Loop: $($runtime.next_loop_at)"
    Write-Host "   Countdown: $($runtime.seconds_until_next_loop)s"
} catch {
    Write-Host "❌ Runtime endpoint failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 4: Test HTML is being served
Write-Host "[4/6] Testing dashboard HTML..."
try {
    $html = Invoke-WebRequest -Uri "http://localhost:8000/" -TimeoutSec 5 -UseBasicParsing
    if ($html.Content -match "Loop Status") {
        Write-Host "✅ Dashboard HTML contains 'Loop Status' section" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Dashboard HTML loaded but 'Loop Status' not found" -ForegroundColor Yellow
    }

    if ($html.Content -match "loadLoopStatus") {
        Write-Host "✅ JavaScript function 'loadLoopStatus' found" -ForegroundColor Green
    } else {
        Write-Host "❌ JavaScript function 'loadLoopStatus' NOT found" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Failed to load dashboard HTML: $_" -ForegroundColor Red
}
Write-Host ""

# Test 5: Check runtime.json file
Write-Host "[5/6] Checking runtime.json file..."
$runtimeFile = "state\runtime.json"
if (Test-Path $runtimeFile) {
    $runtimeJson = Get-Content $runtimeFile | ConvertFrom-Json
    Write-Host "✅ runtime.json exists" -ForegroundColor Green
    Write-Host "   Loop Interval: $($runtimeJson.loop_interval_seconds)s"
    Write-Host "   Last Loop: $($runtimeJson.last_loop_start)"
} else {
    Write-Host "❌ runtime.json NOT found" -ForegroundColor Red
}
Write-Host ""

# Test 6: Summary
Write-Host "[6/6] Summary..."
Write-Host "================================================"
Write-Host "Dashboard URL: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Test Page: file:///$((Get-Location).Path)/test_dashboard_loop_status.html" -ForegroundColor Cyan
Write-Host ""
Write-Host "If loop status is not displaying in the dashboard:"
Write-Host "1. Open browser developer console (F12)"
Write-Host "2. Check for JavaScript errors"
Write-Host "3. Verify /runtime endpoint in Network tab"
Write-Host "4. Check browser console for 'loadLoopStatus' errors"
Write-Host "================================================"
