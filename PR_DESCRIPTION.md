# Pull Request: Fix fractional orders and add cancel-open-orders preflight

## Summary

This PR fixes critical issues and improves Alpaca API integration:
1. **Fractional order submission bug** - Prevents "invalid literal for int()" errors when submitting fractional quantities
2. **Insufficient qty available errors** - Adds automatic order cancellation to prevent stale orders from blocking new trades
3. **API endpoint configuration** - Properly separates Trading API and Data API endpoints for correct alpaca-py SDK usage

## Changes

### 🔧 Fractional Order Support
- **Fixed**: `AlpacaBroker.submit_order()` now handles fractional quantities correctly
  - Fractional BUY market orders: use `notional` parameter (required by Alpaca API)
  - Fractional LIMIT orders: use `float(qty)` parameter
  - Whole share orders: use `int(qty)` parameter
- **Detection**: Uses `Decimal` arithmetic to reliably detect fractional orders
- **Result**: No more "invalid literal for int() with base 10: '0.208'" errors

### 🛡️ Cancel Open Orders Feature
- **New CLI flag**: `--cancel-open-orders`
- **Purpose**: Cancels all open orders before each paper trading run
- **Benefit**: Prevents "insufficient qty available for order" errors from stale orders
- **Implementation**:
  - Added `cancel_all_open_orders()` method to Broker interface
  - Implemented in both MockBroker and AlpacaBroker
  - Integrated into `run_paper_mode()` startup sequence
- **Safety**: Only active in paper mode with non-dry-run

### 🖥️ Task Scheduler Automation
- **New script**: `tools/setup_paper_trading_task.ps1`
- **Schedules**: Hourly runs during market hours (Mon-Fri, 09:35-15:35 EST)
- **Command**: `python.exe -m src.app.runner --mode paper --cancel-open-orders`
- **Features**:
  - Uses venv Python
  - Runs as logged-in user with highest privileges
  - Logs to `logs/paper_live_stdout.log` and `logs/paper_live_stderr.log`
  - Includes easy setup/removal batch files

### 🌐 API Endpoint Configuration
- **Separated endpoints**: Trading API and Data API now use distinct base URLs
- **Environment variables**:
  - `ALPACA_TRADING_BASE_URL` - For TradingClient (SDK appends /v2 automatically)
  - `ALPACA_DATA_BASE_URL` - For StockHistoricalDataClient
- **Implementation**:
  - `AlpacaBroker` uses `url_override` parameter for TradingClient
  - `AlpacaDataProvider` uses `url_override` parameter for StockHistoricalDataClient
  - Proper separation ensures data requests don't use trading endpoint
- **Startup diagnostics**: Shows both endpoints and credential status at startup
- **Verification tool**: `tools/verify_endpoints.ps1` tests both APIs
- **Default URLs**:
  - Paper: `https://paper-api.alpaca.markets` (trading), `https://data.alpaca.markets` (data)
  - Live: `https://api.alpaca.markets` (trading), `https://data.alpaca.markets` (data)

### ✅ Tests & Documentation
- **Tests**: Added 6 new tests for fractional orders and order cancellation
- **All tests passing**: 360 tests pass
- **Documentation**: Updated `docs/ARCHITECTURE.md` per Spec Sync Rule
- **Coverage**: Fractional buy/sell, limit orders, whole shares, and cancellation

## Files Changed

- `src/broker/base.py` (+119/-28): Fractional order logic and cancel method
- `src/app/runner.py` (+31/-5): CLI flag and integration
- `tests/test_broker.py` (+90/-0): New fractional order tests
- `tests/test_loop_runner.py` (+6/-2): Updated mocks for new parameter
- `docs/ARCHITECTURE.md` (+11/-0): Documented new behavior
- `tools/setup_paper_trading_task.ps1` (+165/-0): New automation script
- `tools/setup_paper_task.cmd` (+4/-0): Easy setup wrapper
- `tools/remove_paper_task.cmd` (+4/-0): Easy removal wrapper

## Testing

```bash
# Code formatting and linting
python -m ruff format .  # ✓ 61 files unchanged

# Test suite
.venv/Scripts/python.exe -m pytest -q  # ✓ 360 passed, 1 warning
```

## Usage Examples

### Manual paper trading with order cancellation
```bash
python -m src.app.runner --mode paper --cancel-open-orders
```

### Set up automated hourly paper trading (Windows)
```bash
# Double-click or run from admin PowerShell:
tools\setup_paper_task.cmd

# Or directly:
powershell -ExecutionPolicy Bypass -File tools\setup_paper_trading_task.ps1
```

### Remove automated task
```bash
tools\remove_paper_task.cmd
```

## Safety Notes

- All changes maintain existing behavior when `--cancel-open-orders` is not used
- Fractional order detection uses Decimal arithmetic to avoid float precision issues
- Order cancellation only runs in paper mode (not live)
- Task scheduler requires explicit user setup (not automatic)
- No Alpaca API keys are printed or logged

## Related Issues

Fixes the following observed errors:
- `ValueError: invalid literal for int() with base 10: '0.208'`
- `insufficient qty available for order`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
