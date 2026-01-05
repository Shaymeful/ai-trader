# Alpaca Endpoint Configuration Changes

## Summary
Updated the codebase to properly handle separate Alpaca Trading API and Data API endpoints, ensuring correct usage of alpaca-py SDK's `url_override` parameter.

## Changes Made

### 1. Configuration (`src/app/config.py`)
- **Added two new fields** to `Config` model:
  - `alpaca_trading_base_url`: For TradingClient (alpaca-py appends /v2 automatically)
  - `alpaca_data_base_url`: For StockHistoricalDataClient
- **Removed**: `alpaca_base_url` (replaced by the two new fields)
- **Updated** `get_alpaca_credentials()` to return 4 values: `(api_key, secret_key, trading_base_url, data_base_url)`
- **Added environment variable support**:
  - `ALPACA_TRADING_BASE_URL` (defaults: paper=`https://paper-api.alpaca.markets`, live=`https://api.alpaca.markets`)
  - `ALPACA_DATA_BASE_URL` (default: `https://data.alpaca.markets`)

### 2. Broker (`src/broker/base.py`)
- **Updated** `AlpacaBroker.__init__()` signature:
  - Changed parameter from `base_url` to `trading_base_url`
  - Now passes `url_override=trading_base_url` to `TradingClient`
  - TradingClient automatically appends `/v2` to the URL

### 3. Data Provider (`src/data/provider.py`)
- **Updated** `AlpacaDataProvider.__init__()` signature:
  - Changed parameter from `base_url` to `data_base_url`
  - Now passes `url_override=data_base_url` to `StockHistoricalDataClient`

### 4. Runner (`src/app/runner.py`)
- **Added startup diagnostics** showing:
  - Trading API URL with note that TradingClient appends /v2
  - Data API URL
  - Credential status (masked)
- **Updated** all `AlpacaBroker` instantiations to use `config.alpaca_trading_base_url`
- **Updated** print statements to show `data_url` instead of `base_url`

### 5. Main Module (`src/app/__main__.py`)
- **Updated** all `AlpacaBroker` instantiations:
  - Changed `base_url` parameter to `trading_base_url`
  - Changed references from `config.alpaca_base_url` to `config.alpaca_trading_base_url`
- **Updated** all `AlpacaDataProvider` instantiations:
  - Changed `base_url` parameter to `data_base_url`
  - Changed references to use `config.alpaca_data_base_url`

### 6. Environment Configuration (`.env.example`)
- **Added** `ALPACA_TRADING_BASE_URL` with explanation
- **Added** `ALPACA_DATA_BASE_URL`
- **Removed** old `ALPACA_BASE_URL` variable

### 7. New Verification Tool (`tools/verify_endpoints.ps1`)
- **Created** PowerShell script to verify both endpoints
- **Tests**:
  - Trading API: `/v2/account` endpoint
  - Data API: `/v2/stocks/AAPL/trades/latest` endpoint
- **Shows**: Resolved URLs, status codes, and sample response data
- **Usage**: `powershell -ExecutionPolicy Bypass -File tools\verify_endpoints.ps1`

## Key Behaviors

### alpaca-py SDK Behavior
1. **TradingClient**:
   - Accepts `url_override` parameter
   - Automatically appends `/v2` to the base URL
   - Example: `https://paper-api.alpaca.markets` → `https://paper-api.alpaca.markets/v2`

2. **StockHistoricalDataClient**:
   - Accepts `url_override` parameter
   - Uses the data URL directly for historical data requests
   - Default: `https://data.alpaca.markets`

### Default URLs
- **Paper Trading**:
  - Trading: `https://paper-api.alpaca.markets`
  - Data: `https://data.alpaca.markets`
- **Live Trading**:
  - Trading: `https://api.alpaca.markets`
  - Data: `https://data.alpaca.markets`

## Testing

### Dry-Run Test
```bash
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --once --dry-run
```

**Expected output includes**:
```
API Endpoint Configuration:
  Trading API: https://paper-api.alpaca.markets (TradingClient appends /v2)
  Data API: https://data.alpaca.markets
  Credentials: Present (masked)

Using MockBroker (dry-run or no credentials)
...
Orders placed: 0
```

### Endpoint Verification
```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_endpoints.ps1
```

**Expected output**:
```
[1/2] Testing Trading API endpoint...
  URL: https://paper-api.alpaca.markets/v2/account
  [OK] Trading API responded successfully

[2/2] Testing Data API endpoint...
  URL: https://data.alpaca.markets/v2/stocks/AAPL/trades/latest
  [OK] Data API responded successfully
```

## Migration Guide

### If you have existing `.env` file:
1. Replace `ALPACA_BASE_URL` with:
   ```
   ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
   ALPACA_DATA_BASE_URL=https://data.alpaca.markets
   ```
2. Run verification: `tools\verify_endpoints.ps1`
3. Test with dry-run: `.\.venv\Scripts\python.exe -m src.app.runner --mode paper --once --dry-run`

### For custom endpoint configurations:
Set environment variables:
```powershell
$env:ALPACA_TRADING_BASE_URL = "https://your-trading-endpoint"
$env:ALPACA_DATA_BASE_URL = "https://your-data-endpoint"
```

## Benefits
- ✅ Clear separation between Trading and Data API endpoints
- ✅ Proper use of alpaca-py SDK's `url_override` parameter
- ✅ No manual `/v2` appending needed (SDK handles it)
- ✅ Startup diagnostics show exactly what URLs are being used
- ✅ Verification tool confirms endpoints are working
- ✅ Maintains backward compatibility with default URLs
