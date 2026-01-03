# Alpaca Endpoint Verification Tool
# Tests both Trading API and Data API endpoints to verify correct configuration

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("paper", "live")]
    [string]$Mode = "paper"
)

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  Alpaca Endpoint Verification" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $Mode" -ForegroundColor Yellow
Write-Host ""

# Load environment variables from .env file
$envFile = Join-Path $PSScriptRoot "..\\.env"
if (Test-Path $envFile) {
    Write-Host "Loading .env file..." -ForegroundColor Gray
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Get credentials based on mode
if ($Mode -eq "live") {
    $ApiKey = $env:ALPACA_LIVE_KEY_ID
    $SecretKey = $env:ALPACA_LIVE_SECRET_KEY
    if (-not $ApiKey) { $ApiKey = $env:ALPACA_API_KEY }
    if (-not $SecretKey) { $SecretKey = $env:ALPACA_SECRET_KEY }
    $TradingBaseUrl = if ($env:ALPACA_TRADING_BASE_URL) { $env:ALPACA_TRADING_BASE_URL } else { "https://api.alpaca.markets" }
} else {
    $ApiKey = $env:ALPACA_PAPER_KEY_ID
    $SecretKey = $env:ALPACA_PAPER_SECRET_KEY
    if (-not $ApiKey) { $ApiKey = $env:ALPACA_API_KEY }
    if (-not $SecretKey) { $SecretKey = $env:ALPACA_SECRET_KEY }
    $TradingBaseUrl = if ($env:ALPACA_TRADING_BASE_URL) { $env:ALPACA_TRADING_BASE_URL } else { "https://paper-api.alpaca.markets" }
}

$DataBaseUrl = if ($env:ALPACA_DATA_BASE_URL) { $env:ALPACA_DATA_BASE_URL } else { "https://data.alpaca.markets" }

# Check credentials
if (-not $ApiKey -or -not $SecretKey) {
    Write-Host "ERROR: API credentials not found" -ForegroundColor Red
    Write-Host "Please set environment variables:" -ForegroundColor Yellow
    if ($Mode -eq "paper") {
        Write-Host "  ALPACA_PAPER_KEY_ID" -ForegroundColor Yellow
        Write-Host "  ALPACA_PAPER_SECRET_KEY" -ForegroundColor Yellow
    } else {
        Write-Host "  ALPACA_LIVE_KEY_ID" -ForegroundColor Yellow
        Write-Host "  ALPACA_LIVE_SECRET_KEY" -ForegroundColor Yellow
    }
    exit 1
}

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Trading Base URL: $TradingBaseUrl" -ForegroundColor White
Write-Host "  Data Base URL: $DataBaseUrl" -ForegroundColor White
Write-Host "  API Key: $($ApiKey.Substring(0, 8))..." -ForegroundColor White
Write-Host ""

# Test Trading API
Write-Host "[1/2] Testing Trading API endpoint..." -ForegroundColor Yellow
Write-Host "  URL: $TradingBaseUrl/v2/account" -ForegroundColor Gray

$tradingHeaders = @{
    "APCA-API-KEY-ID" = $ApiKey
    "APCA-API-SECRET-KEY" = $SecretKey
}

try {
    $accountResponse = Invoke-RestMethod -Uri "$TradingBaseUrl/v2/account" -Headers $tradingHeaders -Method Get -ErrorAction Stop
    Write-Host "  [OK] Trading API responded successfully" -ForegroundColor Green
    Write-Host "  Account ID: $($accountResponse.account_number)" -ForegroundColor Green
    Write-Host "  Status: $($accountResponse.status)" -ForegroundColor Green
    Write-Host "  Buying Power: `$$($accountResponse.buying_power)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Trading API request failed" -ForegroundColor Red
    Write-Host "  Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test Data API
Write-Host "[2/2] Testing Data API endpoint..." -ForegroundColor Yellow
Write-Host "  URL: $DataBaseUrl/v2/stocks/AAPL/trades/latest" -ForegroundColor Gray

$dataHeaders = @{
    "APCA-API-KEY-ID" = $ApiKey
    "APCA-API-SECRET-KEY" = $SecretKey
}

try {
    $tradeResponse = Invoke-RestMethod -Uri "$DataBaseUrl/v2/stocks/AAPL/trades/latest" -Headers $dataHeaders -Method Get -ErrorAction Stop
    Write-Host "  [OK] Data API responded successfully" -ForegroundColor Green
    Write-Host "  Symbol: $($tradeResponse.symbol)" -ForegroundColor Green
    Write-Host "  Latest Trade Price: `$$($tradeResponse.trade.p)" -ForegroundColor Green
    Write-Host "  Latest Trade Time: $($tradeResponse.trade.t)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Data API request failed" -ForegroundColor Red
    Write-Host "  Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  Verification Complete" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: alpaca-py TradingClient automatically appends /v2 to the trading base URL" -ForegroundColor Gray
Write-Host "      StockHistoricalDataClient uses the data base URL directly" -ForegroundColor Gray
Write-Host ""
