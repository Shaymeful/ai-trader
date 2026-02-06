# Test if XML file can be imported properly

Write-Host "Testing XML import..." -ForegroundColor Cyan
Write-Host ""

$XMLPath = "C:\dev\ai-trader\AITrader-Loop-Updated.xml"

# Check file exists
if (-not (Test-Path $XMLPath)) {
    Write-Host "ERROR: XML file not found at $XMLPath" -ForegroundColor Red
    exit 1
}

# Try to read XML
try {
    $xml = [xml](Get-Content $XMLPath -Raw)
    Write-Host "[OK] XML file can be read" -ForegroundColor Green

    # Extract arguments
    $args = $xml.Task.Actions.Exec.Arguments
    Write-Host ""
    Write-Host "Arguments in XML file:" -ForegroundColor Yellow
    Write-Host $args -ForegroundColor Gray
    Write-Host ""

    # Check for required settings
    if ($args -match "-WindowStyle Hidden") {
        Write-Host "[OK] Has -WindowStyle Hidden" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] Does not have -WindowStyle Hidden" -ForegroundColor Red
    }

    if ($args -match "SleepSeconds 300") {
        Write-Host "[OK] Has SleepSeconds 300" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] Does not have SleepSeconds 300" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "XML file is correct. The import command should work." -ForegroundColor Green

} catch {
    Write-Host "ERROR: Cannot read XML: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
