# AI Trader

A paper trading bot with SMA crossover strategy, built with clean architecture and comprehensive risk management.

## Features

- **Paper Trading Only**: Safe testing environment with no real money at risk
- **Risk Management**: Position limits, order size constraints, daily loss limits, symbol allowlist
- **SMA Crossover Strategy**: Simple Moving Average crossover with configurable periods
- **Market Hours Guard**: Only trades during configured market hours
- **Mock Mode**: Runs completely offline with simulated data (no API keys needed)
- **Alpaca Integration**: Ready for Alpaca paper trading (requires API keys)
- **Comprehensive Logging**: Structured logs in `logs/` directory
- **Trade History**: CSV records in `out/trades.csv`

## Architecture

```
src/
├── app/          # Main application runner
├── data/         # Market data providers (Mock, Alpaca)
├── signals/      # Trading strategies
├── risk/         # Risk management
└── broker/       # Order execution (Mock, Alpaca)
```

## RUN

### Setup

1. **Create virtual environment** (Python 3.12+ required):
```bash
python -m venv .venv
```

2. **Activate virtual environment**:
```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment** (optional):
```bash
# Copy example config
copy .env.example .env

# Edit .env with your settings
# For mock mode (offline), no changes needed
```

### Run Tests

```bash
pytest
```

This will run 35+ tests covering:
- Risk management (position limits, loss limits, quantity checks)
- Trading strategy (SMA crossover, market hours)
- Data providers (mock data generation)
- Brokers (order execution)
- Models (data validation)
- Configuration (environment loading)

### Run Bot

```bash
python __main__.py
```

Or alternatively:

```bash
python -m src.app
```

The bot will:
1. Load configuration from `.env` (or use defaults)
2. Initialize in **mock mode** (offline, no API keys required)
3. Generate simulated market data
4. Run SMA crossover strategy
5. Execute paper trades through mock broker
6. Write logs to `logs/`
7. Write trades to `out/trades.csv`
8. Write summary to `out/summary.json`

### Output

After running, check:

- **Logs**: `logs/trading_<timestamp>.log` - Detailed execution logs
- **Trades**: `out/trades.csv` - All executed trades
- **Summary**: `out/summary.json` - Session summary with P&L

Example `out/trades.csv`:
```csv
timestamp,symbol,side,quantity,price,order_id,reason
2024-01-15T10:30:00,AAPL,buy,10,180.50,uuid-123,SMA golden cross: fast=181.20 > slow=179.80
2024-01-15T14:45:00,AAPL,sell,10,185.25,uuid-456,SMA death cross: fast=184.50 < slow=185.10
```

## Configuration

All settings can be configured via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `mock` | Trading mode: `mock` or `alpaca` |
| `MAX_POSITIONS` | `5` | Maximum concurrent positions |
| `MAX_ORDER_QUANTITY` | `100` | Maximum shares per order |
| `MAX_DAILY_LOSS` | `1000` | Maximum daily loss threshold ($) |
| `ALLOWED_SYMBOLS` | `AAPL,MSFT,GOOGL,AMZN,TSLA` | Comma-separated symbols |
| `SMA_FAST_PERIOD` | `10` | Fast SMA period (bars) |
| `SMA_SLOW_PERIOD` | `30` | Slow SMA period (bars) |
| `LOG_LEVEL` | `INFO` | Logging level |

### Alpaca Mode (Optional)

To use Alpaca paper trading instead of mock mode:

1. Get free paper trading account at [alpaca.markets](https://alpaca.markets)
2. Generate API keys
3. Install alpaca-py: `pip install alpaca-py`
4. Set environment variables:
   ```bash
   MODE=alpaca
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ```

## Safety

- **Paper Trading Only**: This bot does NOT support live trading
- **Risk Checks**: All orders pass through RiskManager validation
- **Position Limits**: Enforced at strategy and risk level
- **Loss Limits**: Daily loss threshold prevents runaway losses
- **Symbol Allowlist**: Only configured symbols can be traded
- **Market Hours**: Only trades during configured hours (no after-hours)

## Testing

Run tests with coverage:

```bash
pytest -v
pytest --cov=src tests/
```

Test files:
- `tests/test_risk.py` - Risk management tests
- `tests/test_strategy.py` - Strategy logic tests
- `tests/test_broker.py` - Broker execution tests
- `tests/test_data.py` - Data provider tests
- `tests/test_models.py` - Data model tests
- `tests/test_config.py` - Configuration tests

All tests run offline without network access.

## Development

Key files:
- `src/app/__main__.py` - Main entry point
- `src/app/config.py` - Configuration loader
- `src/app/models.py` - Pydantic data models
- `src/risk/manager.py` - Risk management logic
- `src/signals/strategy.py` - SMA crossover strategy
- `src/data/provider.py` - Data provider implementations
- `src/broker/base.py` - Broker implementations

## License

MIT
