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

## Startup Reconciliation

### Purpose
On startup, the bot reconciles its local state with the broker's actual state to ensure consistency after crashes, restarts, or manual interventions.

### Reconciliation Process
1. **Open Orders Sync**: Queries broker for open orders and updates `state.json` to match
   - Adds any broker orders not in local state
   - Removes any local orders no longer open at broker
   - Logs all additions and removals

2. **Position Sync**: Queries broker for current positions and updates risk manager
   - Syncs quantities and average prices for matching positions
   - Adds new positions found at broker
   - Removes local positions not at broker
   - Logs all changes

### CLI Support
- Runs automatically before every trading loop
- `--reconcile-only` flag: Perform reconciliation and exit (no trading loop)
  - Prints summary to stdout
  - Useful for diagnostics and state verification

### Safety
- No orders are canceled or modified during reconciliation
- Only reads broker state and updates local tracking
- Handles broker API errors gracefully (logs warnings, continues)

### Implementation
- `src/app/reconciliation.py`: Core reconciliation logic
- `Broker.get_open_orders()`: Returns set of client_order_ids
- `Broker.get_positions()`: Returns dict of symbol -> (quantity, avg_price)
- Integrated into `run_trading_loop()` after broker/risk manager initialization

---

## CLI Flags
- `--mode {dry-run,paper,live}`
- `--preflight`
- `--once`
- `--max-iterations` (alias: `--iterations`) - Controls trading loop iterations
- `--compute-after-hours`
- `--allow-after-hours-orders`
- `--paper-test-order SYMBOL QTY`
- `--reconcile-only` - Reconcile state with broker and exit (no trading loop)

### Flag Aliases
- `--iterations` works identically to `--max-iterations`
- Both flags accept an integer value and control the number of trading loop iterations
- Default: 5 iterations if not specified

---

## Decision Logging

The trading loop logs comprehensive per-symbol decision information:

### Decision Summary Format
Each symbol processed includes a "Decision Summary" with:
- **Decision**: BUY / SELL / HOLD
- **SMA Signal**: Reason or status (crossover detected, no crossover, insufficient data)
- **SMA Crossover**: Fast SMA vs Slow SMA comparison (e.g., "Fast ($183.50) > Slow ($180.20)")
- **Position Status**: Long or Flat
- **Final Action**: Actual outcome (order submitted, dry-run, or HOLD with reason)

### Gate Blocking Logs
When a signal is generated but blocked by a gate:
- **Gate BLOCKED**: Logs the specific gate (market hours, risk check, idempotency, quantity)
- **Final Action**: HOLD (blocked by gate)

### Examples
- `Decision: BUY` → `Gate BLOCKED: Market closed` → `Final Action: HOLD (market hours gate)`
- `Decision: HOLD` → `SMA Signal: No crossover detected` → `Final Action: HOLD (no signal)`
- `Decision: BUY` → `Final Action: BUY (order submitted)` or `BUY (dry-run)`

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
