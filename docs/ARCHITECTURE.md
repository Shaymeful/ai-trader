# AI-Trader Architecture & Feature Log

This document tracks **intentional architectural decisions**, supported features,
and safety constraints so future changes (human or AI-assisted) do not break
established behavior.

---

## 📋 PR Checklist: Spec Sync Requirement

**Before merging any PR that changes the following, this file MUST be updated in the same commit:**

- [ ] Runtime behavior or trading logic
- [ ] CLI flags or arguments
- [ ] Configuration (env vars, config file structure)
- [ ] Broker or data provider interfaces
- [ ] Risk controls or safety gates
- [ ] Order execution logic or pipeline
- [ ] Output formats or logging

**Verification steps:**
1. Does the PR touch any of the areas above?
2. If yes, are changes documented in the relevant section(s) below?
3. Are new flags added to the CLI Flags section?
4. Are new safety gates added to the Safety Gates section?

**This is a MANDATORY requirement. PRs are incomplete without docs updates.**

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

### Core Flags
- `--mode {dry-run,paper,live}` - Trading mode
- `--preflight` - Validate configuration and connectivity
- `--once` - Run exactly 1 trading loop iteration
- `--max-iterations N` (alias: `--iterations`) - Controls trading loop iterations (default: 5)
- `--compute-after-hours` - Fetch bars and compute indicators when market closed
- `--allow-after-hours-orders` - Allow order submission when market closed (paper/dry-run only)
- `--paper-test-order SYMBOL QTY` - Submit single test MARKET order in paper mode and exit
- `--test-order` - Submit test LIMIT buy (1 share) for first symbol in LIVE mode and exit
- `--reconcile-only` - Reconcile state with broker and exit (no trading loop)

### Order Management Flags
Order management commands support all trading modes (mock, paper, live) with mode-appropriate safety gates.

**Commands:**
- `--list-open-orders` - List all open orders and exit
- `--cancel-order-id ORDER_ID` - Cancel order by broker order ID and exit
- `--cancel-client-order-id CLIENT_ORDER_ID` - Cancel order by client order ID and exit
- `--replace-order-id ORDER_ID --limit-price PRICE [--qty QUANTITY]` - Replace/modify order and exit

**Mode Behavior:**
- **mock/dry-run**: Uses MockBroker (no network, no credentials required, no safety gates)
- **paper**: Uses Alpaca paper API (requires API keys, no safety gates)
- **live**: Uses Alpaca live API (requires API keys + triple safety gates)

**Exit Codes:**
- `0` = Success
- `1` = User error (missing params, safety gate failure)
- `2` = Network/broker error

**Examples:**
```bash
# Mock mode - no credentials needed, safe for day-to-day testing
python -m src.app --mode dry-run --list-open-orders
python -m src.app --mode dry-run --cancel-order-id test-123
python -m src.app --mode dry-run --replace-order-id test-123 --limit-price 150.50

# Paper mode - requires API keys, no safety gates
python -m src.app --mode paper --list-open-orders
python -m src.app --mode paper --cancel-order-id abc-123

# Live mode - requires API keys + triple safety gates
python -m src.app --mode live --i-understand-live-trading --list-open-orders
python -m src.app --mode live --i-understand-live-trading --cancel-order-id abc-123
python -m src.app --mode live --i-understand-live-trading \
  --replace-order-id abc-123 --limit-price 150.50
```

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

### Live Trading Mode Gates
All operations involving the live Alpaca API require **triple authentication**:
1. `--mode live` CLI flag
2. `--i-understand-live-trading` CLI flag
3. `ENABLE_LIVE_TRADING=true` environment variable

These gates apply to:
- Normal trading loop (`run_trading_loop`)
- Test order submission (`--test-order`)
- Order management commands (`--list-open-orders`, `--cancel-order-id`, `--cancel-client-order-id`, `--replace-order-id`)

**Fail-Fast Behavior:**
- Gates are checked **before any file I/O, logging, or API calls**
- Missing safety flags cause immediate `ValueError` with clear error message
- No partial operations - either all gates pass or operation aborts immediately

### Order Management Safety Gates
Order management commands enforce mode-appropriate safety gates:

**Mock/Dry-Run Mode:**
- No safety gates required
- Uses MockBroker (no network, no credentials)
- Safe for day-to-day testing and development

**Paper Mode:**
- Requires API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- No triple safety gates (no --i-understand-live-trading or ENABLE_LIVE_TRADING required)
- Uses Alpaca paper API endpoint

**Live Mode:**
- Requires triple authentication (same as trading loop):
  1. `--mode live` (must be live Alpaca API endpoint)
  2. `--i-understand-live-trading` flag
  3. `ENABLE_LIVE_TRADING=true` env var
  4. API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- Fail-fast before any I/O or API calls

**Additional Requirements (all modes):**
- `--replace-order-id`: Requires `--limit-price` parameter
- `--replace-order-id`: Validates replacement through RiskManager (notional/exposure checks)
- Cancel operations: Verify order status after cancellation attempt (best effort)
- Replace operations: Use Alpaca replace endpoint if available, fallback to cancel+new

### Other Safety Gates
- After-hours order submission blocked by default (use `--allow-after-hours-orders` in paper/dry-run only)
- Paper test order cannot run in live mode
- Live mode cannot use `--allow-after-hours-orders`

---

## Cost-Aware Trading & Execution Controls

The system includes explicit mechanisms to model, limit, and diagnose trading costs that arise from spreads and execution quality.

### Quote Model
A `Quote` abstraction is used during order evaluation and submission:
- **bid**: best bid price
- **ask**: best ask price
- **last**: last traded price
- **mid**: midpoint of bid/ask
- **spread**: ask − bid
- **spread_bps**: spread expressed in basis points

