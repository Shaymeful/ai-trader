# AI-Trader Architecture & Feature Log

This document tracks **intentional architectural decisions**, supported features,
and safety constraints so future changes (human or AI-assisted) do not break
established behavior.

---

## Core Capabilities
- Alpaca paper trading support
- Live trading (explicit opt-in only)
- SMA crossover strategy
- Deterministic market data fetching
- Risk controls and safety gates

---

## Data Providers

### AlpacaDataProvider
- Uses alpaca-py `StockHistoricalDataClient`
- 1-minute bars via IEX feed
- Market-close windowing (most recent regular session at 16:00 ET)
- Weekend-safe rollback to last trading day
- Bar timestamps normalized to naive datetime
- Logs explicit diagnostics when no bars are returned

---

## Brokers

### AlpacaBroker
- Supports paper and live modes
- client_order_id used for idempotency
- Normalized order status mapping

---

## CLI Flags
- `--mode {dry-run,paper,live}`
- `--preflight`
- `--once`
- `--max-iterations` (alias: `--iterations`) - Controls trading loop iterations
- `--compute-after-hours`
- `--allow-after-hours-orders`
- `--paper-test-order SYMBOL QTY`

### Flag Aliases
- `--iterations` works identically to `--max-iterations`
- Both flags accept an integer value and control the number of trading loop iterations
- Default: 5 iterations if not specified

---

## Safety Gates
- Live trading requires explicit acknowledgment flag
- After-hours order submission blocked by default
- Paper test order cannot run in live mode

---

## Known Constraints
- Alpaca free tier uses IEX feed
- Minute bars require regular-session windowing
- Historical minute data must end at market close