Quotes are obtained from the active broker via `Broker.get_quote(symbol)`.

### Spread-Aware Order Logic
Before any order is placed:
- The current spread is evaluated
- Orders are **blocked** if `spread_bps > max_spread_bps`
- When enabled, orders are placed as **LIMIT orders** using spread-aware pricing:
  - BUY: `min(ask, mid + spread × 0.25)`
  - SELL: `max(bid, mid − spread × 0.25)`

This logic is enforced centrally in the order pipeline and applies to all trading modes.

### Minimum Edge Threshold
The system supports an optional minimum edge requirement:
- Configured via `min_edge_bps`
- For BUY orders, required price improvement must be negative and exceed the threshold
- For SELL orders, required price improvement must be positive and exceed the threshold
- This prevents trades where estimated execution costs outweigh expected benefit

### Slippage Tracking
Each order records:
- Expected price at submission
- Actual fill price
- Absolute slippage
- Slippage in basis points
- Spread at time of submission

These fields are persisted in trade records and used during reconciliation and reporting.

### Cost Diagnostics
When enabled, the system automatically generates a per-run cost report summarizing:
- Total trades
- Aggregate spread cost
- Aggregate slippage (absolute and signed)
- Average spread at submission
- Worst observed slippage

This report is written to disk alongside other run outputs for post-run analysis.

### CLI Flags
Relevant flags include:
- `--use-limit-orders / --no-limit-orders`
- `--max-spread-bps`
- `--min-edge-bps`
- `--cost-diagnostics / --no-cost-diagnostics`

---

## Symbol Eligibility & Liquidity Guardrails

The system implements comprehensive symbol eligibility checks to prevent trading of illiquid, penny-stock, or otherwise unsuitable symbols.

### Purpose
Block orders for symbols that fail safety or quality criteria:
- Prevent trading penny stocks (low price)
- Avoid illiquid symbols (low volume)
- Enforce whitelist/blacklist controls
- Require valid market quotes

### Enforcement Location
All eligibility checks are enforced **centrally in the order pipeline** (`src/app/order_pipeline.py`) during `submit_signal_order()`, immediately after risk checks and before spread/cost checks.

This ensures **every order attempt** passes eligibility requirements before broker submission.

### Eligibility Checks (in order)

1. **Whitelist Check** (if configured)
   - If `symbol_whitelist` is non-empty, only listed symbols are allowed
   - Empty whitelist = allow all (no restriction)
   - **Reason format**: `"Blocked: symbol {SYMBOL} not in whitelist"`

2. **Blacklist Check** (always enforced if configured)
   - Symbols in `symbol_blacklist` are always blocked
   - **Blacklist wins over whitelist** (precedence rule)
   - **Reason format**: `"Blocked: symbol {SYMBOL} in blacklist"`

3. **Quote Requirement Check**
   - If `require_quote=true`, order requires valid bid/ask quote
   - Blocks if `bid <= 0` or `ask <= 0`
   - **Reason format**: `"Blocked: quote missing (require_quote=true)"`

4. **Price Range Check**
   - Uses quote mid price (or signal price as fallback)
   - Blocks if `price < min_price`
   - Blocks if `price > max_price`
   - **Reason format**: `"Blocked: price={PRICE} < min_price={MIN}"` or `"Blocked: price={PRICE} > max_price={MAX}"`

5. **Volume Check**
   - Fetches average daily volume via `DataProvider.get_avg_volume(symbol)`
   - Blocks if `avg_volume < min_avg_volume`
   - **Reason format**: `"Blocked: avg_volume={VOL} < min_avg_volume={MIN}"`

All checks log detailed warnings including measured values and configured limits.

### Data Sources

**Price**: Prefers quote mid price if available; falls back to signal price

**Volume**: Uses `DataProvider.get_avg_volume(symbol, lookback_days=20)`
- **MockDataProvider**: Returns deterministic volumes for known symbols (e.g., AAPL=50M, MSFT=30M), or 5M for unknown
- **AlpacaDataProvider**: Computes average from recent bars via base implementation

### Configuration

All parameters have conservative defaults to prevent accidental trading of unsuitable symbols:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_avg_volume` | 1,000,000 | Minimum average daily volume |
| `min_price` | $2.00 | Minimum price (penny stock threshold) |
| `max_price` | $1000.00 | Maximum price (sanity cap) |
| `require_quote` | true | Require valid bid/ask quote |
| `symbol_whitelist` | [] (empty) | Allowed symbols (empty = allow all) |
| `symbol_blacklist` | [] (empty) | Blocked symbols |

### CLI Flags
- `--min-avg-volume <int>` - Set minimum volume threshold
- `--min-price <float>` - Set minimum price
- `--max-price <float>` - Set maximum price
- `--require-quote / --no-require-quote` - Toggle quote requirement
- `--symbol-whitelist <comma-separated>` - Set whitelist (e.g., "AAPL,MSFT,GOOGL")
- `--symbol-blacklist <comma-separated>` - Set blacklist (e.g., "TSLA,GME")

### Precedence Rules
1. Blacklist always wins (blocks even if whitelisted)
2. If whitelist is non-empty, only whitelisted symbols pass
3. All other checks (quote, price, volume) apply to any symbol that passes lists
4. Eligibility runs **before** spread/edge checks to fail fast on ineligible symbols

### Testing
- Tests use deterministic mock data for reproducibility
- `tests/test_symbol_eligibility.py` covers all checks and precedence rules
- MockDataProvider returns fixed volumes for test symbols
- Tests use custom broker/provider classes to control quote and volume data

---

## Known Constraints
- Alpaca free tier uses IEX feed
- Minute bars require regular-session windowing
- Historical minute data must end at market close
