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
- **Fractional order support**:
  - For fractional BUY market orders (qty < 1 or has decimal places): uses `notional` parameter
  - For fractional LIMIT orders: uses `float(qty)` parameter (Alpaca accepts fractional qty for limits)
  - For whole share orders: uses `int(qty)` parameter
  - Detection: Uses `Decimal` arithmetic to check if `qty % 1 != 0` or `qty < 1`
  - Prevents "invalid literal for int()" errors when submitting fractional quantities

---

## Capital Allocation & Position Sizing

### Overview

The allocation engine distributes account capital across multiple strategies using **equity-based normalized weights** with deterministic netting for multi-strategy conflicts.

**Key Design Principles:**
- **Equity-based allocation**: Uses account equity (not buying_power) as the allocation base for risk management
- **Dynamic weight normalization**: Adjusts weights among enabled strategies to prevent allocation errors when strategies are added/removed
- **Fractional share support**: Supports decimal quantities where broker allows, otherwise rounds to whole shares
- **Deterministic netting**: Combines multi-strategy intents for same symbol using signed notionals
- **Centralized sizing**: Position sizing logic centralized in allocation module (not in strategies)
- **Backward compatibility**: Falls back to legacy equal-weight allocation if registry/broker unavailable

### Allocation Modes

#### Registry Mode (NEW - Equity-Based)

When StrategyRegistry + broker are available, uses equity-based allocation with normalized weights:

```python
# 1. Fetch account equity
account = broker.client.get_account()
equity = float(account.equity)  # e.g., $50,000

# 2. Get enabled strategies and compute normalized weights
# Config: Strategy A (weight=0.5, enabled), Strategy B (weight=0.3, enabled), Strategy C (weight=0.2, disabled)
enabled_weight_sum = 0.5 + 0.3 = 0.8
normalized_weights = {
    "A": 0.5 / 0.8 = 0.625 (62.5%),
    "B": 0.3 / 0.8 = 0.375 (37.5%)
}

# 3. Compute per-strategy budgets
budget_A = equity * 0.625 = $31,250
budget_B = equity * 0.375 = $18,750

# 4. Size each intent using conviction
# Strategy A has intent for AAPL with conviction=0.85
target_notional = budget_A * 0.85 = $26,562.50
# Apply per-strategy max_position_size if configured
if max_position_size:
    target_notional = min(target_notional, max_position_size)

# 5. Convert to shares
price_AAPL = $150
qty = target_notional / price_AAPL = 177.08 shares
# Round to int for final order: 177 shares
```

#### Legacy Mode (Backward Compatible)

When registry/broker unavailable, uses equal-weight allocation with max_positions_notional:

```python
# Equal weight across all strategies
num_strategies = 2
budget_per_strategy = max_positions_notional / num_strategies

# Simple aggregation: sum target quantities by symbol
for strategy, intents in strategy_intents.items():
    for intent in intents:
        aggregated_targets[symbol] += intent.target_quantity
```

### Weight Normalization

**Problem**: When strategies are enabled/disabled, configured weights may not sum to 1.0

**Solution**: Normalize weights dynamically among enabled strategies:

```python
normalized_weight_i = weight_i / sum(weights of enabled strategies)
```

**Example**:
- Strategy A: weight=0.5, enabled
- Strategy B: weight=0.3, enabled
- Strategy C: weight=0.2, disabled

Sum of enabled weights = 0.8
- Normalized A = 0.5 / 0.8 = 0.625 (62.5% of capital)
- Normalized B = 0.3 / 0.8 = 0.375 (37.5% of capital)

**Edge Case**: If all enabled strategies have weight=0, assign equal weights (1.0 / num_enabled)

### Netting Policy

**Purpose**: Combine multi-strategy intents for same symbol into single target position

**Algorithm**:
1. Convert each intent to signed notional:
   - `target_quantity > 0` → `+notional` (buy/long)
   - `target_quantity < 0` → `-notional` (sell/short)
   - `target_quantity = 0` → neutral (close position)

2. Sum notionals by symbol across all strategies:
   ```python
   net_notional = (Strategy_A_qty * price) + (Strategy_B_qty * price)
   ```

3. Determine final direction:
   - `net_notional > 0` → BUY intent
   - `net_notional < 0` → SELL intent
   - `net_notional = 0` → NEUTRAL (intents cancel out)

4. Convert net notional back to shares for final order

**Example**:
```python
# Strategy A: wants to hold 10 shares of AAPL (buy)
# Strategy B: wants to hold -5 shares of AAPL (sell short)
# Price: $150

notional_A = 10 * 150 = +$1,500
notional_B = -5 * 150 = -$750
net_notional = $1,500 + (-$750) = $750

# Final: BUY 5 shares of AAPL (net_notional / price = 750 / 150)
```

**Attribution**: Track which strategies contributed to each netted target for ledger audit trail

### Fractional Share Handling

**Broker Support Detection**:
- Fractional shares supported where Alpaca allows (typically liquid stocks)
- Detection: Check if broker accepts fractional qty in order submission

**Rounding Behavior**:
```python
# If fractional allowed:
qty = notional / price  # Keep fractional (e.g., 33.33 shares)

# If whole shares only:
qty = int(notional / price)  # Floor to whole shares (e.g., 33 shares)
```

**Implementation**: `allocation.compute_qty_from_notional(price, notional, allow_fractional)`

### Ledger Events

Allocation engine emits detailed events for audit trail:

**AllocationWeightsComputedEvent**:
- Total equity used
- Configured vs normalized weights
- Enabled strategy IDs

**StrategyBudgetComputedEvent** (per strategy):
- Strategy ID
- Equity
- Normalized weight
- Computed budget

**IntentSizedEvent** (per intent):
- Strategy ID
- Symbol
- Target quantity
- Conviction
- Budget
- Computed notional
- Price
- Candidate ID (if from candidate system)

**NettedSymbolTargetEvent** (per symbol):
- Symbol
- Net notional
- Net quantity
- Final direction (buy/sell/neutral)
- Contributing strategies
- Price

**WarningEquityUnavailableEvent**:
- Reason equity was unavailable
- Fallback mode used

### Implementation Files

**Core Module**: `src/app/allocation.py`
- `get_total_equity(account_state)` - Extract equity from account
- `compute_weight_summary(strategies)` - Normalize weights among enabled strategies
- `compute_strategy_budget(equity, normalized_weight)` - Compute per-strategy budget
- `compute_target_notional(budget, conviction, risk_limits)` - Size intent using conviction
- `compute_qty_from_notional(price, notional, allow_fractional)` - Convert notional to shares
- `net_intents_by_symbol(intents, market_data, strategy_map)` - Net multi-strategy intents

**Integration**: `src/app/allocator.py`
- `Allocator` class with dual-mode support (registry + legacy)
- `_allocate_with_registry()` - New equity-based allocation
- `_allocate_legacy()` - Backward-compatible equal-weight allocation
- Accepts optional `registry`, `broker`, `ledger` parameters

**Ledger Events**: `src/app/ledger.py`
- `AllocationWeightsComputedEvent`
- `StrategyBudgetComputedEvent`
- `IntentSizedEvent`
- `NettedSymbolTargetEvent`
- `WarningEquityUnavailableEvent`

**Tests**: `tests/test_allocation.py`
- 28 unit tests covering:
  - Equity extraction
  - Weight normalization (including edge cases)
  - Budget computation
  - Notional sizing with risk limits
  - Quantity rounding (fractional vs whole shares)
  - Multi-strategy netting
  - Attribution tracking

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
- `--dry-run` - Run full pipeline (signals + risk checks + pricing) but never submit orders
  - **Market-hours gating behavior**: In DryRun mode, market-hours checks apply ONLY to order submission (which is skipped anyway). The bot still:
    - Loads candidates from snapshot
    - Computes signals and strategy intents
    - Runs allocation and position sizing logic
    - Logs all events to ledger (JSONL format)
    - Updates dashboard with latest data
  - **Use case**: Testing full trading logic after market close without submitting orders. Validates end-to-end pipeline including candidate evaluation, signal generation, allocation, and risk checks.
  - **Status file**: Writes success/failure to `logs/loop_status.log` with timestamp, orders placed (always 0 in DryRun), and strategy weights.
- `--preflight` - Validate configuration and connectivity
- `--once` - Run exactly 1 trading loop iteration
- `--max-iterations N` (alias: `--iterations`) - Controls trading loop iterations (default: 5)
- `--compute-after-hours` - Fetch bars and compute indicators when market closed
- `--allow-after-hours-orders` - Allow order submission when market closed (paper/dry-run only)
- `--paper-test-order SYMBOL QTY` - Submit single test MARKET order in paper mode and exit
- `--test-order` - Submit test LIMIT buy (1 share) for first symbol in LIVE mode and exit
- `--reconcile-only` - Reconcile state with broker and exit (no trading loop)
- `--status` - Print operator-facing status/metrics snapshot and exit (no trading loop)
- `--check-env` - Check environment configuration and credentials without running bot

### Risk Control Flags
- `--max-daily-loss <dollars>` - Maximum daily loss threshold (default: 500)
- `--max-session-loss <dollars>` - Maximum session loss threshold, resets on restart (default: disabled)
- `--max-order-notional <dollars>` - Maximum order notional value (default: 500)
- `--max-positions-notional <dollars>` - Maximum total positions exposure (default: 10000)

### Order Management Flags
Order management commands support all trading modes (mock, paper, live) with mode-appropriate safety gates.

**Commands:**
- `--list-open-orders` - List all open orders and exit
- `--cancel-order-id ORDER_ID` - Cancel order by broker order ID and exit
- `--cancel-client-order-id CLIENT_ORDER_ID` - Cancel order by client order ID and exit
- `--replace-order-id ORDER_ID --limit-price PRICE [--qty QUANTITY]` - Replace/modify order and exit
- `--cancel-open-orders` - Cancel all open orders before running (paper mode only, requires non-dry-run)
  - Prevents "insufficient qty available" errors caused by stale open orders
  - Runs automatically at start of each trading loop iteration when enabled
  - Returns count of orders canceled and logs to stdout
  - Integrated into `run_paper_mode()` after broker initialization

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

### Utility Commands

**Selector Module:**
- `python -m src.app.selector.run_once` - Run RSS selector once and generate candidates
  - Fetches RSS feeds from `config/selector.yaml`
  - Generates candidates → `out/selector/snapshot.json`
  - Logs events → `out/selector/events.jsonl`
  - Outputs summary to console (candidates count by action and sector)
  - Use for manual candidate generation or testing RSS feed configuration
  - Can be scheduled via Windows Task Scheduler (see `tools/windows/run_selector.ps1`)

**Dashboard API:**
- `GET /selector/status` - Returns selector status including last run time, candidate counts, and errors
- Dashboard provides monitoring UI at `http://localhost:8000` when running

### Flag Aliases
- `--iterations` works identically to `--max-iterations`
- Both flags accept an integer value and control the number of trading loop iterations
- Default: 5 iterations if not specified

---

## Environment Variables

The bot supports mode-specific Alpaca API credentials, allowing you to maintain both paper and live credentials simultaneously without manual swapping.

### Alpaca Credentials

**Paper Trading (Simulated):**
- `ALPACA_PAPER_KEY_ID` - Paper trading API key (starts with "PK")
- `ALPACA_PAPER_SECRET_KEY` - Paper trading secret key

**Live Trading (Real Money):**
- `ALPACA_LIVE_KEY_ID` - Live trading API key (starts with "AK")
- `ALPACA_LIVE_SECRET_KEY` - Live trading secret key

**Legacy (Backward Compatibility):**
- `ALPACA_API_KEY` - Falls back if mode-specific vars not set
- `ALPACA_SECRET_KEY` - Falls back if mode-specific vars not set

### Mode Selection

The bot automatically selects the correct credential set based on the `--mode` flag:
- `--mode paper` → Uses `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`
- `--mode live` → Uses `ALPACA_LIVE_KEY_ID` and `ALPACA_LIVE_SECRET_KEY`
- `--mode dry-run` → No credentials required (mock mode)

### Setting Environment Variables

**Windows PowerShell:**
```powershell
# Paper trading credentials
$env:ALPACA_PAPER_KEY_ID = "PKxxxxxxxxxxxxxxxxxx"
$env:ALPACA_PAPER_SECRET_KEY = "yyyyyyyyyyyyyyyyyyyy"

# Live trading credentials (REAL MONEY)
$env:ALPACA_LIVE_KEY_ID = "AKxxxxxxxxxxxxxxxxxx"
$env:ALPACA_LIVE_SECRET_KEY = "zzzzzzzzzzzzzzzzzzzz"
```

**Linux/Mac Bash:**
```bash
# Paper trading credentials
export ALPACA_PAPER_KEY_ID="PKxxxxxxxxxxxxxxxxxx"
export ALPACA_PAPER_SECRET_KEY="yyyyyyyyyyyyyyyyyyyy"

# Live trading credentials (REAL MONEY)
export ALPACA_LIVE_KEY_ID="AKxxxxxxxxxxxxxxxxxx"
export ALPACA_LIVE_SECRET_KEY="zzzzzzzzzzzzzzzzzzzz"
```

**Using .env File (Recommended):**
```bash
# .env file (do NOT commit this file to git)
ALPACA_PAPER_KEY_ID=PKxxxxxxxxxxxxxxxxxx
ALPACA_PAPER_SECRET_KEY=yyyyyyyyyyyyyyyyyyyy

ALPACA_LIVE_KEY_ID=AKxxxxxxxxxxxxxxxxxx
ALPACA_LIVE_SECRET_KEY=zzzzzzzzzzzzzzzzzzzz
```

### Checking Configuration

Use `--check-env` to validate your environment setup:

```bash
# Check paper mode configuration
python -m src.app --mode paper --check-env

# Check live mode configuration
python -m src.app --mode live --check-env
```

**Output Example:**
```
================================================================================
ENVIRONMENT CHECK
================================================================================
Selected Mode: paper
Trading Mode: Paper (simulated trading)

Expected Environment Variables:
  ALPACA_PAPER_KEY_ID
  ALPACA_PAPER_SECRET_KEY

Configuration:
  API Base URL: https://paper-api.alpaca.markets

Credentials Status: ✓ Found
  API Key: ...XY12
  Secret Key: ...****

✓ All required credentials are set
================================================================================
```

### Safety Features

1. **Mode Isolation**: Paper credentials cannot accidentally be used in live mode and vice versa
2. **Validation**: Bot validates required credentials at startup with clear error messages
3. **No Secret Exposure**: `--check-env` only shows last 4 characters of API key, never shows secrets
4. **Explicit Base URLs**: Each mode has a fixed base URL (paper: `https://paper-api.alpaca.markets`, live: `https://api.alpaca.markets`)

### Migration from Legacy Variables

If you're currently using `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`:
1. The bot will continue to work (backward compatible)
2. To use both paper and live:
   - Rename paper credentials to `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`
   - Add live credentials as `ALPACA_LIVE_KEY_ID` and `ALPACA_LIVE_SECRET_KEY`
   - Remove old `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` vars

---

## Dry-Run Execution Preview

### Purpose
The `--dry-run` flag enables execution preview mode where the full trading pipeline runs (signal generation, risk checks, quote fetching, pricing decisions) but no orders are ever submitted to the broker.

### Key Features
- **No Order Submission**: Broker submit/cancel/replace endpoints are never called
- **Full Pipeline Execution**: Runs complete strategy logic including:
  - Market data fetching (bars and quotes)
  - Signal generation (SMA crossovers)
  - Risk manager checks (position sizing, exposure limits)
  - Limit price calculation (spread-aware pricing)
- **Preview Output**: For each symbol, prints concise decision summary with:
  - Symbol name
  - Decision (BUY/SELL/HOLD)
  - Quantity (if order would be placed)
  - Limit price (if applicable)
  - Reason (crossover detected, market closed, gate blocked, etc.)
- **Banner**: Prints `DRY RUN — NO ORDERS SUBMITTED` at start for visibility

### Mode Compatibility
Dry-run works with any trading mode without requiring credentials or safety gates:

**Mock Mode (`--mode dry-run --dry-run`):**
- Uses MockBroker (no network calls)
- Uses MockDataProvider (deterministic test data)
- No credentials required

**Paper Mode (`--mode paper --dry-run`):**
- Uses MockBroker (no orders submitted)
- Can use AlpacaDataProvider if credentials available (accurate market data)
- Falls back to MockDataProvider if no credentials
- **No API credentials required** (unlike normal paper mode)

**Live Mode (`--mode live --dry-run`):**
- Uses MockBroker (no orders submitted)
- Can use AlpacaDataProvider if credentials available
- **No safety gates required** (no `--i-understand-live-trading` or `ENABLE_LIVE_TRADING=true`)
- Safe for testing live mode logic without risk

### Safety Gates Bypass
When `--dry-run` is set, the following safety checks are **bypassed** (since no orders will be submitted):
1. Live trading triple authentication (--i-understand-live-trading + ENABLE_LIVE_TRADING)
2. API credential requirements for paper/live modes
3. After-hours order submission gates (preview still respects market hours for accuracy)

### Implementation Details
- **Broker**: Always uses MockBroker regardless of configured mode
- **Data Provider**: Uses real provider (Alpaca) if credentials available, otherwise MockDataProvider
- **Risk Checks**: Still executed to show what would be rejected
- **Order Pipeline**: Runs through spread checks and limit price calculation before stopping
- **State File**: Not modified (no orders to track)

### Examples

**Test strategy logic without submitting orders:**
```bash
python -m src.app --mode dry-run --dry-run --once --symbols AAPL,MSFT
```

**Preview with real market data (requires Alpaca credentials):**
```bash
python -m src.app --mode paper --dry-run --once --symbols AAPL,MSFT
```

**Test live mode logic safely (no credentials or safety gates needed):**
```bash
python -m src.app --mode live --dry-run --once --symbols AAPL,MSFT
```

**Run multiple iterations to see decision patterns:**
```bash
python -m src.app --dry-run --iterations 10 --symbols AAPL
```

### Output Format
```
======================================================================
DRY RUN — NO ORDERS SUBMITTED
======================================================================

PREVIEW:
  --------------------------------------------------------------------------------
  Symbol Act  Qty      Price  Reason
  --------------------------------------------------------------------------------
  AAPL   BUY    5   $175.25  Golden cross detected (fast>slow)
  MSFT   HOLD   -       N/A  No crossover detected
  GOOGL  HOLD   -       N/A  Market closed (gate blocked)
  --------------------------------------------------------------------------------
```

### Testing
Comprehensive test coverage in `tests/test_dry_run.py`:
- Verifies no broker calls made
- Checks preview output format
- Tests mode combinations (mock, paper, live)
- Validates safety gate bypass
- Confirms credential bypass for paper/live modes

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

### Session Kill Switch (MAX_SESSION_LOSS)
The session kill switch is an in-session safety feature that stops all new order submissions once session losses exceed a threshold.

**Key Characteristics:**
- **Not persisted**: Session PnL resets to $0 on each bot restart
- **In-session protection**: Prevents runaway losses within a single bot session
- **Optional**: Disabled by default (set via `--max-session-loss` flag or `MAX_SESSION_LOSS` env var)
- **Complementary to daily loss**: Session loss and daily loss are tracked independently

**Behavior:**
1. Session PnL starts at $0 when bot starts
2. Session PnL accumulates as positions are closed (realized PnL only)
3. When `session_pnl <= -max_session_loss`:
   - All new order submissions are blocked for the remainder of the session
   - A clear WARNING is logged on first trip (logged once to avoid spam)
   - Bot continues running (data fetching, reconciliation, logging)
4. Next bot restart: Session PnL resets to $0 (fresh start)

**CLI Flag:**
```bash
# Enable $100 session loss limit
python -m src.app --max-session-loss 100

# Disabled by default
python -m src.app  # No session loss limit
```

**Use Cases:**
- **Intraday protection**: Stop trading after -$100 loss in current session
- **Development/testing**: Test risk controls without persisted state
- **Complementary to daily limit**: Layer multiple safety thresholds (e.g., $100 session, $500 daily)

**Example:**
```bash
# Bot starts at 9:30 AM
python -m src.app --max-session-loss 100

# 10:00 AM: Loses $80 (still trading, under limit)
# 10:15 AM: Loses another $25 (total: -$105)
# -> KILL SWITCH TRIPS: No more orders this session
# -> Bot continues running but won't submit orders

# Bot restarts at 11:00 AM
python -m src.app --max-session-loss 100
# -> Session PnL resets to $0
# -> Can trade again (daily PnL still tracked separately)
```

**Comparison to Daily Loss:**
| Feature | Daily Loss (MAX_DAILY_LOSS) | Session Loss (MAX_SESSION_LOSS) |
|---------|----------------------------|--------------------------------|
| Persistence | Persisted across restarts | NOT persisted (resets on restart) |
| Scope | Calendar day (US/Eastern) | Current bot session |
| Reset | Automatic at midnight ET | Manual (restart bot) |
| Use Case | Prevent daily loss bypass | In-session runaway protection |
| Default | $500 | Disabled (None) |

### Pause Trading (Global Kill Switch)

The pause trading feature provides a runtime kill switch to stop order submission without terminating the bot process.

**Key Characteristics:**
- **File-based flag**: Uses `state/pause_trading.flag` file presence to control state
- **Non-blocking**: Bot continues to run, evaluate signals, and log events while paused
- **Dashboard control**: Managed via dashboard UI (`POST /pause_trading` endpoint)
- **No data loss**: All trading logic still executes (signals, allocation, ledger logging) except order submission

**Behavior:**

When paused (`state/pause_trading.flag` exists):
1. Trading loop continues normally (data fetching, candidate loading, signal evaluation)
2. Strategy intents are computed and allocation is performed
3. Orders are prepared and validated through risk gates
4. **Order submission is skipped** (no broker API calls made)
5. Ledger logs all events including "would-have-been" orders
6. Dashboard shows warning banner: "TRADING PAUSED"

When unpaused (`state/pause_trading.flag` removed):
7. Next loop iteration resumes normal order submission
8. No restart required

**Control Methods:**

1. **Dashboard UI**:
   ```
   Navigate to http://localhost:8000
   Toggle "Pause Trading" switch in health panel
   ```

2. **API Endpoint**:
   ```bash
   # Pause trading
   curl -X POST http://localhost:8000/pause_trading \
     -H "Content-Type: application/json" \
     -d '{"paused": true}'

   # Resume trading
   curl -X POST http://localhost:8000/pause_trading \
     -H "Content-Type: application/json" \
     -d '{"paused": false}'
   ```

3. **Manual File Control**:
   ```bash
   # Pause trading
   echo "paused" > state/pause_trading.flag

   # Resume trading
   rm state/pause_trading.flag
   ```

**Use Cases:**
- **Emergency stop**: Pause trading due to unexpected market conditions without killing bot
- **Maintenance window**: Stop orders while investigating positions or logs
- **Partial testing**: Test signal evaluation logic without submitting orders (similar to DryRun but runtime-controlled)
- **Safe configuration changes**: Pause before making significant strategy parameter changes

**Comparison to Other Controls:**

| Feature | Pause Trading | DryRun Mode | Kill Bot Process |
|---------|---------------|-------------|------------------|
| Order Submission | Blocked | Blocked | Stopped |
| Signal Evaluation | Active | Active | Stopped |
| Ledger Logging | Active | Active | Stopped |
| Dashboard Updates | Active | Active | Stopped |
| Control Method | Runtime flag | CLI flag | Process termination |
| Resume | Remove flag | Restart with --paper | Restart process |
| Restart Required | No | Yes | Yes |

---

## Process Control

### Single Instance Guard

**Purpose**: Prevent duplicate concurrent executions of the runner when started by Task Scheduler or other automation.

**Problem**: Windows Task Scheduler can sometimes trigger overlapping task instances, leading to:
- Two python processes running `src.app.runner` simultaneously
- Race conditions in state file access
- Duplicate order submissions
- Inconsistent PnL tracking

**Solution**: Defense-in-depth with three layers:

1. **Task Scheduler**: `IfAlreadyRunning: IgnoreNew` setting
2. **PowerShell Lock**: Exclusive file lock in `tools/run_paper_dryrun.ps1`
3. **Python Mutex**: Windows named mutex in `runner.py` main()

### Implementation

**Python Single Instance Guard** (`src/app/runner.py`):
- **Execution Timing**: Runs at **module import time** in `if __name__ == "__main__"` block
  - Executes BEFORE `main()` is called
  - Executes BEFORE argument parsing
  - Executes BEFORE any code that could trigger Python re-exec with `-m`
- **Guard Functions**:
  - `_acquire_mutex(mutex_name: str) -> bool` - Acquires Windows named mutex
  - `_acquire_file_lock(lock_file: Path) -> bool` - Acquires exclusive file lock
- **Guard Execution**: Inlined at module level (no wrapper function)
  ```python
  if __name__ == "__main__":
      mutex_acquired = _acquire_mutex(...)
      lock_acquired = _acquire_file_lock(...)
      if not mutex_acquired or not lock_acquired:
          sys.exit(0)
      main()  # Only reached if both guards succeed
  ```
- **TWO Mechanisms** (BOTH required):
  1. **Windows Named Mutex**: `Local\AI_TRADER__PAPER_DRYRUN_LOOP`
     - Uses `pywin32` library (`win32event.CreateMutex`) - **MANDATORY**
     - Session-local namespace for reliability
     - Checks `ERROR_ALREADY_EXISTS` (183) to detect duplicates
     - Held for process lifetime (auto-released by OS on exit)
  2. **Exclusive File Lock**: `logs/paper_dryrun.lock`
     - OS-level exclusive lock via `CreateFileW` with `dwShareMode=0`
     - No file sharing - true exclusive access
     - Handle held open for process lifetime (auto-released on exit)
- **FAIL-CLOSED Policy** (production-critical):
  - **BOTH** guards must succeed or execution stops immediately
  - If mutex fails (exists or error) → EXIT immediately
  - If file lock fails (held or error) → EXIT immediately
  - If pywin32 not installed → `ImportError` at module import (immediate failure)
  - **NO** fallback logic, **NO** "continue anyway", **NO** try/except around imports
  - **NO** code path allows execution if guard fails
- **Behavior**:
  - First instance: Acquires both mutex + lock → `main()` runs normally
  - Duplicate instance: Fails to acquire → prints message → `sys.exit(0)`
  - Error case: Cannot verify single instance → prints error → `sys.exit(0)`
  - Missing pywin32: `ImportError` before any code executes

**PowerShell File Lock** (`tools/run_paper_dryrun.ps1`):
- Lock file: `logs/paper_dryrun.lock`
- Method: `[System.IO.File]::Open(..., "ReadWrite", "None")` (exclusive access)
- Behavior:
  - If lock held by another script: logs to `task_scheduler.log` and exits 0
  - If lock acquired: holds lock for entire runner lifetime
  - Lock auto-released when script exits (finally block disposes file handle)
- **Note**: Separate from runner.py's `logs/runner.lock` - both provide independent protection

**Debug Logging**:
- Every runner start logs comprehensive diagnostics:
  - PID, parent PID, interpreter path, arguments
  - Current market time (America/New_York)
- If blocked by guard: logs PID and interpreter of blocked instance
- This helps identify:
  - Virtual environment mismatches (wrong Python interpreter)
  - Multiple instances or spawn issues
  - Parent-child process relationships
- Logged to stdout at module import time (before any other operations)

**Market-Time Logging**:
- All log filenames use `America/New_York` timezone (market time)
- Format: `YYYYMMDD_HHMMSS_ET` (e.g., `20250131_143025_ET`)
- Prevents UTC date rollover bug: logs with "tomorrow's date" while market is still today
- Daily loss accounting already uses market time via `get_today_date_eastern()`
- Internal timestamps may still use UTC for data consistency

**Dependencies**:
- `pywin32>=311` is **MANDATORY** for Windows
- Import statement has clear error if pywin32 missing (explains venv requirement)
- This is intentional: fail-closed policy requires hard dependency
- Non-Windows platforms: runner.py will not work (Windows-only by design)

**Verification**:
```powershell
# Manual test - Terminal 1: Start runner
python -m src.app.runner --mode paper --once --dry-run

# Terminal 2: Try to start again (should be blocked in < 5 seconds)
python -m src.app.runner --mode paper --once --dry-run
# Expected output:
# [runner] pid=<PID2> ppid=<PPID2> argv=[...]
# ================================================================================
# SINGLE INSTANCE GUARD: Another instance is already running
# ================================================================================
# Mutex: Local\AI_TRADER__PAPER_DRYRUN_LOOP
# Lock file: logs\paper_dryrun.lock
# Exiting.
# ================================================================================

# Verify process count (should be 1)
Get-Process python | Where-Object {
    (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*src.app.runner*"
}
```

**Logging**:
- PowerShell lock events logged to `logs/task_scheduler.log`
- Python guard blocks print to stdout (visible in console/logs)
- Debug PID/PPID logged at every start

**Why Three Layers**:
Even if one layer fails (e.g., Task Scheduler misconfigured), the other two provide backup protection. This is critical for automated deployments where manual monitoring may be limited.

---

## State Persistence & Daily Loss Tracking

### Purpose
Daily loss enforcement must persist across bot restarts to prevent circumvention of `MAX_DAILY_LOSS` limits. All daily counters reset automatically when the trading day changes (US/Eastern timezone).

### Critical Safety Requirement
**The bot MUST NOT allow users to bypass daily loss limits by restarting.** If a bot accumulates -$100 loss (approaching the limit), restarting the bot must NOT reset that counter to $0.

### Persisted State Fields
The following fields are persisted in `state.json` (located at `out/state.json`):

**`daily_date`** (string, YYYY-MM-DD):
- Current trading day in US/Eastern timezone
- Used to detect day rollover
- Automatically updated when loading state on a new day

**`daily_realized_pnl`** (dict[str, str]):
- Maps date strings (YYYY-MM-DD) to realized PnL (Decimal as string)
- Example: `{"2024-01-15": "-80.50", "2024-01-16": "25.00"}`
- Preserves historical daily PnL for analysis
- Only today's entry is used for risk checks

### Day Rollover Logic
When `load_state()` is called (at startup):
1. Computes today's date in US/Eastern timezone
2. Compares `state.daily_date` to today
3. If different (new trading day):
   - Updates `state.daily_date = today`
   - Does NOT delete historical PnL entries
   - Today's PnL starts at $0 (no entry in dict yet)
4. If same (same trading day):
   - Loads persisted daily PnL from state
   - RiskManager initialized with this value
   - Trading blocked if daily loss limit exceeded

### Daily PnL Synchronization
The bot syncs daily PnL from RiskManager back to state at multiple points:

1. **After each order** (in main trading loop):
   - Computes delta between RiskManager PnL and state PnL
   - Calls `update_daily_realized_pnl(state, delta)`
   - Saves state to disk

2. **After reconciliation** (startup sync with broker):
   - Syncs any PnL changes from reconciled positions
   - Ensures state matches broker reality

3. **Never** during dry-run mode:
   - Dry-run does not modify state
   - Daily PnL not updated in dry-run

### RiskManager Integration
**Initialization:**
```python
daily_pnl = get_daily_realized_pnl(state)  # Loads persisted PnL
risk_manager = RiskManager(config, daily_realized_pnl=daily_pnl)
```

**Daily Loss Check:**
```python
if self.daily_pnl <= -self.config.max_daily_loss:
    return RiskCheckResult(False, f"Daily loss limit ({self.config.max_daily_loss}) exceeded")
```

- Check: `daily_pnl <= -max_daily_loss` (e.g., -$100 <= -$100 blocks trading)
- Blocks ALL new orders once limit reached
- Persists across restarts (cannot be bypassed)

### Implementation Files
- `src/app/state.py`: State model, load/save, daily PnL tracking
  - `BotState.daily_date`: Current trading day
  - `BotState.daily_realized_pnl`: Historical daily PnL
  - `get_today_date_eastern()`: Get current date in Eastern timezone
  - `get_daily_realized_pnl(state)`: Get today's PnL
  - `update_daily_realized_pnl(state, delta)`: Update today's PnL
  - `load_state()`: Handles day rollover logic
- `src/app/__main__.py`: Main trading loop
  - Loads daily PnL from state on startup
  - Syncs RiskManager PnL back to state after fills
- `src/risk/manager.py`: Risk checks
  - Initialized with persisted daily_realized_pnl
  - Enforces max_daily_loss limit

### Testing
Comprehensive tests in `tests/test_daily_loss_persistence.py`:
- **Restart persistence**: Daily loss survives bot restarts
- **Day rollover**: Counters reset on new trading day (Eastern timezone)
- **Blocking behavior**: Trading blocked immediately after restart when limit exceeded
- **Multiple restarts**: Loss accumulates correctly across N restarts
- **Timezone**: All tests use US/Eastern timezone

All tests are offline (no network calls, mock broker/provider).

### Example Scenarios

**Scenario 1: Restart bypass attempt (BLOCKED)**
1. Bot runs, accumulates -$100 loss
2. User restarts bot hoping to reset counter
3. `load_state()` loads persisted -$100 loss
4. RiskManager blocks all new trades
5. ✅ Restart bypass prevented

**Scenario 2: New trading day (ALLOWED)**
1. Bot runs on Monday, accumulates -$100 loss, stops trading
2. Tuesday morning, bot starts
3. `load_state()` detects day rollover (Monday → Tuesday)
4. Daily PnL resets to $0 for Tuesday
5. ✅ Trading allowed on new day

**Scenario 3: Multiple restarts, accumulating loss**
1. Session 1: -$30 loss, save state, exit
2. Session 2: Load state (-$30), add -$40 loss, save state (-$70), exit
3. Session 3: Load state (-$70), add -$35 loss, save state (-$105), exit
4. Session 4: Load state (-$105), trading blocked (exceeds -$100 limit)
5. ✅ Loss persists and accumulates correctly

---

## Operator Observability

The `--status` flag provides an operator-facing snapshot of current bot state and metrics for monitoring and debugging purposes.

### Purpose
Provide real-time visibility into bot health, risk status, and trading activity without running the full trading loop.

### Features
- **No market hours required**: Works anytime (market open or closed)
- **No credentials required**: Works in mock mode without Alpaca API keys
- **Human-readable output**: Formatted table printed to console
- **Machine-readable output**: JSON file written to `out/status.json`
- **Fast execution**: Exits immediately after displaying status

### Metrics Displayed

**System Info:**
- Timestamp (UTC + US/Eastern)
- Trading mode (mock/paper/live)

**PnL Tracking:**
- Daily realized PnL (persisted across restarts)
- Session realized PnL (in-memory, resets on restart)

**Risk Status:**
- Daily loss kill-switch status (tripped/not tripped)
- Session loss kill-switch status (tripped/not tripped)

**Trading Activity:**
- Open positions count and details
- Open orders count and details

**Signals:**
- Last signal per symbol (currently not persisted, shows "N/A")

### Usage

```bash
# Check status in mock mode (no credentials needed)
python -m src.app --status

# Check status in paper mode
python -m src.app --mode paper --status

# Check status in live mode (requires safety gates)
python -m src.app --mode live --i-understand-live-trading --status
```

### Output Format

**Console Output:**
```
================================================================================
OPERATOR STATUS SNAPSHOT
================================================================================
Timestamp (UTC):        2024-01-15 15:30:45
Timestamp (US/Eastern): 2024-01-15 10:30:45

Mode:                   dry-run
Daily PnL:              $   -123.45
Session PnL:            $      0.00

Open Positions:                  2
Open Orders:                     1

Daily Loss Kill-Switch: False
Session Loss Kill-Switch: False

Positions:
  AAPL: 10 shares @ $150.25
  MSFT: 5 shares @ $380.50

Open Orders:
  GOOGL: BUY 10 @ $142.30

Last Signals: (Not persisted)
================================================================================

Machine-readable output written to: out/status.json
```

**JSON Output (`out/status.json`):**
```json
{
  "timestamp_utc": "2024-01-15T15:30:45.123456",
  "timestamp_eastern": "2024-01-15T10:30:45.123456-05:00",
  "mode": "dry-run",
  "daily_pnl": -123.45,
  "session_pnl": 0.0,
  "open_positions_count": 2,
  "open_orders_count": 1,
  "daily_loss_kill_switch_tripped": false,
  "session_loss_kill_switch_tripped": false,
  "positions": [
    {"symbol": "AAPL", "quantity": 10, "avg_price": 150.25},
    {"symbol": "MSFT", "quantity": 5, "avg_price": 380.50}
  ],
  "orders": [
    {"symbol": "GOOGL", "side": "BUY", "qty": 10, "limit_price": 142.30}
  ],
  "last_signals": {}
}
```

### Use Cases

1. **Pre-trading checks**: Verify bot state before starting trading session
2. **Health monitoring**: Quick check of PnL, positions, and risk status
3. **Debugging**: Inspect state after unexpected behavior
4. **Automation**: Parse JSON for monitoring dashboards or alerts
5. **Risk management**: Verify kill-switch status without starting bot

### Implementation Notes

- **Session PnL**: Always shows 0 in status output (not persisted, only tracks within running session)
- **Daily PnL**: Loaded from `state.json` (persisted across restarts)
- **Kill-switch status**: Computed based on current PnL vs configured limits
- **Positions/Orders**: Fetched from broker (MockBroker in mock mode, Alpaca API in paper/live)

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

## Order Slicing & Risk-Reducing Sells

The execution layer implements automatic order slicing to handle orders exceeding `max_order_notional` caps, while ensuring risk-reducing sells can always proceed.

### Problem Statement

**Original Issue:**
- Executor blocked risk-reducing sells when they exceeded `max_order_notional`
- Example: Position of SPY=2 @ $690/share ($1380 total), with `max_order_usd=$100`
- Attempting to flatten (target=0) would generate SELL 2 @ $1380 > $100 cap → **order blocked**
- **Result**: Position stuck, unable to close

### Solution: Automatic Order Slicing

Orders exceeding `max_order_notional` are automatically sliced into multiple smaller orders:
- Each slice respects the `max_order_notional` cap
- Applies to both BUY and SELL orders
- Preserves all order attributes (symbol, side, limit price, reason)
- All slices use same limit price offset rules (-0.5% for buys, +0.5% for sells)

**Slicing Algorithm:**
```python
# Given: Order to SELL 5 shares @ $690, max_order_notional = $150

1. Calculate notional: 5 * $690 = $3,450
2. Exceeds cap → slice required
3. Max shares per slice: floor($150 / $690) = 0 → force to 1 (minimum)
4. Total slices needed: ceil(5 / 1) = 5 slices
5. Result: 5 separate SELL orders of 1 share each @ ~$687 (with +0.5% offset)
```

**Minimum Tradeable Unit:**
- If price exceeds cap (e.g., $690 > $150), max_qty_per_slice = 0
- Force to 1 share minimum (cannot trade fractional shares)
- Individual slices may exceed cap but proceed anyway (minimum atomic unit)

### Risk-Reducing Sells Policy

**Definition:** A sell order is "risk-reducing" if it closes an existing long position.

**Policy Rules:**
1. **Risk-reducing sells ALWAYS proceed** (with slicing if needed)
2. **Risk-increasing orders** (BUY) are subject to `max_positions_notional` cap
3. Risk-reducing sells bypass exposure cap checks
4. Ensures positions can always be closed regardless of order size

**Detection:**
- Order marked as `is_risk_reducing=True` when:
  - `side == SELL`
  - Current position quantity > 0 (closing long)
- Tracked throughout slicing and execution

**Example:**
```
Current: SPY=2 @ $680
Target: SPY=0 (flatten)
Delta: -2 (SELL 2)
max_order_notional: $100

Without risk-reducing policy: BLOCKED (2 * $690 = $1380 > $100)
With risk-reducing policy: SLICED into 2 orders of 1 share each → PROCEEDS
```

### Reconciliation Policy

**Explicit Position Behavior:**
- Symbols **not present** in `AllocationResult.target_positions` are treated as `target=0` (flatten)
- This makes flattening behavior explicit and deterministic
- Reconciliation considers ALL symbols in current positions OR target positions

**Reconciliation Steps:**
1. Fetch current positions from broker
2. Compare current vs target for all symbols
3. Calculate delta: `target_qty - current_qty`
4. Generate order instructions for non-zero deltas
5. Apply slicing and risk enforcement
6. Place orders

**Reconciliation Table Output:**
```
Reconciliation:
  Symbol    Current   Target    Delta Action
  ------------------------------------------------------------
  AAPL            5        2       -3 SELL 3
  SPY             2        0       -2 SELL 2 (flatten)
  MSFT            0        1        1 BUY 1
```

### Responsibility Split: Allocator vs Executor

**Allocator (`src/app/allocator.py`):**
- Assigns capital budgets to strategies (equal-weight by default)
- Aggregates target positions across strategies
- Enforces **only** `max_positions_notional` (total portfolio cap)
- **Does NOT enforce** `max_order_notional` (delegated to executor)
- Passes through target quantities unchanged (no pre-filtering)

**Executor (`src/app/execution/alpaca_executor.py`):**
- Reconciles target vs current positions
- Generates order instructions (delta-based)
- Enforces `max_order_notional` via order slicing
- Enforces `max_positions_notional` for risk-increasing orders only
- Tracks exposure correctly (adds for buys, subtracts for risk-reducing sells)
- Places orders (or dry-run prints)

**Rationale:**
- Allocator operates at portfolio level (total exposure)
- Executor operates at order level (individual order constraints)
- Clean separation of concerns
- Slicing logic centralized in execution layer

### Slicing Implementation

**Core Function:** `AlpacaExecutor._slice_order(instruction, price)`

**Returns:** List of `OrderSlice` objects, each containing:
- `instruction`: OrderInstruction with adjusted quantity
- `slice_index`: 1-based index of this slice
- `total_slices`: Total number of slices for this order

**Single Order (no slicing):**
```python
OrderSlice(
    instruction=OrderInstruction(symbol="XLF", side=BUY, quantity=1, ...),
    slice_index=1,
    total_slices=1
)
```

**Sliced Order:**
```python
[
    OrderSlice(instruction=OrderInstruction(symbol="SPY", side=SELL, quantity=1, ...), slice_index=1, total_slices=2),
    OrderSlice(instruction=OrderInstruction(symbol="SPY", side=SELL, quantity=1, ...), slice_index=2, total_slices=2),
]
```

### Execution Logging

**Slicing Notification:**
```
Execution (max_order_usd=$100):
  AAPL: Order $1366.95 exceeds cap, slicing into 5 orders
```

**Dry-Run Output (with slicing):**
```
  [DRY-RUN] AAPL   SELL   1 @ $ 272.02  (Target=0, Current=5, Delta=-5) [slice 1/5] (risk-reducing)
  [DRY-RUN] AAPL   SELL   1 @ $ 272.02  (Target=0, Current=5, Delta=-5) [slice 2/5] (risk-reducing)
  [DRY-RUN] AAPL   SELL   1 @ $ 272.02  (Target=0, Current=5, Delta=-5) [slice 3/5] (risk-reducing)
  [DRY-RUN] AAPL   SELL   1 @ $ 272.02  (Target=0, Current=5, Delta=-5) [slice 4/5] (risk-reducing)
  [DRY-RUN] AAPL   SELL   1 @ $ 272.02  (Target=0, Current=5, Delta=-5) [slice 5/5] (risk-reducing)
```

**Production Logging:**
```
INFO: Order placed: AAPL SELL 1 @ $272.02 (slice 1/5, ID: abc-123)
INFO: Order placed: AAPL SELL 1 @ $272.02 (slice 2/5, ID: abc-124)
...
```

### Risk Enforcement Rules

**For Risk-Increasing Orders (BUY):**
1. Apply slicing if notional exceeds `max_order_notional`
2. Check each slice against `max_positions_notional`
3. Skip slice if adding it would exceed total exposure cap
4. Update exposure tracker: `exposure += slice_notional`

**For Risk-Reducing Orders (SELL closing position):**
1. Apply slicing if notional exceeds `max_order_notional`
2. **Bypass** `max_positions_notional` check (always proceed)
3. Update exposure tracker: `exposure -= slice_notional`
4. Never skip risk-reducing slices

**Exposure Tracking:**
- Current exposure calculated from broker positions
- Updated after each slice placement
- Risk-reducing orders **decrease** exposure
- Risk-increasing orders **increase** exposure

### Testing

**Test Coverage (`tests/test_execution.py`):**

1. `test_executor_slices_large_order` - Verify BUY order slicing
2. `test_executor_risk_reducing_sell_with_slicing` - **Critical**: Flatten position with low cap
3. `test_executor_partial_flatten_with_slicing` - Partial position reduction
4. `test_executor_buy_order_slicing` - BUY orders also sliced
5. `test_executor_mixed_slicing_and_no_slicing` - Mixed scenarios

**Test Coverage (`tests/test_allocator.py`):**

6. `test_allocator_passes_through_large_orders` - Allocator doesn't pre-filter by `max_order_notional`

**Critical Test Scenario:**
```python
# Current: SPY=2 @ $680, Target: 0 (flatten)
# max_order_notional=$100, price=$690
# Expected: 2 SELL orders of 1 share each (sliced)
# Result: PASSES - position flattened

config = Config(max_order_notional=Decimal("100"))
broker.positions["SPY"] = (2, Decimal("680.00"))
target_positions = {}  # Empty = flatten to 0

result = executor.reconcile_and_execute(target_positions, prices)
assert len(result.orders_placed) == 2  # 2 slices
assert all(order.side == OrderSide.SELL for order in broker.orders)
```

All 329 tests pass with slicing enabled.

### Before vs After Comparison

| Scenario | Before (Blocking) | After (Slicing) |
|----------|------------------|-----------------|
| SPY position=2, target=0, cap=$100 | SELL 2 blocked ($1380 > $100) | SELL 2 sliced into 2 orders of 1 share |
| Orders placed | 0 | 2 |
| Orders skipped | 1 (blocked) | 0 |
| Position result | **Stuck at 2 shares** | **✅ Flattened to 0** |
| Can close positions | **NO** | **YES** |

### CLI Flags

**Relevant Risk Parameters:**
- `--max-order-notional <dollars>` - Maximum order notional value (default: $500)
  - Enforced via automatic order slicing
  - Applies to both BUY and SELL orders
  - Risk-reducing sells always proceed (sliced if needed)
- `--max-positions-notional <dollars>` - Maximum total positions exposure (default: $10000)
  - Enforced by allocator (total cap)
  - Enforced by executor for risk-increasing orders only
  - Bypassed for risk-reducing sells

**Strategy Runner Flags:**
- `--mode paper` - Uses AlpacaBroker with slicing enabled
- `--dry-run` - Prints sliced orders without placing

### Implementation Files

- `src/app/allocator.py` - Portfolio allocation (only enforces total cap)
- `src/app/execution/alpaca_executor.py` - Order slicing and execution
  - `_slice_order()` - Core slicing logic
  - `_generate_order_instructions()` - Delta calculation, risk-reducing detection
  - `_execute_orders()` - Slice placement, exposure tracking
  - `reconcile_and_execute()` - Top-level reconciliation
- `tests/test_execution.py` - Execution and slicing tests
- `tests/test_allocator.py` - Allocator behavior tests

---

## Shadow PnL Performance Tracking

The system implements Shadow PnL to enable strategy performance tracking and dynamic weight updates without requiring actual fills. This allows performance monitoring in shadow mode and paper --dry-run mode by computing mark-to-market returns from hourly price changes.

### Purpose

Enable performance tracking for multi-strategy portfolios when fills are not available:
- Shadow mode: No orders placed, only intents generated
- Paper --dry-run mode: Orders previewed but not submitted
- Track strategy performance using market returns
- Dynamically adjust strategy capital allocation weights based on performance

### Core Components

**Shadow PnL Calculator** (`src/app/shadow_pnl.py`):
- Computes 1-period returns: `r = (close_t - close_t-1) / close_t-1`
- Stores previous prices internally for cross-run return calculation
- Allocates per-strategy notional based on intents and budgets
- Attributes returns: `strategy_return = sum(notional_weight * symbol_return)`

**Strategy State** (`src/app/state.py:StrategyState`):
- `weight`: Capital allocation (0.0-1.0, sum=1.0)
- `cumulative_pnl`: Total profit/loss from attributed returns
- `rolling_returns`: Last N return samples (default: 200)
- `drawdown`: Maximum decline from peak equity (negative value)
- `trade_count`: Number of attributed samples

### Return Calculation Algorithm

**Market Returns:**
```python
# First run: store current prices
prev_prices["SPY"] = 400.0

# Second run: compute returns
current_price = 404.0
return_pct = (404.0 - 400.0) / 400.0  # = 0.01 (1% gain)
```

**Notional Allocation (Simple Equal Allocation):**
```python
# Strategy has budget=$5000 with intents=[SPY, QQQ] (both target_qty > 0)
num_intents = 2
notional_per_symbol = $5000 / 2 = $2500

# Result:
strategy_notionals["Trend_MA20"]["SPY"] = $2500
strategy_notionals["Trend_MA20"]["QQQ"] = $2500
```

**Strategy Return Attribution:**
```python
# Given:
# - Trend_MA20 allocated: SPY=$2500, QQQ=$2500
# - Returns: SPY=+1%, QQQ=-1%

total_notional = $2500 + $2500 = $5000
weighted_return = (2500/5000 * 0.01) + (2500/5000 * -0.01) = 0.0

# Update state:
state.rolling_returns.append(0.0)
state.cumulative_pnl += 0.0 * 5000 = $0
state.trade_count += 1
```

### Weight Update Algorithm

**Conservative Dynamic Reweighting:**

1. **Gating**: Require ALL strategies have >= `min_samples` (default: 20) before adjusting weights
   - Until threshold met: maintain equal weights (e.g., 0.5 each for 2 strategies)
   - Prevents premature weight shifts from insufficient data

2. **Performance Score**:
   ```python
   score = mean(returns) - 0.5 * stdev(returns) - abs(drawdown)
   ```
   - Rewards consistent positive returns
   - Penalizes volatility and drawdowns
   - Balances risk-adjusted performance

3. **Softmax Normalization**:
   ```python
   target_weights = softmax(scores)  # Convert scores to probability distribution
   ```
   - Ensures weights sum to 1.0
   - Amplifies performance differences while maintaining proportionality

4. **Smoothing** (90% persistence):
   ```python
   new_weight = 0.9 * old_weight + 0.1 * target_weight
   ```
   - Prevents sudden strategy shifts
   - Gradual weight transitions
   - Reduces noise sensitivity

5. **Bounds Enforcement**:
   ```python
   clamped_weight = max(0.05, min(0.80, smoothed_weight))
   ```
   - Min: 5% per strategy (prevents complete elimination)
   - Max: 80% per strategy (prevents over-concentration)

6. **Final Normalization**: Ensure weights sum to 1.0 after clamping

### Integration Points

**Shadow Mode** (`python -m src.app.runner --mode shadow`):
- Runs at end of each shadow run
- Computes capital allocation via Allocator (gets strategy budgets)
- Updates strategy states with mark-to-market returns
- Persists to `state/strategy_state.json`
- Prints performance summary table

**Paper Dry-Run Mode** (`python -m src.app.runner --mode paper --dry-run`):
- Same as shadow mode
- Useful for testing weight dynamics without order submission
- Adds note: "No fills occurred. Performance tracking uses mark-to-market returns."

### Configuration

**`config/config.yaml`:**
```yaml
performance:
  min_samples: 20   # Samples required before weight updates
  max_samples: 200  # Rolling window size
```

**Config Fields** (`src/app/config.py`):
- `performance_min_samples`: Minimum samples before weight updates (default: 20)
- `performance_max_samples`: Maximum rolling return samples per strategy (default: 200)

### State Persistence

**File**: `state/strategy_state.json`

**Format**:
```json
{
  "Trend_MA20": {
    "name": "Trend_MA20",
    "weight": 0.55,
    "cumulative_pnl": 42.15,
    "rolling_returns": [0.001, 0.002, ...],
    "drawdown": -0.015,
    "trade_count": 25,
    "last_updated": "2025-12-29T12:00:00"
  },
  "MeanRev_Z1.0": {
    "name": "MeanRev_Z1.0",
    "weight": 0.45,
    "cumulative_pnl": 18.32,
    "rolling_returns": [0.0005, 0.001, ...],
    "drawdown": -0.008,
    "trade_count": 25,
    "last_updated": "2025-12-29T12:00:00"
  }
}
```

### Output

**Strategy Performance Summary** (printed at end of runs):
```
================================================================================
Strategy Performance Summary (min_samples=20)
================================================================================
Strategy          Weight    Cumul PnL    Drawdown    Samples
--------------------------------------------------------------------------------
Trend_MA20         55.0%       $42.15      -1.5%         25
MeanRev_Z1.0       45.0%       $18.32      -0.8%         25
================================================================================
```

**First Run Behavior:**
```
================================================================================
Shadow PnL: First run (no previous prices)
Performance tracking will begin on next run.
================================================================================
```

**Samples** initially at 0, increments starting from second run.

### Expected Behavior Over Time

**Run 1 (First run):**
- No previous prices → no returns computed
- Samples stay at 0
- Weights stay equal (0.5 each)
- State file updated with timestamps

**Run 2 (Second run):**
- Returns computed (have previous prices)
- Samples increment to 1
- cumulative_pnl may be non-zero
- Weights still equal (need 20 samples)

**Run 20+ (Sufficient samples):**
- Samples >= 20 for all strategies
- Weights start updating based on performance
- Better-performing strategy gets higher weight (gradual shift via 90% smoothing)
- Weights bounded to [5%, 80%] per strategy

### Safety & Limitations

**Mark-to-Market Assumptions:**
- Assumes instant execution at hourly close prices
- Does not account for slippage, spreads, or execution costs
- Useful for relative strategy comparison, not absolute performance

**Conservative Approach:**
- 20 sample minimum prevents premature adjustments
- 90% smoothing prevents sudden strategy shifts
- [5%, 80%] bounds protect against over-concentration
- Drawdown penalties discourage losing strategies

**Use Cases:**
- Shadow mode: Strategy research and validation
- Dry-run mode: Testing portfolio dynamics before live execution
- Performance comparison: Identify better-performing strategies
- Dynamic allocation: Gradually shift capital to winners

### Implementation Files

- `src/app/shadow_pnl.py` - Shadow PnL calculator (return calculation, notional allocation, performance attribution)
- `src/app/state.py` - StrategyState class and weight update algorithm
- `src/app/runner.py` - Integration in shadow mode and paper dry-run
- `config/config.yaml` - Performance tracking configuration
- `tests/test_shadow_pnl.py` - Comprehensive offline tests (10 test cases covering returns, allocation, weights, drawdown, persistence)

### CLI Usage

```bash
# Run shadow mode with performance tracking
python -m src.app.runner --mode shadow

# Run paper dry-run with performance tracking
python -m src.app.runner --mode paper --dry-run

# Check strategy state
cat state/strategy_state.json
```

---

## Hourly Loop Runner for Automated Execution

The strategy runner supports an optional **loop mode** for running repeatedly at scheduled intervals, designed for automated Windows scheduling without manual intervention.

### Purpose

Enable hands-off automated trading:
- Run strategies hourly (or custom interval) without manual execution
- Robust error handling: exceptions logged but execution continues
- Comprehensive logging for monitoring and debugging
- Safe Windows Task Scheduler integration

### CLI Flags

**Loop Control:**
- `--loop`: Run in loop mode (repeats every --sleep-seconds)
- `--once`: Run once and exit (default behavior, mutually exclusive with --loop)
- `--sleep-seconds <int>`: Seconds to sleep between iterations (default: 3600 = 1 hour)

**Mode Selection:**
- `--mode shadow`: Shadow mode (no orders)
- `--mode paper`: Paper trading mode
- `--dry-run`: Paper dry-run (only with --mode paper)

### Usage Examples

**Run shadow mode once (default behavior):**
```bash
python -m src.app.runner --mode shadow
```

**Run shadow mode hourly (loop):**
```bash
python -m src.app.runner --mode shadow --loop
```

**Run paper dry-run every 30 minutes:**
```bash
python -m src.app.runner --mode paper --dry-run --loop --sleep-seconds 1800
```

**Run paper mode hourly:**
```bash
python -m src.app.runner --mode paper --loop
```

### Loop Behavior

**Execution Flow:**
1. Print loop mode banner with configuration
2. Execute strategy runner (shadow or paper mode)
3. Log result to `logs/loop_status.log`
4. Sleep for --sleep-seconds
5. Repeat from step 2

**Exception Handling:**
- All exceptions caught and logged to `logs/loop_errors.log`
- Execution continues to next iteration (no crashes)
- Both success and error logged to `logs/loop_status.log`

**Stopping the Loop:**
- Press `Ctrl+C` to gracefully shut down
- Displays total iterations completed
- Exits with code 0 (clean shutdown)

### Log Files

**`logs/loop_status.log`** (status summary per iteration):
```
[2025-12-30T10:00:00+00:00] SUCCESS | mode=shadow | dry_run=False | orders_placed=0 | orders_skipped=0 | weights=[Trend_MA20=55.00%, MeanRev_Z1.0=45.00%]
[2025-12-30T11:00:00+00:00] SUCCESS | mode=shadow | dry_run=False | orders_placed=0 | orders_skipped=0 | weights=[Trend_MA20=56.00%, MeanRev_Z1.0=44.00%]
[2025-12-30T12:00:00+00:00] ERROR | mode=shadow | dry_run=False | exception=ConnectionError: Failed to fetch market data
[2025-12-30T13:00:00+00:00] SUCCESS | mode=shadow | dry_run=False | orders_placed=0 | orders_skipped=0 | weights=[Trend_MA20=55.50%, MeanRev_Z1.0=44.50%]
```

**Format:**
- Timestamp: ISO 8601 format (UTC)
- Status: SUCCESS or ERROR
- Mode: shadow or paper
- Dry-run flag: True or False
- Orders placed: Count of orders submitted
- Orders skipped: Count of orders blocked
- Weights: Strategy allocation weights (if tracked)
- Exception: Error type and message (ERROR only)

**`logs/loop_errors.log`** (full stack traces):
```
================================================================================
ERROR at 2025-12-30T12:00:00+00:00 (iteration 3)
================================================================================
Traceback (most recent call last):
  File "src/app/runner.py", line 607, in run_loop
    result = run_shadow_mode()
  File "src/app/runner.py", line 150, in run_shadow_mode
    market_data = provider.get_market_data(universe)
ConnectionError: Failed to fetch market data
```

### Windows Task Scheduler Setup

**Option 1: PowerShell Script (Recommended)**

Create `run_hourly_shadow.ps1`:
```powershell
# Navigate to repo directory
Set-Location "C:\dev\ai-trader"

# Activate Python environment (if using venv)
# & "C:\dev\ai-trader\venv\Scripts\Activate.ps1"

# Run in loop mode
python -m src.app.runner --mode shadow --loop --sleep-seconds 3600

# Log will capture Ctrl+C exits
```

**Task Scheduler Configuration:**
1. Open Task Scheduler
2. Create Basic Task:
   - Name: "AI Trader Hourly Shadow Mode"
   - Trigger: At system startup (or specific time)
   - Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\dev\ai-trader\run_hourly_shadow.ps1"`
   - Start in: `C:\dev\ai-trader`
3. Settings:
   - ✅ Run whether user is logged on or not
   - ✅ Run with highest privileges (if needed for credentials)
   - ✅ Stop task if runs longer than 3 days (safety)
   - ❌ Stop if runs longer than X hours (we want continuous)

**Option 2: Direct Python Execution**

Task Scheduler Action:
- Program: `python.exe`
- Arguments: `-m src.app.runner --mode shadow --loop`
- Start in: `C:\dev\ai-trader`

### Monitoring Loop Execution

**Check if loop is running:**
```powershell
# Windows: Find Python process running loop
Get-Process python | Where-Object { $_.CommandLine -like "*--loop*" }
```

**View recent status:**
```bash
# Tail last 10 entries from status log
tail -10 logs/loop_status.log

# Windows PowerShell:
Get-Content logs\loop_status.log -Tail 10
```

**Check for errors:**
```bash
# View error log
cat logs/loop_errors.log

# Windows PowerShell:
Get-Content logs\loop_errors.log
```

**Count success/error ratio:**
```bash
# Linux/Mac:
grep -c SUCCESS logs/loop_status.log
grep -c ERROR logs/loop_status.log

# Windows PowerShell:
(Select-String -Path logs\loop_status.log -Pattern "SUCCESS").Count
(Select-String -Path logs\loop_status.log -Pattern "ERROR").Count
```

### Safety Features

**Exception Resilience:**
- Network errors: Logged, execution continues
- API failures: Logged, execution continues
- Market data issues: Logged, execution continues
- Any unhandled exception: Logged, execution continues

**No Silent Failures:**
- All exceptions written to `logs/loop_errors.log`
- All status updates written to `logs/loop_status.log`
- Both stdout and log files capture execution state

**Keyboard Interrupt Handling:**
- Graceful shutdown on Ctrl+C
- Displays iteration count
- Exits cleanly (code 0)

### Testing

**Unit tests** (`tests/test_loop_runner.py`):
- Uses `monkeypatch` to mock `time.sleep` (no real sleeping)
- Uses `tmp_path` for isolated log files
- Tests exception handling and recovery
- Tests status/error logging
- Tests keyboard interrupt handling
- All tests run offline (no network calls)

**Run tests:**
```bash
python -m pytest tests/test_loop_runner.py -v
```

### Implementation Files

- `src/app/runner.py`:
  - `RunResult` dataclass: Execution result container
  - `run_loop()`: Main loop with exception handling and logging
  - `run_shadow_mode()`: Returns RunResult
  - `run_paper_mode()`: Returns RunResult
  - `main()`: CLI argument parsing with --loop/--once/--sleep-seconds
- `tests/test_loop_runner.py`: Comprehensive loop tests (7 test cases)

### CLI Reference

```bash
# Show help
python -m src.app.runner --help

# Run once (default)
python -m src.app.runner --mode shadow

# Explicit once mode
python -m src.app.runner --mode shadow --once

# Run in loop (hourly by default)
python -m src.app.runner --mode shadow --loop

# Custom sleep interval
python -m src.app.runner --mode shadow --loop --sleep-seconds 1800  # 30 min

# Paper dry-run loop
python -m src.app.runner --mode paper --dry-run --loop

# Paper live loop (requires credentials)
python -m src.app.runner --mode paper --loop
```

---

## Candidate System (Selector-to-Execution Pipeline)

### Overview

The candidate system implements a multi-layer architecture that separates **candidate sourcing** (AI/news/screeners) from **strategy confirmation** (price-action validation). This design enables:

- **Attribution tracking**: Full traceability from candidate → strategy → intent → order → fill → PnL
- **Risk isolation**: Strategies gate on both candidate recommendation AND price confirmation
- **Flexible sourcing**: Candidates can come from AI, news APIs, screeners, or manual input
- **Backward compatibility**: If no candidates exist, strategies fall back to config universe

**Design Principle:** Candidates represent *potential* trading opportunities that strategies must independently confirm. A BUY candidate does NOT automatically result in a trade - the strategy must verify the signal with price action.

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Selector (AI/News/Screener)                       │
│  - Generates candidates with metadata                       │
│  - Writes to out/selector/snapshot.json                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Candidate Store (src/app/candidates/)             │
│  - Loads and filters candidates                             │
│  - Applies: expiration, liquidity, deduplication            │
│  - Outputs: tradeable candidates only (BUY/SELL)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Strategy Execution (src/app/runner.py)            │
│  - Strategies evaluate candidate symbols                    │
│  - Generate intents ONLY if BOTH:                           │
│    * Candidate says BUY/SELL                                │
│    * Strategy confirms with price-action                    │
│  - Propagates candidate_id through to orders                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Ledger/Attribution (src/app/ledger.py)            │
│  - Tracks candidate_loaded events                           │
│  - Tracks strategy_intent_created events                    │
│  - Tracks order_placed events (with candidate_id)           │
│  - Enables full attribution analysis                        │
└─────────────────────────────────────────────────────────────┘
```

### RSS Selector Implementation

**Location:** `src/app/selector/`

The RSS Selector is a rules-based candidate generator targeting automation and energy sectors. It monitors RSS feeds, classifies headlines, extracts symbols, and maps sentiment to trading actions.

**Key Features:**
- **Targeted sectors**: Automation and Energy
- **Conservative symbol extraction**: Only explicit patterns `(SYMBOL)`, `SYMBOL:`, `$SYMBOL`
- **Sentiment analysis**: Maps headlines to BUY/SELL/WATCH based on keywords
- **Confidence scoring**: Quantifies signal strength (0.60-0.90)
- **Safety**: Selector NEVER places orders - only generates candidates

**Configuration:** `config/selector.yaml`
```yaml
sectors_enabled: [automation, energy]
rss_feeds:
  - https://example.com/automation
  - https://example.com/energy

keyword_rules:
  automation:
    keywords: [automation, robot, robotics, warehouse, PLC, ...]
  energy:
    keywords: [energy, oil, gas, solar, wind, battery, ...]

action_keywords:
  buy: [beats, raises guidance, upgrades, contract, ...]
  sell: [misses, cuts guidance, lawsuit, bankruptcy, ...]

speculative_words: [may, could, explores, considers, plans, might, potentially, looking at]

confidence_modifiers:
  base_confidence: 0.55
  strong_keyword_bonus: 0.10  # Per keyword match
  max_confidence: 0.90
  uncertain_symbol_penalty: 0.15
  vagueness_penalty: 0.10  # Subtract if speculative words without hard actions

screening:
  liquidity_floor_usd: 20000000  # $20M minimum avg daily dollar volume (if available)
  duplicate_suppression_minutes: 60  # Suppress same symbol+action within 60 minutes
```

**Execution:**
- **CLI**: `python -m src.app.selector.run_once`
- **Scheduled**: Windows Task Scheduler via `tools/windows/run_selector.ps1`
- **Frequency**: Every 15 minutes during market hours (8:50 AM - 4:10 PM ET)

**Output Files:**
- **Snapshot**: `out/selector/snapshot.json` - Current candidates with schema matching Candidate model
- **Events**: `out/selector/events.jsonl` - JSONL event log for processing history

**Dashboard API:** `GET /selector/status`
```json
{
  "last_run": "2026-01-05T10:00:00-05:00",
  "candidates_count": 5,
  "candidates_by_action": {"buy": 2, "sell": 1, "watch": 2},
  "last_error": null
}
```

**Processing Pipeline:**
1. Fetch RSS feeds from configured URLs
2. Parse RSS XML (title + description)
3. Classify sector via keyword matching (automation vs energy)
4. Extract symbol using regex: `\(([A-Z]{1,5})\)|([A-Z]{1,5}):|\$([A-Z]{1,5})\b`
5. Map action: sell keywords → SELL, buy keywords → BUY, else → WATCH
6. Compute confidence: `base + (keyword_count × bonus) - (uncertainty_penalty if no symbol) - (vagueness_penalty if speculative)`
7. Apply screening filters:
   - **Liquidity floor**: Reject if avg_dollar_volume < $20M (if data available)
   - **Duplicate suppression**: Reject if same symbol+action within 60 minutes
   - **Vagueness filter**: Already applied via confidence penalty in step 6
8. Create candidate with TTL (BUY: 180min, SELL: 120min, WATCH: 240min)
9. Write to snapshot.json and append event to events.jsonl

**Candidate Expiration (TTL):**
- BUY candidates: 180 minutes (3 hours)
- SELL candidates: 120 minutes (2 hours)
- WATCH candidates: 240 minutes (4 hours)

**Safety Controls:**
- Max candidates per run: 50 (configurable)
- Minimum confidence: 0.60 (configurable)
- Symbol allowlist/denylist support
- No network calls in tests (uses fixtures)

**Screening Quality Controls:**
- **Liquidity Floor**: Rejects candidates with avg_dollar_volume < $20M (if data available)
  - Graceful degradation: Allows candidates through when market data unavailable
  - Prevents illiquid penny stocks from entering the pipeline
  - Configurable via `screening.liquidity_floor_usd`
- **Vagueness Penalty**: Subtracts 0.10 confidence for speculative headlines
  - Applied when headline contains speculative words (may, could, explores, plans, etc.)
  - Only triggers if no hard action keywords present (beats, raises guidance, etc.)
  - Prevents weak speculation from generating candidates
  - Configurable via `confidence_modifiers.vagueness_penalty`
- **Duplicate Suppression**: Prevents same symbol+action within 60-minute window
  - Tracks recent candidates with automatic cleanup of expired entries
  - Prevents duplicate candidates from repeated RSS headlines
  - Configurable via `screening.duplicate_suppression_minutes`

**Testing:**
- Unit tests: `tests/test_selector.py` (49 tests covering all modules)
- Fixtures: `tests/fixtures/rss_automation.xml`, `tests/fixtures/rss_energy.xml`
- Tests verify: sector classification, symbol extraction, action mapping, confidence scoring, liquidity filtering, vagueness penalty, duplicate suppression, snapshot writing
- Test coverage:
  - 13 tests for core selector functionality
  - 10 tests for sector classification
  - 7 tests for confidence scoring
  - 5 tests for liquidity floor screening
  - 5 tests for vagueness penalty
  - 6 tests for duplicate suppression
  - 3 tests for end-to-end integration

**Documentation:** See `docs/SELECTOR.md` for detailed usage and configuration guide.

### Candidate Schema

**Location:** `src/app/candidates/schema.py`

**Core Fields:**
```python
class Candidate(BaseModel):
    # Identification
    candidate_id: str              # Stable unique identifier
    created_at: str                # ISO 8601 timestamp (UTC)
    expires_at: str                # ISO 8601 timestamp (UTC)

    # Trading details
    symbol: str                    # Trading symbol
    action: Action                 # BUY, SELL, WATCH, AVOID
    confidence: float              # 0.0 to 1.0
    horizon: Horizon               # INTRADAY, SWING, LONG

    # Optional metadata
    sector: str | None             # Sector classification
    event_type: str | None         # Event trigger (earnings, news, technical)
    tags: list[str]                # Additional tags
    reason: str | None             # Human-readable reason
    avg_dollar_volume: float | None  # For liquidity filtering
```

**Enums:**
- **Action:** `BUY`, `SELL`, `WATCH` (monitor only), `AVOID` (explicitly skip)
- **Horizon:** `INTRADAY` (same-day), `SWING` (2-10 days), `LONG` (weeks+)

**Methods:**
- `is_expired(now)`: Check if candidate has expired
- `is_tradeable()`: Returns True if action is BUY or SELL

### Storage Format

**Snapshot File:** `out/selector/snapshot.json`

```json
{
  "generated_at": "2026-01-05T04:11:20Z",
  "count": 3,
  "candidates": [
    {
      "candidate_id": "sample-001",
      "created_at": "2026-01-05T03:42:32Z",
      "expires_at": "2026-01-05T09:42:32Z",
      "symbol": "AAPL",
      "action": "buy",
      "confidence": 0.85,
      "horizon": "intraday",
      "sector": "Technology",
      "event_type": "earnings_beat",
      "tags": ["momentum", "breakout"],
      "reason": "Strong earnings beat with positive guidance",
      "avg_dollar_volume": 50000000000.0
    }
  ],
  "metadata": {
    "source": "ai_selector",
    "description": "GPT-4 generated candidates"
  }
}
```

**Event Log:** `out/selector/events.jsonl` (JSONL format, one event per line)
- Used for tracking candidate generation history
- Each line is a JSON object with timestamp and event_type

### Filtering Pipeline

**Location:** `src/app/candidates/store.py`

The filtering pipeline processes raw candidates through multiple stages:

1. **filter_valid()**: Remove expired candidates
   - Compares `expires_at` against current time
   - Timezone-aware comparison (handles naive/aware datetime)

2. **filter_by_liquidity()**: Remove illiquid candidates
   - Filters by `avg_dollar_volume >= min_dollar_volume`
   - Default threshold: $1M daily volume
   - Candidates with `avg_dollar_volume=None` pass through (unknown liquidity)

3. **deduplicate()**: Remove duplicate candidate_ids
   - Keeps newest candidate based on `created_at` timestamp
   - Handles updates to existing candidates

4. **Filter to tradeable actions**: Remove WATCH and AVOID
   - Only BUY and SELL actions pass through
   - WATCH candidates are tracked but not traded
   - AVOID candidates explicitly excluded

**Usage:**
```python
from src.app.candidates.store import get_tradeable_candidates, load_candidates

# Load and filter candidates
raw_candidates = load_candidates()  # Safe fallback to empty list
tradeable = get_tradeable_candidates(
    raw_candidates,
    now=datetime.now(UTC).replace(tzinfo=None),
    min_dollar_volume=1_000_000.0
)
```

### Integration with Strategies

**Location:** `src/app/runner.py` (shadow and paper modes)

**Execution Flow:**

1. **Load Candidates:**
   ```python
   raw_candidates = load_candidates()
   tradeable_candidates = get_tradeable_candidates(raw_candidates, now, min_dollar_volume)
   ```

2. **Build Universe:**
   ```python
   if tradeable_candidates:
       universe = [c.symbol for c in tradeable_candidates]
       candidate_map = {c.symbol: c.candidate_id for c in tradeable_candidates}
   else:
       universe = config.universe_symbols  # Fallback to config
       candidate_map = {}
   ```

3. **Strategy Evaluation:**
   ```python
   for strategy in strategies:
       intents = strategy.generate_intents(universe, market_data, candidate_map)

       for intent in intents:
           # intent.candidate_id contains the candidate attribution
           if intent.target_quantity > 0:  # Strategy confirmed candidate
               # Proceed to order placement
   ```

**Strategy Interface:**
```python
class Strategy(ABC):
    @abstractmethod
    def generate_intents(
        self,
        universe: list[str],
        market_data: dict,
        candidate_map: dict[str, str] | None = None
    ) -> list[PositionIntent]:
        pass
```

**PositionIntent Model:**
```python
@dataclass
class PositionIntent:
    symbol: str
    target_quantity: int
    conviction: float
    reason: str
    candidate_id: str | None = None  # Propagated from candidate_map
```

### Ledger Events

**Location:** `src/app/ledger.py`

The ledger tracks candidate attribution through the full execution pipeline:

#### CandidateLoadedEvent
Emitted when candidates are loaded from snapshot:
```python
{
  "event_id": "uuid",
  "timestamp": "2026-01-05T04:11:20+00:00",
  "event_type": "candidate_loaded",
  "count_total": 3,
  "count_tradeable": 2,
  "symbols": ["AAPL", "SPY"],
  "snapshot_path": "out/selector/snapshot.json"
}
```

#### CandidateSelectedEvent
Emitted when a strategy selects a candidate for evaluation:
```python
{
  "event_id": "uuid",
  "timestamp": "2026-01-05T04:11:21+00:00",
  "event_type": "candidate_selected",
  "candidate_id": "sample-001",
  "symbol": "AAPL",
  "action": "buy",
  "confidence": 0.85,
  "horizon": "intraday",
  "strategy_id": "Trend_MA20",
  "reason": "Candidate passed strategy filters"
}
```

#### StrategyIntentCreatedEvent
Emitted when a strategy generates a position intent:
```python
{
  "event_id": "uuid",
  "timestamp": "2026-01-05T04:11:22+00:00",
  "event_type": "strategy_intent_created",
  "strategy_id": "Trend_MA20",
  "version": 1,
  "symbol": "AAPL",
  "target_quantity": 1,
  "conviction": 0.85,
  "reason": "Price 150.0 > MA(20) 145.0",
  "candidate_id": "sample-001"
}
```

#### OrderPlacedEvent (Updated)
Includes candidate_id for full attribution:
```python
{
  "event_id": "uuid",
  "timestamp": "2026-01-05T04:11:23+00:00",
  "event_type": "order_placed",
  "strategy_id": "Trend_MA20",
  "version": 1,
  "client_order_id": "order-123",
  "symbol": "AAPL",
  "side": "buy",
  "quantity": "1",
  "order_type": "market",
  "limit_price": null,
  "candidate_id": "sample-001"
}
```

**Ledger File:** `out/ledger/YYYY-MM-DD.jsonl` (one event per line)

### Attribution Chain Example

Full end-to-end attribution flow:

```
1. candidate_loaded
   ├─ 3 total candidates loaded
   └─ 2 tradeable (AAPL buy, SPY buy)

2. strategy_intent_created
   ├─ Trend_MA20 → AAPL
   ├─ candidate_id: sample-001
   └─ reason: "Price > MA"

3. order_placed
   ├─ AAPL market buy 1 share
   ├─ candidate_id: sample-001
   └─ strategy_id: Trend_MA20

4. order_filled
   ├─ AAPL filled @ $150.00
   └─ candidate_id: sample-001

5. position_update
   └─ AAPL position: +1 @ $150.00, PnL: $0.00

Query: "Which candidate generated the most PnL?"
Answer: Filter ledger by candidate_id, sum realized PnL
```

### Backward Compatibility

The candidate system is fully backward compatible:

1. **Empty Candidate List:**
   - `load_candidates()` returns `[]` if no snapshot exists
   - Runner falls back to `config.universe_symbols`
   - No candidates = no candidate-related ledger events

2. **Optional candidate_id:**
   - All `candidate_id` fields are `str | None`
   - Legacy code paths set `candidate_id=None`
   - Existing intents/orders continue to work

3. **Config Universe Fallback:**
   ```python
   if tradeable_candidates:
       universe = [c.symbol for c in tradeable_candidates]
   else:
       universe = config.universe_symbols  # Fallback
   ```

4. **No Breaking Changes:**
   - Existing strategy interface preserved
   - `candidate_map` parameter is optional
   - All tests pass (389/395, 6 pre-existing failures)

### Testing

**Test File:** `tests/test_candidates.py`

**Test Coverage:**
- Schema validation (19 tests)
- Candidate expiration and tradeability
- Confidence range validation (0.0-1.0)
- Timestamp format validation (ISO 8601)
- Storage (write/load snapshot)
- Filtering pipeline:
  - Expiration filtering
  - Liquidity filtering
  - Deduplication (keeps newest)
  - Full pipeline (get_tradeable_candidates)
- Propagation:
  - PositionIntent includes candidate_id
  - Strategies propagate candidate_id
- Ledger events:
  - CandidateLoadedEvent
  - StrategyIntentCreatedEvent
  - OrderPlacedEvent with candidate_id

**Sample Data Generation:**
```bash
python -m src.app.candidates.sample_snapshot --output out/selector/snapshot.json --force
```

Generates 3 sample candidates:
- AAPL (buy, confidence=0.85, intraday)
- SPY (buy, confidence=0.72, swing)
- TSLA (watch, confidence=0.65, intraday)

### Future Enhancements

**Short Term:**
- Add `CandidateSelectedEvent` emission when strategies evaluate candidates
- Wire `candidate_id` through to actual order placement (currently in events only)
- Add ledger querying/reporting tools for attribution analysis

**Medium Term:**
- Implement AI-powered candidate generation (GPT-4 + news APIs)
- Add candidate scoring/ranking based on historical performance
- Support per-strategy candidate filtering (sector, horizon, confidence thresholds)
- Add candidate expiration notifications

**Long Term:**
- Real-time candidate streaming (WebSocket)
- Machine learning model for candidate quality scoring
- Multi-source candidate aggregation (AI + screeners + news)
- Candidate performance analytics dashboard

---

## Universe Configuration

### Overview

The trading universe can be configured using sector groups for better organization and per-sector control. This enables the UI to display checkboxes for each sector and allows the loop to trade only enabled sectors.

### Configuration Format

**Sector-Based Format** (Recommended):

```yaml
universe:
  # Fallback behavior when resolving symbols
  # Options: "preserve_order" (default), "alphabetical"
  fallback_mode: "preserve_order"

  # Sector groups
  sectors:
    core_index:
      enabled: true
      description: "Major market index ETFs"
      symbols:
        - SPY
        - QQQ

    mega_cap_tech:
      enabled: true
      description: "Mega-cap technology stocks"
      symbols:
        - AAPL
        - MSFT
        - NVDA
        - AMD
        - META
        - GOOGL
        - TSLA

    us_sector_etfs:
      enabled: true
      description: "US sector rotation ETFs"
      symbols:
        - XLF
        - XLE
        - XLV
```

**Legacy Format** (Still Supported):

```yaml
universe:
  core:
    symbols:
      - SPY
      - QQQ
      - AAPL
      - MSFT
      # ...
```

### Resolution Logic

**Implementation:** `src/app/universe.py`

**Resolution Priority:**
1. **Legacy format** (`universe.core.symbols`) - Takes precedence if both formats present
2. **Sector format** (`universe.sectors`) - New structured format
3. **Empty** - Returns empty list with warning

**Deduplication:**
- Symbols can appear in multiple sectors
- First occurrence is preserved (sector declaration order)
- Duplicates are removed and counted
- Warning emitted if duplicates found

**Fallback Modes:**
- `preserve_order` - Maintain sector declaration order (default)
- `alphabetical` - Sort symbols alphabetically
- `random` - Randomize order (testing only)

**Integration:**
```python
# In src/app/config.py:
resolution = resolve_universe(yaml_config)
config.universe_symbols = resolution.symbols

# In src/app/runner.py:
universe = config.universe_symbols  # Resolved from sectors
```

### API Endpoint

**GET /universe/sectors** - View sector configuration and resolved symbols

**Response:**
```json
{
  "sectors": [
    {
      "sector_name": "core_index",
      "enabled": true,
      "description": "Major market index ETFs",
      "symbols": ["SPY", "QQQ"],
      "symbol_count": 2
    },
    {
      "sector_name": "mega_cap_tech",
      "enabled": true,
      "description": "Mega-cap technology stocks",
      "symbols": ["AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "TSLA"],
      "symbol_count": 7
    },
    {
      "sector_name": "us_sector_etfs",
      "enabled": true,
      "description": "US sector rotation ETFs",
      "symbols": ["XLF", "XLE", "XLV"],
      "symbol_count": 3
    }
  ],
  "resolved_symbols": [
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA",
    "AMD", "META", "GOOGL", "TSLA", "XLF", "XLE", "XLV"
  ],
  "total_symbols": 12,
  "fallback_mode": "preserve_order",
  "deduplication_count": 0,
  "warnings": [],
  "source": "sectors"
}
```

### Operator Overrides

**Implementation:** `src/app/universe_registry.py`

Universe sector configuration can be modified at runtime via dashboard UI. Changes are staged immediately but activated at the start of the next trading loop tick (next-tick activation pattern).

**Override File:** `out/universe_overrides.json`

**Persistence Format:**
```json
{
  "sectors": {
    "mega_cap_tech": {
      "enabled": false,
      "active_version": 1,
      "pending_version": 2,
      "last_modified": "2026-01-06T16:30:00.123456+00:00"
    },
    "core_index": {
      "enabled": true,
      "active_version": 1,
      "pending_version": null,
      "last_modified": null
    }
  },
  "registry_version": 1,
  "last_saved": "2026-01-06T16:30:00.123456+00:00"
}
```

**File Characteristics:**
- Only stores overrides for **changed sectors** (not all sectors)
- Atomic writes using temp file + rename pattern
- Version tracking: `active_version` (current) vs `pending_version` (staged)
- Timestamps in ISO 8601 format with UTC timezone

**Activation Behavior:**

1. **Stage Change** (Immediate):
   - Operator toggles sector checkbox in dashboard
   - POST request updates registry in-memory
   - Override saved to `out/universe_overrides.json`
   - `pending_version` incremented
   - Dashboard shows orange "Pending" badge

2. **Activate Change** (Next Loop Tick):
   - Runner calls `universe_registry.check_and_activate_pending()`
   - `pending_version` promoted to `active_version`
   - Changes take effect for current loop iteration
   - Pending badge removed from dashboard

**API Endpoints:**

**POST /universe/sectors/{sector_name}/enable**
```bash
# Disable mega_cap_tech sector
curl -X POST http://localhost:8000/universe/sectors/mega_cap_tech/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Response:
{
  "success": true,
  "message": "Sector mega_cap_tech disabled. Change will activate on next loop tick.",
  "pending_version": 2
}
```

**POST /universe/reset**
```bash
# Reset all sectors to base config defaults
curl -X POST http://localhost:8000/universe/reset \
  -H "Content-Type: application/json" \
  -d '{}'

# Response:
{
  "success": true,
  "message": "Universe reset to defaults. All sectors enabled.",
  "pending_version": null
}
```

**Dashboard UI:**

Located in the Universe Sectors section (above Strategies):

- **Per-sector toggle switches** - Enable/disable individual sectors
- **Live stats** - Enabled sectors count and total symbols
- **Pending indicators** - Orange border on cards with pending changes
- **Reset button** - One-click restore to base config defaults

**Runner Integration:**

```python
# In src/app/runner.py (loop mode):
# Initialize registry at startup
universe_registry = UniverseRegistry()

# At start of each loop iteration (after strategy activation):
activated = universe_registry.check_and_activate_pending()
if activated:
    print("Universe configuration changes activated:")
    for sector_name, old_version, new_version in activated:
        print(f"  {sector_name}: v{old_version} -> v{new_version}")

# Use registry for universe resolution:
if universe_registry is not None:
    resolution = universe_registry.resolve()
    universe = resolution.symbols
else:
    universe = config.universe_symbols  # Fallback to base config
```

**Rollback Strategy:**

1. **Delete overrides file:**
   ```bash
   rm out/universe_overrides.json
   ```

2. **Restart bot:**
   - Will use base config from `config/config.yaml`
   - No code changes needed for rollback

3. **Or use Reset button:**
   - Click "Reset to Defaults" in dashboard
   - Deletes overrides file and reloads
   - Immediate rollback without restart

**Safety Features:**

- **Atomic writes** - Temp file + rename prevents corruption
- **Version tracking** - Detects conflicts and ordering
- **Next-tick activation** - Changes don't affect current iteration
- **Backward compatible** - Works without overrides file
- **Unknown sectors ignored** - Safely handles stale overrides

**Example Workflow:**

1. Operator disables `mega_cap_tech` sector via dashboard
2. Dashboard shows orange "Pending" badge
3. Current loop iteration completes with old universe
4. Next loop iteration starts
5. Runner activates pending change: `mega_cap_tech: v1 -> v2`
6. Universe now excludes AAPL, MSFT, NVDA, AMD, META, GOOGL, TSLA
7. Strategies trade only remaining sectors
8. Pending badge removed from dashboard

### Backward Compatibility

**Legacy Support:**
- Old `universe.core.symbols` format still works
- Takes precedence if both formats present
- Warning logged suggesting migration
- No code changes needed to support both formats

**Migration Path:**
1. Code supports both formats simultaneously
2. Update `config/config.yaml` to new sector format
3. Verify resolved symbols match expected list
4. No breaking changes - can revert config anytime

**Rollback Strategy:**
- Revert `config/config.yaml` to legacy format
- Code automatically falls back to legacy resolution
- No code changes needed for rollback

### Default Configuration

By default, all sectors are enabled and produce the same symbol list as the legacy format:

**Resolved Symbols:**
```
SPY, QQQ, AAPL, MSFT, NVDA, AMD, META, GOOGL, TSLA, XLF, XLE, XLV
```

**Sectors:**
- `core_index` (2 symbols): SPY, QQQ
- `mega_cap_tech` (7 symbols): AAPL, MSFT, NVDA, AMD, META, GOOGL, TSLA
- `us_sector_etfs` (3 symbols): XLF, XLE, XLV

### Testing

**Test File:** `tests/test_universe.py`

**Test Coverage:**
- Legacy format backward compatibility
- New sector format resolution
- Disabled sectors exclusion
- Symbol deduplication across sectors
- Fallback mode sorting (alphabetical, preserve_order)
- Empty universe handling
- Exact backward compatibility match

**Config Integration Tests:** `tests/test_config.py`
- Sector-based universe resolution through config loader
- Legacy format still works through config loader

**API Tests:** `tests/test_api.py`
- GET /universe/sectors endpoint response structure
- Sector list validation
- Resolved symbols validation

### Future Enhancements

**Short Term:**
- POST endpoints to toggle sector enabled state (requires persistence)
- UI checkboxes for per-sector control in dashboard

**Medium Term:**
- Per-strategy sector filtering
- Dynamic sector creation via UI
- Sector performance analytics

**Long Term:**
- AI-powered sector recommendations
- Auto-balancing across sectors
- Correlation-based sector grouping

---

## Strategy Dashboard System

### Overview

The strategy dashboard provides a read-only monitoring interface and safe configuration API for managing multiple trading strategies on a single Alpaca account. The system is **optional** - the bot runs normally if the dashboard is never started.

**Key Design Principles:**
- **Next-tick activation**: All configuration changes are staged and activate only at the start of the next trading loop iteration
- **No mid-loop changes**: Zero impact on in-flight orders or execution logic
- **Optional service**: Bot functions identically whether dashboard is running or not
- **Safe edits**: All changes go through validation and version tracking
- **Backward compatible**: Existing execution, risk, and order logic unchanged

### Architecture Components

#### 1. Strategy Registry (`src/app/strategy_registry.py`)

**Purpose:** Central configuration management with version tracking and deterministic loading.

**Data Model:**
```python
@dataclass
class StrategyConfig:
    strategy_id: str              # Unique identifier
    name: str                     # Display name
    description: str              # Human-readable description
    enabled: bool                 # Whether strategy is active
    weight: float                 # Capital allocation (0.0 to 1.0)
    params: dict[str, Any]        # Strategy-specific parameters
    risk_limits: dict             # Per-strategy risk constraints
    active_version: int           # Currently running version
    pending_version: int | None   # Staged version for next tick
    last_modified: datetime       # Last configuration change timestamp

@dataclass
class GlobalConfig:
    max_daily_loss: float
    max_total_positions: int
    max_order_notional: float
    bar_timeframe: str
    market_open_hour: int
    market_open_minute: int
    market_close_hour: int
    market_close_minute: int
```

**Configuration Sources:**
1. **Base Configuration** (`config/strategies.yaml`):
   - Version-controlled strategy definitions
   - Immutable baseline configuration
   - Defines default parameters and risk limits

2. **Operator Overrides** (`out/strategies_overrides.json`):
   - Runtime configuration changes
   - Persisted modifications from dashboard/API
   - Merged on top of base configuration

**Loading Process:**
1. Load base config from YAML
2. Parse strategies and global settings
3. Load overrides from JSON (if exists)
4. Apply overrides with deterministic merge (override wins)
5. Initialize version tracking

**API Methods:**
- `load()` - Load and merge configurations
- `get_strategy(strategy_id)` - Get specific strategy config
- `get_enabled_strategies()` - Filter for enabled strategies only
- `stage_change(strategy_id, changes)` - Stage configuration change
- `check_and_activate_pending()` - Activate pending versions (called at loop start)
- `_save_overrides()` - Persist changes to JSON (atomic write)

**Version Tracking:**
- `active_version`: Currently running configuration version
- `pending_version`: Configuration staged for next loop tick
- Each `stage_change()` increments `pending_version`
- `check_and_activate_pending()` promotes `pending_version` to `active_version`

**Example Base Configuration** (`config/strategies.yaml`):
```yaml
strategies:
  - strategy_id: "Trend_MA20"
    name: "Trend Following (MA20)"
    description: "SMA crossover with 10/20 periods"
    enabled: true
    weight: 0.4
    params:
      sma_fast_period: 10
      sma_slow_period: 20
    risk_limits:
      max_position_size: 5000
      max_positions: 3
      max_daily_loss: 500

global:
  max_daily_loss: 1000
  max_total_positions: 10
  max_order_notional: 10000
  bar_timeframe: "1Min"
```

#### 2. Event Ledger (`src/app/ledger.py`)

**Purpose:** Append-only event log for tracking strategy decisions, orders, and fills with deterministic state reconstruction.

**File Format:** JSONL (JSON Lines) - one event per line
- Location: `out/ledger/YYYY-MM-DD.jsonl`
- Daily rotation (one file per calendar day)

**Event Types:**
1. `strategy_config_activated` - Strategy configuration version activated
2. `signal_generated` - Strategy produced a trading signal
3. `order_placed` - Order submitted to broker
4. `order_filled` - Order execution completed
5. `position_update` - Position state changed

**Event Schema:**
```python
@dataclass
class LedgerEvent:
    event_id: str        # UUID
    timestamp: str       # ISO 8601 timestamp (UTC)
    event_type: str      # Event type discriminator
```

**Example Events:**
```json
{"event_id": "uuid", "timestamp": "2024-01-15T10:30:00Z", "event_type": "strategy_config_activated", "strategy_id": "Trend_MA20", "version": 2, "config_snapshot": {...}}
{"event_id": "uuid", "timestamp": "2024-01-15T10:31:00Z", "event_type": "signal_generated", "strategy_id": "Trend_MA20", "version": 2, "symbol": "AAPL", "signal_type": "buy", "strength": 0.85}
{"event_id": "uuid", "timestamp": "2024-01-15T10:31:05Z", "event_type": "order_placed", "strategy_id": "Trend_MA20", "version": 2, "client_order_id": "AAPL-uuid", "symbol": "AAPL", "side": "buy", "quantity": "10"}
{"event_id": "uuid", "timestamp": "2024-01-15T10:31:30Z", "event_type": "order_filled", "strategy_id": "Trend_MA20", "version": 2, "client_order_id": "AAPL-uuid", "fill_price": "150.50"}
```

**API Methods:**
- `append(event)` - Append event to today's ledger
- `read_all(date=None)` - Read all events (optionally for specific date)
- `rebuild_state()` - Deterministically reconstruct state from event stream

**State Reconstruction:**
The `rebuild_state()` method processes all events in chronological order to reconstruct:
- Active strategy configurations
- Per-strategy positions (symbol -> quantity, avg_price, unrealized_pnl)
- Per-strategy realized PnL
- Order history with fill status

This enables:
- Crash recovery without external state
- Historical PnL attribution
- Audit trail for all strategy decisions
- Debugging and backtesting

#### 3. Order Attribution

**Purpose:** Track which strategy generated each order for multi-strategy attribution.

**Model Changes:**
```python
class Order(BaseModel):
    # ... existing fields ...
    strategy_id: str | None = None      # Strategy that generated order
    strategy_version: int | None = None # Strategy version at order time

class OrderRecord(BaseModel):  # CSV output
    # ... existing fields ...
    strategy_id: str | None = None
    strategy_version: int | None = None

class FillRecord(BaseModel):   # CSV output
    # ... existing fields ...
    strategy_id: str | None = None
    strategy_version: int | None = None

class TradeRecord(BaseModel):  # CSV output
    # ... existing fields ...
    strategy_id: str | None = None
    strategy_version: int | None = None
```

**CSV Headers Updated:**
- `orders.csv`: Added `strategy_id,strategy_version` columns
- `fills.csv`: Added `strategy_id,strategy_version` columns
- `trades.csv`: Added `strategy_id,strategy_version` columns

**Backward Compatibility:**
- Fields are optional (default to `None`)
- Existing orders without attribution still work
- Empty strings in CSV if no attribution

#### 4. Trading Loop Integration (`src/app/runner.py`)

**Initialization:**
```python
# Before loop starts
registry = StrategyRegistry()
print(f"Registry loaded: {len(registry.get_state().strategies)} strategies configured")
```

**Next-Tick Activation:**
```python
# At START of each loop iteration
activated = registry.check_and_activate_pending()
if activated:
    for strategy_id, old_version, new_version in activated:
        print(f"  {strategy_id}: v{old_version} → v{new_version}")
```

**Execution Flow:**
1. Loop iteration begins
2. `check_and_activate_pending()` promotes any staged changes
3. Log activated version changes
4. Execute trading logic with **new** configuration
5. Sleep until next iteration

**Safety:**
- Changes activate at loop boundary only
- No mid-loop configuration drift
- Atomic version transitions
- Deterministic activation timing

#### 5. FastAPI Service (`src/ui_api/app.py`)

**Purpose:** RESTful API for read-only monitoring and safe configuration edits.

**Startup:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global registry, ledger
    registry = StrategyRegistry()
    ledger = Ledger()
    yield
```

**GET Endpoints (Read-Only):**

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `GET /health` | Service health check | `{status, timestamp, registry_loaded, ledger_available}` |
| `GET /health/detailed` | Comprehensive system health | `{status, timestamp, market_status, last_loop_tick, last_error, registry_loaded, ledger_available, single_instance_ok, trading_paused}` |
| `GET /account/summary` | Account configuration | `{total_capital, max_daily_loss, max_total_positions, enabled_strategies_count, total_strategies_count}` |
| `GET /strategies` | All strategies with config | `{strategies: [...], global_config: {...}}` |
| `GET /allocation` | Allocation with normalized weights | `{equity_base, timestamp, strategies: [{strategy_id, enabled, configured_weight, normalized_weight, budget, utilization}], mode}` |
| `GET /candidates` | Current candidate symbols | `{candidates: [{symbol, action, confidence, horizon, sector, tags, reason, expires_at}], count, last_generated}` |
| `GET /activity?limit=N` | Recent ledger events | `{events: [...], total_events}` |

**POST Endpoints (Safe Edit - Staged Changes):**

| Endpoint | Purpose | Request Body | Returns |
|----------|---------|--------------|---------|
| `POST /strategies/{id}/enable` | Enable/disable strategy | `{enabled: bool}` | `{success, message, pending_version}` |
| `POST /strategies/{id}/weight` | Update capital weight | `{weight: float}` | `{success, message, pending_version}` |
| `POST /strategies/{id}/params` | Update parameters | `{params: dict}` | `{success, message, pending_version}` |
| `POST /pause_trading` | Pause/resume order submission | `{paused: bool}` | `{success, message}` |
| `POST /universe/sectors/{sector}/tickers` | Add/remove tickers manually | `{add: [str], remove: [str]}` | `{success, message, pending_version}` |
| `POST /account/summary` | Update account settings | `{total_capital?, max_daily_loss?, max_total_positions?}` | `{success, message}` |

**Read-Only Performance Endpoints:**

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `GET /account/performance` | Broker account performance | `{equity, last_equity, cash, buying_power, day_pl, day_pl_pct, total_pl, total_pl_pct, data_source, message}` |
| `GET /account/performance/series?hours=24` | Equity time series | `{points: [{timestamp, equity, cash, mode}], count, hours}` |

**Operational Control Endpoints:**

- **GET /health/detailed**: Returns comprehensive system status including market hours (9:30 AM - 4:00 PM ET), last loop tick timestamp, last error from logs, and trading paused state.

- **GET /allocation**: Returns per-strategy allocation details with normalized weights. When strategies are enabled/disabled, weights are dynamically normalized so they sum to 1.0. Shows equity-based budgets when account equity is available.

- **GET /candidates**: Returns current symbol candidates from `out/selector/snapshot.json`. Candidates have expiration timestamps and are refreshed by external selector process.

- **POST /pause_trading**: Creates/removes `state/pause_trading.flag` file. When paused, the trading loop continues to evaluate signals and log events, but skips order submission entirely. This is a safety mechanism for emergency stops without killing the bot process.

**Validation:**
- Weight must be 0.0 to 1.0 (Pydantic validation)
- Strategy ID must exist (ValueError on unknown strategy)
- All changes persist to `out/strategies_overrides.json`
- All changes set `pending_version` and activate on next tick

**Error Handling:**
- 400 Bad Request: Invalid input (weight out of range, unknown strategy)
- 500 Internal Server Error: Failed to persist changes
- 503 Service Unavailable: Registry/ledger not loaded
- Proper exception chaining with `from e`

**Starting the Service:**
```bash
uvicorn src.ui_api.app:app --reload --port 8000
```

**API Documentation:**
- Automatic OpenAPI schema: http://localhost:8000/docs
- ReDoc alternative: http://localhost:8000/redoc

#### 6. HTML Dashboard (`src/ui_api/dashboard.html`)

**Purpose:** Single-page web application for visual strategy monitoring and configuration.

**Served At:** `GET /` - http://localhost:8000

**Features:**

1. **Health & Status Panel:**
   - Market status indicator (open/closed based on 9:30 AM - 4:00 PM ET)
   - Last loop tick timestamp
   - System health status (shows errors if any)
   - Pause trading toggle (global kill switch)
   - Warning banner when trading is paused

2. **Account Summary:**
   - Total capital (proxy calculation)
   - Max daily loss limit
   - Max total positions
   - Enabled strategies count

3. **Strategy Cards:**
   - Visual status badges (ENABLED/DISABLED)
   - Pending version indicator (orange border + badge)
   - Key metrics:
     - Configured Weight %
     - Normalized Weight % (dynamic, sums to 100%)
     - Equity-based Budget (when available)
   - Interactive controls:
     - Toggle switch for enable/disable
     - Range slider for weight adjustment (0-100%)
     - Collapsible parameters view (JSON formatted)
     - Edit button for detailed parameter changes

4. **Candidates Inspector:**
   - Table showing symbol candidates from selector
   - Filterable by:
     - Action (buy/sell/watch)
     - Minimum confidence threshold
     - Symbol/sector/tag search
   - Displays:
     - Symbol, action, confidence bar, horizon
     - Sector classification
     - Tags (momentum, breakout, etc.)
     - Reason/rationale
     - Expiration timestamp
   - Shows count and last generated time

5. **Activity Feed:**
   - Recent events from ledger (last 20)
   - Color-coded by event type:
     - Orange: config changes
     - Blue: signals
     - Purple: orders
     - Green: fills
   - Shows timestamp, event type, strategy ID, details
   - Scrollable feed

6. **Auto-Refresh:**
   - Automatic reload every 30 seconds
   - Manual refresh button
   - "Last updated" timestamp

7. **User Feedback:**
   - Success messages (green, auto-dismiss after 3s)
   - Error messages (red, auto-dismiss after 5s)
   - Loading states during API calls
   - Graceful error handling

**Technology:**
- Self-contained single HTML file
- Embedded CSS (no external stylesheets)
- Vanilla JavaScript (no frameworks)
- Mobile-responsive design
- Dark theme (`#0f172a` background)

**API Integration:**
```javascript
// On load and every 30s
async function loadDashboard() {
    const accountData = await fetch('/account/summary');
    const strategiesData = await fetch('/strategies');
    const activityData = await fetch('/activity?limit=20');
    // Update UI
}

// User interactions
async function toggleStrategy(strategyId, enabled) {
    await fetch(`/strategies/${strategyId}/enable`, {
        method: 'POST',
        body: JSON.stringify({enabled})
    });
    showSuccess('Change will activate on next loop tick');
    loadDashboard();  // Refresh to show pending version
}
```

#### 7. Operator UI Enhancements (Manual Controls)

**Purpose:** Three operator-gated features for manual intervention and monitoring: Sector Editor (manual ticker management), Account Summary Editor (risk settings), and P&L Section (real-time performance).

##### Feature 1: Sector Editor (Manual Ticker Management)

**Backend:** `POST /universe/sectors/{sector_name}/tickers`

**Request Model:**
```python
class UpdateTickersRequest(BaseModel):
    add: list[str] = Field(default_factory=list)      # Tickers to add (e.g., ["NVDA", "AMD"])
    remove: list[str] = Field(default_factory=list)    # Tickers to remove (e.g., ["TSLA"])
```

**Endpoint Behavior:**
1. Validates sector exists in UniverseRegistry
2. Normalizes tickers (uppercase, dedupe)
3. Checks for overlaps between add/remove lists (HTTP 400 if found)
4. Stages changes via `universe_registry.stage_constituent_change()` (increments pending_version)
5. Attempts tradability check via Alpaca broker (best-effort, warns if unavailable)
6. Logs to ledger with event type `manual_sector_tickers_staged`
7. Returns success with pending_version and warnings list

**Validation:**
- At least one of `add` or `remove` must be non-empty (HTTP 400 if both empty)
- Sector must exist (HTTP 404 if not found)
- No duplicate tickers across add/remove (HTTP 400 if overlap)
- Uppercase normalization applied automatically
- Deduplication within each list

**Ledger Event:**
```json
{
  "event_type": "manual_sector_tickers_staged",
  "sector_name": "mega_cap_tech",
  "add": ["NVDA", "AMD"],
  "remove": ["TSLA"],
  "pending_version": 3,
  "actor": "operator_ui"
}
```

**UI Components:**

1. **"View / Edit Tickers" Button** on each sector card
   - Opens sector editor modal
   - Shows current tickers as removable pills
   - Ticker count badge

2. **Sector Editor Modal:**
   - **Current Tickers List:**
     - Displays all tickers as pills with X remove buttons
     - Scrollable (max-height: 300px)
     - Live count display
   - **Add Tickers Input:**
     - Text input accepting comma or space-separated tickers
     - "Add" button to stage additions
     - Normalizes to uppercase automatically
   - **Remove Tickers Input:**
     - Text input accepting comma or space-separated tickers
     - "Remove" button to stage removals
     - Alternative to clicking X on individual pills
   - **Save Changes Button:**
     - Shows confirmation dialog: "Add N ticker(s) and Remove M ticker(s) for {sector}? Changes will be staged."
     - Calls POST endpoint with aggregated add/remove lists
     - Displays success/error messages
     - Closes modal and refreshes sector list on success

**JavaScript Functions:**
```javascript
// State tracking for modal
let currentSector = null;
let currentTickers = [];      // Working copy of tickers
let tickersToAdd = [];        // Accumulated additions
let tickersToRemove = [];     // Accumulated removals

function openSectorEditor(sectorName, tickers) {
    // Initialize modal with sector data
}

function addTickers() {
    // Parse input, add to currentTickers and tickersToAdd
}

function removeTickers() {
    // Parse input, remove from currentTickers, add to tickersToRemove
}

async function saveSectorChanges() {
    // POST aggregated changes, handle response
}
```

**Activation Flow:**
1. Operator clicks "View / Edit Tickers" on sector card
2. Modal opens showing current ticker list
3. Operator adds/removes tickers via input fields or pill buttons
4. Changes tracked in modal state (not yet committed)
5. Operator clicks "Save Changes"
6. Confirmation dialog shown
7. POST request sent with add/remove lists
8. UniverseRegistry stages changes (pending_version++)
9. Success message shown: "Added N ticker(s), Removed M ticker(s) to {sector}. Changes staged (vX)."
10. Changes activate at next loop tick via `universe_registry.check_and_activate_pending()`

##### Feature 2: Account Summary Editor

**Backend:** `POST /account/summary` and updated `GET /account/summary`

**Request Model:**
```python
class AccountSummaryUpdateRequest(BaseModel):
    total_capital: float | None = Field(default=None, ge=1000.0)       # Min $1000
    max_daily_loss: float | None = Field(default=None, ge=100.0)       # Min $100
    max_total_positions: int | None = Field(default=None, ge=1, le=50) # Range 1-50
```

**Endpoint Behavior:**
1. Loads existing settings from `out/account_summary.json` (if exists)
2. Applies partial updates (only non-None fields)
3. Validates updated values (Pydantic constraints)
4. Saves atomically to `out/account_summary.json` (temp file + rename)
5. Logs to ledger with event type `account_summary_updated` (includes old/new values)
6. Returns success with list of updated fields

**Persistence File:** `out/account_summary.json`
```json
{
  "total_capital": 50000.0,
  "max_daily_loss": 1500.0,
  "max_total_positions": 15
}
```

**Updated GET Endpoint:**
The `GET /account/summary` endpoint now checks `out/account_summary.json` first:
- If file exists: Load settings from file
- If file missing or read error: Fall back to config defaults
- Priority: persisted settings > config defaults
- Backwards compatible: No breaking changes

**Ledger Event:**
```json
{
  "event_type": "account_summary_updated",
  "old_settings": {"total_capital": 10000, "max_daily_loss": 1000, "max_total_positions": 10},
  "new_settings": {"total_capital": 50000, "max_daily_loss": 1500, "max_total_positions": 15},
  "updated_fields": ["total_capital", "max_daily_loss", "max_total_positions"],
  "actor": "operator_ui"
}
```

**UI Components:**

1. **"Edit" Button** in Account Summary section header
   - Opens account summary editor modal

2. **Account Summary Editor Modal:**
   - **Total Capital Input:**
     - Number input, min $1000, step $100
     - Pre-filled with current value
   - **Max Daily Loss Input:**
     - Number input, min $100, step $10
     - Pre-filled with current value
   - **Max Total Positions Input:**
     - Number input, range 1-50, step 1
     - Pre-filled with current value
   - **Save Changes Button:**
     - Validates all fields non-empty
     - Shows confirmation: "Update account settings? This will affect risk limits."
     - Calls POST endpoint
     - Displays success/error messages
     - Closes modal and refreshes dashboard on success

**JavaScript Functions:**
```javascript
function openAccountSummaryEditor() {
    // Load current values from DOM into modal inputs
    document.getElementById('edit-total-capital').value = parseFloat(
        document.getElementById('total-capital').textContent.replace(/[$,]/g, '')
    );
    // ... similar for other fields
    document.getElementById('account-summary-modal').classList.add('active');
}

async function saveAccountSummary() {
    const totalCapital = parseFloat(document.getElementById('edit-total-capital').value);
    const maxDailyLoss = parseFloat(document.getElementById('edit-max-daily-loss').value);
    const maxPositions = parseInt(document.getElementById('edit-max-positions').value);

    if (!confirm('Update account settings? This will affect risk limits.')) return;

    const response = await fetch('/account/summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            total_capital: totalCapital,
            max_daily_loss: maxDailyLoss,
            max_total_positions: maxPositions
        })
    });
    // Handle response...
}
```

**Backwards Compatibility:**
- If `out/account_summary.json` doesn't exist, GET endpoint returns config defaults
- No breaking changes to existing code
- Persisted settings take priority when available
- Existing config values still work as fallback

##### Feature 3: P&L / Performance Section

**Backend:** `GET /account/performance`

**Response Model:**
```python
class AccountPerformanceResponse(BaseModel):
    equity: float | None = None              # Current account equity
    last_equity: float | None = None         # Previous day's closing equity
    cash: float | None = None                # Available cash
    buying_power: float | None = None        # Margin buying power
    day_pl: float | None = None              # Day P&L ($)
    day_pl_pct: float | None = None          # Day P&L (%)
    total_pl: float | None = None            # Total P&L ($ - unavailable currently)
    total_pl_pct: float | None = None        # Total P&L (% - unavailable currently)
    data_source: str = "unavailable"         # "paper", "live", or "unavailable"
    message: str | None = None               # Error message if unavailable
```

**Endpoint Behavior:**
1. Loads config to determine mode (paper or live)
2. Instantiates AlpacaBroker with appropriate credentials
3. Calls `broker.get_account()` to fetch account data
4. Calculates day P&L: `equity - last_equity`
5. Calculates day P&L %: `(day_pl / last_equity) * 100`
6. Returns performance metrics with `data_source` set to mode
7. **Graceful Fallback:** If broker unavailable or error:
   - Returns all metrics as `None`
   - Sets `data_source = "unavailable"`
   - Includes error message in `message` field
   - Returns HTTP 200 (not an error response)

**Data Sources:**
- **Paper Mode:** Fetches from Alpaca Paper Trading API using `alpaca_paper_key_id` and `alpaca_paper_secret_key`
- **Live Mode:** Fetches from Alpaca Live Trading API using `alpaca_live_key_id` and `alpaca_live_secret_key`
- **Unavailable:** Returns placeholder data if broker connection fails

**UI Components:**

1. **Performance Section** (new dashboard section)
   - Positioned between Account Summary and Universe Sectors
   - Grid layout: 4 cards (responsive, min 200px per card)

2. **Performance Cards:**
   - **Day P&L Card:**
     - Large value display ($ amount)
     - Percentage display below (green if positive, red if negative)
     - Color-coded: green text for gains, red for losses
   - **Equity Card:**
     - Current account equity ($)
   - **Cash Card:**
     - Available cash balance ($)
   - **Buying Power Card:**
     - Total margin buying power ($)

3. **Unavailable State:**
   - All values show "--" placeholder
   - Message displayed below cards: "Broker data unavailable: {error message}"
   - No error colors (neutral gray)

**JavaScript Functions:**
```javascript
async function loadPerformance() {
    try {
        const response = await fetch('/account/performance');
        const data = await response.json();

        if (data.data_source === 'unavailable') {
            // Show placeholders and message
            document.getElementById('day-pl').textContent = '--';
            document.getElementById('performance-message').textContent = data.message;
            document.getElementById('performance-message').style.display = 'block';
        } else {
            // Update with real data
            const dayPL = data.day_pl || 0;
            const dayPLPct = data.day_pl_pct || 0;
            document.getElementById('day-pl').textContent = '$' + dayPL.toFixed(2);

            const pctEl = document.getElementById('day-pl-pct');
            pctEl.textContent = (dayPLPct >= 0 ? '+' : '') + dayPLPct.toFixed(2) + '%';
            pctEl.className = 'performance-pct ' + (dayPLPct >= 0 ? 'positive' : 'negative');

            document.getElementById('equity').textContent = '$' + (data.equity || 0).toFixed(2);
            document.getElementById('cash').textContent = '$' + (data.cash || 0).toFixed(2);
            document.getElementById('buying-power').textContent = '$' + (data.buying_power || 0).toFixed(2);
        }
    } catch (error) {
        console.error('Error loading performance:', error);
    }
}
```

**Auto-Refresh:**
- Called by `loadDashboard()` every 30 seconds
- Provides near-real-time P&L updates
- No user interaction required

**Future Enhancements:**
- Total P&L tracking (requires storing initial equity)
- Historical equity curve chart
- Per-strategy P&L attribution
- Intraday high/low watermarks

##### Common Features (All Three Enhancements)

**Operator Gating:**
- All write operations require explicit user interaction
- Confirmation dialogs before staging changes:
  - Sector Editor: "Add N ticker(s) and Remove M ticker(s) for {sector}? Changes will be staged."
  - Account Summary: "Update account settings? This will affect risk limits."
- No automated changes without approval

**Audit Logging:**
- All changes emit ledger events with:
  - Event type (e.g., `manual_sector_tickers_staged`, `account_summary_updated`)
  - Actor: `"operator_ui"`
  - Old/new values where applicable
  - Timestamp (UTC)
- Full audit trail for compliance and debugging

**Error Handling:**
- Validation errors shown inline (red text)
- Network errors caught and displayed gracefully
- HTTP 400: Invalid input (user-fixable)
- HTTP 404: Resource not found
- HTTP 500: Server error (logged)
- HTTP 503: Service unavailable (registry/ledger not loaded)

**No LLM Keys Required:**
- All features work with config, registry, and broker only
- No dependency on OpenAI or Anthropic API keys
- Performance section gracefully handles broker unavailability

**Backwards Compatibility:**
- Account Summary: Falls back to config defaults if persisted file missing
- No breaking changes to existing workflows
- Existing proposal approve/reject flow unchanged
- Zero impact on trading loop or execution logic

**Testing:**
- 7 comprehensive unit tests added (`tests/test_ui_api_enhancements.py`)
- Mock broker for performance endpoint testing
- Mock UniverseRegistry for sector editor testing
- File I/O tests for account summary persistence
- All tests passing

### Usage Examples

#### Starting the Dashboard

```bash
# Terminal 1: Start trading bot with registry
python -m src.app.runner --mode paper --dry-run --loop

# Terminal 2: Start dashboard API (optional)
uvicorn src.ui_api.app:app --reload --port 8000

# Browser: Open dashboard
# http://localhost:8000
```

#### Programmatic API Usage

```bash
# Get all strategies
curl http://localhost:8000/strategies

# Disable a strategy
curl -X POST http://localhost:8000/strategies/Trend_MA20/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Update weight
curl -X POST http://localhost:8000/strategies/MeanRev_Z1.0/weight \
  -H "Content-Type: application/json" \
  -d '{"weight": 0.5}'

# Update parameters
curl -X POST http://localhost:8000/strategies/Trend_MA20/params \
  -H "Content-Type: application/json" \
  -d '{"params": {"sma_fast_period": 15, "sma_slow_period": 30}}'
```

#### Configuration Files

**Base Configuration** (`config/strategies.yaml`):
```yaml
strategies:
  - strategy_id: "Trend_MA20"
    name: "Trend Following (MA20)"
    description: "SMA crossover with 10/20 periods for trend following"
    enabled: true
    weight: 0.4
    params:
      sma_fast_period: 10
      sma_slow_period: 20
    risk_limits:
      max_position_size: 5000
      max_positions: 3
      max_daily_loss: 500

  - strategy_id: "MeanRev_Z1.0"
    name: "Mean Reversion (Z-Score 1.0)"
    description: "SMA crossover with 5/15 periods for mean reversion"
    enabled: true
    weight: 0.3
    params:
      sma_fast_period: 5
      sma_slow_period: 15
    risk_limits:
      max_position_size: 3000
      max_positions: 5
      max_daily_loss: 300

  - strategy_id: "Momentum_MACD"
    name: "Momentum (MACD-like)"
    description: "SMA crossover with 12/26 periods for momentum"
    enabled: false
    weight: 0.3
    params:
      sma_fast_period: 12
      sma_slow_period: 26
    risk_limits:
      max_position_size: 4000
      max_positions: 4
      max_daily_loss: 400

global:
  max_daily_loss: 1000
  max_total_positions: 10
  max_order_notional: 10000
  bar_timeframe: "1Min"
  market_open_hour: 9
  market_open_minute: 30
  market_close_hour: 16
  market_close_minute: 0
```

**Overrides File** (`out/strategies_overrides.json` - auto-generated):
```json
{
  "strategies": {
    "Trend_MA20": {
      "enabled": false,
      "weight": 0.3,
      "params": {
        "sma_fast_period": 10,
        "sma_slow_period": 20
      },
      "active_version": 2,
      "pending_version": null,
      "last_modified": "2024-01-15T10:30:00+00:00"
    }
  },
  "registry_version": 1,
  "last_saved": "2024-01-15T10:30:00+00:00"
}
```

### Safety Guarantees

1. **Next-Tick Activation:**
   - Changes never apply mid-loop
   - All changes activate at loop boundary
   - Deterministic activation timing
   - No race conditions

2. **Version Tracking:**
   - Every change increments version
   - `active_version` vs `pending_version` clearly separated
   - Audit trail of all configuration changes
   - Rollback possible by reverting overrides file

3. **Atomic Persistence:**
   - Write to temp file, then rename (atomic operation)
   - No partial writes
   - Crash-safe persistence

4. **Zero Execution Impact:**
   - Dashboard is optional (bot runs without it)
   - No changes to existing execution logic
   - No changes to risk controls
   - No changes to order placement logic
   - Only adds optional attribution fields

5. **Validation:**
   - Weight bounded to [0.0, 1.0]
   - Strategy ID must exist
   - Type validation via Pydantic
   - Graceful error handling

### Testing

**Test Coverage:** 395 tests passing
- 8 tests: Strategy registry (loading, merging, staging, activation, validation)
- 13 tests: Ledger system (append, read, rebuild, event types)
- 14 tests: FastAPI service (all endpoints, validation, error handling, dashboard)
- All existing tests pass (backward compatible)

**Test Files:**
- `tests/test_strategy_registry.py` - Registry functionality
- `tests/test_ledger.py` - Event logging and state reconstruction
- `tests/test_api.py` - API endpoints and dashboard
- `tests/test_main.py` - Updated for new CSV headers (strategy attribution)

**Test Strategy:**
- Unit tests with temporary config directories
- FastAPI TestClient for API tests
- Mocked fixtures for isolated testing
- No external dependencies (no real broker/ledger files)

### Dependencies

**Added Dependencies:**
```
fastapi>=0.104.0    # Web framework
uvicorn>=0.24.0     # ASGI server
httpx>=0.28.0       # TestClient support (dev only)
```

**No Breaking Changes:**
- All dependencies optional for dashboard
- Bot runs without FastAPI installed
- Graceful degradation if config files missing

### File Structure

```
ai-trader/
├── config/
│   └── strategies.yaml              # Base strategy configuration (version controlled)
├── out/
│   ├── strategies_overrides.json    # Runtime configuration overrides (auto-generated)
│   └── ledger/
│       └── YYYY-MM-DD.jsonl        # Daily event logs (auto-generated)
├── src/
│   ├── app/
│   │   ├── strategy_registry.py    # Configuration management
│   │   ├── ledger.py               # Event logging
│   │   ├── runner.py               # Loop integration (next-tick activation)
│   │   └── models.py               # Order attribution fields
│   └── ui_api/
│       ├── __init__.py
│       ├── app.py                  # FastAPI service
│       └── dashboard.html          # Web dashboard
└── tests/
    ├── test_strategy_registry.py   # Registry tests
    ├── test_ledger.py              # Ledger tests
    └── test_api.py                 # API tests
```

### Performance Considerations

1. **Registry Loading:**
   - Happens once at loop startup
   - YAML parsing is fast (<1ms for typical configs)
   - JSON override loading is fast (<1ms)

2. **Ledger Appends:**
   - Append-only writes (fast)
   - No locks or complex I/O
   - Daily rotation keeps files small

3. **API Latency:**
   - Registry reads are in-memory (microseconds)
   - Ledger reads scan file (milliseconds for typical daily activity)
   - Dashboard auto-refresh configurable (default 30s)

4. **Loop Impact:**
   - `check_and_activate_pending()` is O(N) where N = number of strategies (typically 3-5)
   - Runs once per loop tick (minimal overhead)
   - No blocking I/O in hot path

### Future Enhancements (Not Implemented)

Potential future additions (listed here for architectural consideration):

1. **Multi-Strategy Execution:**
   - Currently, strategies defined but not executed in parallel
   - Would require allocator integration
   - Would require per-strategy position tracking in risk manager

2. **Real-Time WebSocket Updates:**
   - Dashboard currently polls every 30s
   - WebSocket would enable push updates
   - Would require SSE or WebSocket endpoint

3. **Historical Performance Metrics:**
   - Ledger supports this via `rebuild_state()`
   - Would need UI components for charts/graphs
   - Could calculate Sharpe ratio, drawdown, etc. per strategy

4. **Strategy Parameter Optimization:**
   - Grid search or genetic algorithms
   - Would use ledger for historical evaluation
   - Would stage optimal parameters via existing API

5. **Multi-Account Support:**
   - Currently single Alpaca account
   - Would require account_id field throughout
   - Registry would need per-account strategies

### 8. Equity Curve Time Series

The **Equity Curve** feature provides automatic background capture of portfolio equity snapshots and displays them as a time series in the dashboard. This enables operators to track portfolio performance over time without requiring manual data export.

#### Purpose

- **Performance Monitoring:** Track equity changes throughout the trading day and across sessions
- **Visual Feedback:** See portfolio evolution in the dashboard with minimal latency
- **Historical Record:** Maintain bounded history of equity snapshots (up to 5000 points)
- **Audit Trail:** Complement ledger events with time-series account data

#### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Background Capture                         │
│                                                               │
│  ┌─────────────────┐           ┌─────────────────┐          │
│  │  Runner Loop    │           │  Dashboard UI   │          │
│  │  (non-dry-run)  │           │  Performance    │          │
│  │                 │           │  Endpoint       │          │
│  └────────┬────────┘           └────────┬────────┘          │
│           │                              │                   │
│           │ capture after success        │ capture on fetch  │
│           │                              │                   │
│           ▼                              ▼                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         src/app/equity_capture.py                     │  │
│  │  - capture_equity_snapshot()                          │  │
│  │  - load_equity_series()                               │  │
│  └───────────────────┬───────────────────────────────────┘  │
│                      │                                       │
│                      ▼                                       │
│           out/perf/equity.jsonl                              │
│           (atomic writes, rotation at 5000 points)           │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │  GET /account/performance/series     │
        │  Returns: {points, count, hours}     │
        └──────────────┬───────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │       Dashboard UI Table              │
        │  - Shows last 20 points               │
        │  - Reverse chronological              │
        │  - Time, Equity, Cash, Mode           │
        └───────────────────────────────────────┘
```

#### Core Module: `src/app/equity_capture.py`

##### `capture_equity_snapshot(equity, cash, mode, equity_file, max_points)`

Appends equity snapshot to time series file with automatic rotation.

**Parameters:**
- `equity` (float): Current portfolio equity
- `cash` (float): Current cash balance
- `mode` (str): Trading mode ("paper" or "live")
- `equity_file` (Path, optional): Output file path (default: `out/perf/equity.jsonl`)
- `max_points` (int, optional): Maximum points to retain (default: 5000)

**Behavior:**
1. Creates `out/perf/` directory if missing
2. Reads existing snapshots from file (if exists)
3. Appends new snapshot with UTC timestamp
4. Truncates to last `max_points` if exceeded
5. Writes back atomically (temp file + rename)
6. Gracefully handles corrupted data (discards invalid lines)

**Snapshot Format:**
```json
{
  "timestamp": "2026-01-06T10:30:00.123456+00:00",
  "equity": 102500.50,
  "cash": 48750.25,
  "mode": "paper"
}
```

**Atomic Write Pattern:**
```python
with NamedTemporaryFile(mode="w", dir=equity_file.parent, delete=False) as tmp:
    for point in existing_points:
        tmp.write(json.dumps(point) + "\n")
    tmp_path = Path(tmp.name)

tmp_path.replace(equity_file)  # Atomic on POSIX, near-atomic on Windows
```

##### `load_equity_series(equity_file, hours)`

Loads and filters equity snapshots by time window.

**Parameters:**
- `equity_file` (Path, optional): Input file path (default: `out/perf/equity.jsonl`)
- `hours` (int, optional): Time window in hours (default: 24)

**Returns:**
- `list[dict]`: Snapshots within time window (sorted chronologically)

**Behavior:**
1. Returns empty list if file doesn't exist
2. Calculates cutoff time (`now - timedelta(hours)`)
3. Reads JSONL file line-by-line
4. Filters snapshots by timestamp
5. Skips corrupted lines or invalid timestamps
6. Returns filtered list (oldest to newest)

**Error Handling:**
- Missing file → empty list
- Corrupted JSON lines → skipped (logged as warning)
- Invalid timestamp format → skipped
- File read errors → empty list (logged as warning)

#### Background Capture Integration

##### Runner Loop (`src/app/runner.py`)

Captures equity after each successful loop iteration (non-dry-run only).

**Location:** Line 1019-1050 (after status log write)

**Code:**
```python
# Capture equity snapshot (best-effort)
if not dry_run:
    try:
        from src.app.equity_capture import capture_equity_snapshot
        from src.broker.base import AlpacaBroker

        # Get current equity from broker
        if config.mode == "paper":
            broker = AlpacaBroker(
                key_id=config.alpaca_paper_key_id or "",
                secret_key=config.alpaca_paper_secret_key or "",
                is_paper=True,
            )
        else:
            broker = AlpacaBroker(
                key_id=config.alpaca_live_key_id or "",
                secret_key=config.alpaca_live_secret_key or "",
                is_paper=False,
            )

        account = broker.get_account()
        equity = float(account.equity)
        cash = float(account.cash)

        capture_equity_snapshot(equity=equity, cash=cash, mode=config.mode)

    except Exception as e:
        print(f"WARNING: Failed to capture equity snapshot: {e}")
```

**Behavior:**
- Runs only when `dry_run=False` (actual trading mode)
- Creates broker client to fetch current account state
- Calls `capture_equity_snapshot()` with equity/cash
- **Best-effort:** Catches exceptions, logs warnings, never blocks trading
- **Timing:** Captures after orders are placed and status logged

##### Dashboard Performance Endpoint (`src/ui_api/app.py`)

Captures equity when dashboard fetches performance data.

**Location:** Line 1562-1572 (inside `GET /account/performance`)

**Code:**
```python
# Capture equity snapshot (best-effort)
try:
    from src.app.equity_capture import capture_equity_snapshot

    capture_equity_snapshot(equity=equity, cash=cash, mode=config.mode)
except Exception as e:
    print(f"WARNING: Failed to capture equity snapshot: {e}")
```

**Behavior:**
- Runs when dashboard polls performance endpoint (every 30 seconds)
- Captures equity alongside fetching account performance
- **Best-effort:** Never fails the API request
- **Timing:** Captures after successful broker API call

#### API Endpoint

##### `GET /account/performance/series`

Returns equity time series filtered by time window.

**Query Parameters:**
- `hours` (int, optional): Time window in hours (default: 24, max: 720)

**Response:**
```json
{
  "points": [
    {
      "timestamp": "2026-01-06T09:30:00.123456+00:00",
      "equity": 100000.00,
      "cash": 50000.00,
      "mode": "paper"
    },
    {
      "timestamp": "2026-01-06T10:30:00.234567+00:00",
      "equity": 100500.50,
      "cash": 49500.25,
      "mode": "paper"
    }
  ],
  "count": 2,
  "hours": 24
}
```

**Behavior:**
1. Caps `hours` at 720 (30 days)
2. Calls `load_equity_series(hours=hours)`
3. Returns empty `points` list if no data
4. Returns all points within time window (no limit)

**Status Codes:**
- `200 OK`: Always (even if no data)

**Implementation:**
```python
@app.get("/account/performance/series")
async def get_equity_series(hours: int = 24):
    """Get equity time series for the last N hours."""
    from pathlib import Path
    from src.app.equity_capture import load_equity_series

    # Cap hours at 30 days
    hours = min(hours, 720)

    equity_file = Path("out/perf/equity.jsonl")
    points = load_equity_series(equity_file, hours=hours)

    return {
        "points": points,
        "count": len(points),
        "hours": hours,
    }
```

#### Dashboard UI Components

##### Equity Curve Section

**Location:** `src/ui_api/dashboard.html` (inside Performance section, after performance cards)

**HTML Structure:**
```html
<div class="equity-curve-section">
    <div class="section-header">
        <h3>Equity Curve (Last 24 Hours)</h3>
        <button class="btn-secondary" onclick="loadEquitySeries()">
            Refresh
        </button>
    </div>
    <div class="equity-table-container">
        <table class="equity-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Equity</th>
                    <th>Cash</th>
                    <th>Mode</th>
                </tr>
            </thead>
            <tbody id="equity-table-body">
                <!-- Dynamically populated -->
            </tbody>
        </table>
    </div>
</div>
```

**CSS Styling:**
- `.equity-table-container`: Scrollable container (max-height: 400px)
- `.equity-table thead`: Sticky header (always visible when scrolling)
- `.equity-table tbody tr:hover`: Hover highlight for rows
- Consistent with dashboard theme (dark background, blue accents)

##### JavaScript Functions

**`loadEquitySeries(hours = 24)`**

Fetches equity series from API and renders table.

**Behavior:**
1. Fetches `GET /account/performance/series?hours=${hours}`
2. Handles empty data gracefully (shows "No equity data available")
3. Takes last 20 points, reverses order (most recent first)
4. Formats timestamps as `"Jan 6, 10:30 AM"`
5. Renders table rows with equity, cash, mode badge
6. Handles errors (shows "Failed to load equity data")

**Implementation:**
```javascript
async function loadEquitySeries(hours = 24) {
    try {
        const response = await fetch(`/account/performance/series?hours=${hours}`);
        const data = await response.json();

        const tbody = document.getElementById('equity-table-body');

        if (!data.points || data.points.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted">No equity data available</td></tr>';
            return;
        }

        // Show last 20 points, most recent first
        const points = data.points.slice(-20).reverse();

        tbody.innerHTML = points.map(point => {
            const timestamp = new Date(point.timestamp);
            const timeStr = timestamp.toLocaleString('en-US', {
                month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });

            return `
                <tr>
                    <td>${timeStr}</td>
                    <td>$${(point.equity || 0).toFixed(2)}</td>
                    <td>$${(point.cash || 0).toFixed(2)}</td>
                    <td><span class="badge">${point.mode}</span></td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading equity series:', error);
        tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Failed to load equity data</td></tr>';
    }
}
```

**Auto-Refresh:**

Called automatically on dashboard load:
```javascript
async function loadDashboard() {
    // ... other loads ...
    await loadPerformance();
    await loadEquitySeries();  // Added
    // ...
}
```

#### Storage Format

##### File: `out/perf/equity.jsonl`

**Format:** JSON Lines (one JSON object per line)

**Example:**
```jsonl
{"timestamp":"2026-01-06T09:30:00.123456+00:00","equity":100000.0,"cash":50000.0,"mode":"paper"}
{"timestamp":"2026-01-06T10:30:00.234567+00:00","equity":100500.5,"cash":49500.25,"mode":"paper"}
{"timestamp":"2026-01-06T11:30:00.345678+00:00","equity":101000.75,"cash":49000.0,"mode":"paper"}
```

**Fields:**
- `timestamp` (str): ISO 8601 UTC timestamp with microsecond precision
- `equity` (float): Total portfolio equity (positions + cash)
- `cash` (float): Available cash balance
- `mode` (str): Trading mode ("paper" or "live")

**File Size Bounds:**
- **Max Points:** 5000 (configurable via `max_points` parameter)
- **Estimated Size:** ~300 bytes per line → 5000 lines ≈ 1.5 MB
- **Rotation:** Automatic (keeps last 5000 points, discards oldest)

**Directory Structure:**
```
out/
├── perf/
│   └── equity.jsonl        # Time series snapshots
├── strategies_overrides.json
└── universe_proposals.json
```

#### Safety Features

1. **Atomic Writes:**
   - Uses temp file + rename pattern
   - Prevents corruption on crash or interruption
   - Windows: Near-atomic (replace operation)
   - POSIX: Guaranteed atomic

2. **Bounded Growth:**
   - Hard cap at 5000 points (default)
   - Prevents unbounded disk usage
   - 5000 snapshots ≈ 69 days at 1 snapshot/20 minutes

3. **Best-Effort Capture:**
   - Never blocks trading operations
   - Exceptions caught and logged as warnings
   - Missing broker data → skip capture (no crash)
   - File I/O errors → skip capture (no crash)

4. **Corruption Handling:**
   - Invalid JSON lines → skipped during read
   - Missing timestamp → line skipped
   - Invalid timestamp format → line skipped
   - Entire file corrupted → discarded, new file started

5. **No LLM Keys Required:**
   - Pure data capture and retrieval
   - No external API dependencies (besides Alpaca)
   - Works in all trading modes

#### Testing

##### Unit Tests: `tests/test_equity_capture.py` (10 tests)

**Capture Function Tests:**
1. `test_capture_equity_snapshot_creates_file` - File creation
2. `test_capture_equity_snapshot_appends_to_existing` - Append behavior
3. `test_capture_equity_snapshot_caps_at_max_points` - Rotation (5 points max)
4. `test_capture_equity_snapshot_handles_missing_directory` - Auto-create dirs
5. `test_capture_equity_snapshot_handles_corrupted_file` - Recovery from corruption
6. `test_capture_with_different_modes` - Paper/live mode tracking

**Load Function Tests:**
7. `test_load_equity_series_returns_empty_if_no_file` - Missing file handling
8. `test_load_equity_series_filters_by_time_window` - Time-based filtering (24h)
9. `test_load_equity_series_handles_corrupted_lines` - Skips invalid JSON
10. `test_load_equity_series_handles_missing_timestamp` - Skips entries without timestamp

##### API Tests: `tests/test_equity_api.py` (5 tests)

**Endpoint Tests:**
1. `test_get_equity_series_empty` - Empty data response
2. `test_get_equity_series_with_data` - Data retrieval (3 points)
3. `test_get_equity_series_with_custom_hours` - Time window filtering (48h → 24h)
4. `test_get_equity_series_caps_max_hours` - Hours capped at 720
5. `test_get_equity_series_filters_old_data` - Old data excluded (100h → 24h)

**Test Coverage:**
- File I/O operations (create, append, rotate)
- Atomic write behavior
- Time window filtering
- Corruption recovery
- API endpoint contract
- Query parameter validation

**Running Tests:**
```bash
pytest tests/test_equity_capture.py tests/test_equity_api.py -v
# All 15 tests pass
```

#### Usage Examples

##### Viewing Equity Curve in Dashboard

1. Start trading bot (paper mode with loop):
   ```bash
   python -m src.app.runner --mode paper --loop
   ```

2. Open dashboard:
   ```
   http://localhost:8000
   ```

3. Navigate to Performance section → Equity Curve table
   - Shows last 20 snapshots
   - Click "Refresh" to reload

##### API Usage (Programmatic)

**Get last 24 hours:**
```bash
curl http://localhost:8000/account/performance/series
```

**Get last 7 days:**
```bash
curl http://localhost:8000/account/performance/series?hours=168
```

**Response Example:**
```json
{
  "points": [
    {
      "timestamp": "2026-01-06T09:30:00.123456+00:00",
      "equity": 100000.0,
      "cash": 50000.0,
      "mode": "paper"
    }
  ],
  "count": 1,
  "hours": 24
}
```

##### Manual Snapshot (CLI)

```python
from pathlib import Path
from src.app.equity_capture import capture_equity_snapshot

# Capture a snapshot manually
capture_equity_snapshot(
    equity=100000.0,
    cash=50000.0,
    mode="paper",
    equity_file=Path("out/perf/equity.jsonl"),
    max_points=5000,
)
```

#### Performance Considerations

1. **Capture Overhead:**
   - File I/O: ~1-2ms per capture (atomic write)
   - Broker API call: Already happening (no extra latency)
   - Negligible impact on loop timing (best-effort)

2. **API Latency:**
   - File read: ~10-20ms for 5000 points
   - Time filtering: O(N) scan, fast for small files
   - Network transfer: ~1KB per 20 points (minimal)

3. **Disk Usage:**
   - 5000 points ≈ 1.5 MB (bounded)
   - Single file (no log rotation needed)
   - JSONL format (human-readable, easy to debug)

4. **Dashboard Impact:**
   - Auto-loads on page load (1 request)
   - Manual refresh available (button)
   - No WebSocket/polling overhead

#### Limitations

1. **No Historical Backfill:**
   - Snapshots start when feature is deployed
   - No automatic backfill from ledger or broker history
   - Manual backfill possible via CLI script

2. **No Chart Visualization:**
   - Currently displays as table (last 20 points)
   - Future: Add line chart with chart library
   - Table is simpler and doesn't require external dependencies

3. **Single File Storage:**
   - No per-day rotation (unlike logs)
   - Entire history in one file (bounded at 5000 points)
   - Sufficient for short-term monitoring (weeks to months)

4. **No Persistence Across Modes:**
   - Paper and live mode use same file
   - Mode is tracked per snapshot but not filtered
   - Mixed mode data if switching between paper/live

#### Future Enhancements (Not Implemented)

1. **Line Chart Visualization:**
   - Add chart library (e.g., Chart.js)
   - Render equity over time as line graph
   - Hover tooltips for exact values

2. **Per-Day Files:**
   - Split into daily files (`equity_20260106.jsonl`)
   - Easier to manage long histories
   - Automatic cleanup of old files

3. **Drawdown Calculation:**
   - Calculate max drawdown from equity series
   - Display in dashboard (e.g., "Max DD: -2.5%")
   - Alert on excessive drawdown

4. **Export to CSV:**
   - Download equity series as CSV
   - For external analysis (Excel, Python, etc.)

5. **Intraday Statistics:**
   - High/low equity for current day
   - Intraday volatility (std-dev of returns)
   - Display in Performance section

---

## Universe Advisor: LLM-Powered Sector Recommendations

### Overview

The **Universe Advisor** is an LLM-powered decision-support system that analyzes market regime and recent news to generate sector enable/disable recommendations. It operates as a **gated system** - all proposals require explicit operator approval before affecting trading.

**Key Architecture Principle:** The advisor is **advisory only**. It produces proposals that are reviewed and approved by the operator via the dashboard UI. Approved proposals stage changes in the UniverseRegistry which activate on the next loop tick.

```
┌─────────────────┐
│  Dashboard UI   │ ← Operator approves/rejects proposals
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   API Server    │ POST /universe/proposals/generate
│                 │ POST /universe/proposals/{id}/approve
│                 │ POST /universe/proposals/{id}/reject
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              Universe Advisor                        │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │   Market   │  │    RSS     │  │    LLM     │   │
│  │   Regime   │  │  Events    │  │  Provider  │   │
│  │  Detector  │  │  Loader    │  │  (OpenAI/  │   │
│  │            │  │            │  │  Anthropic)│   │
│  └────────────┘  └────────────┘  └────────────┘   │
│         │                │               │          │
│         └────────────────┴───────────────┘          │
│                          │                          │
│                   ┌──────▼──────┐                   │
│                   │  Guardrails  │                   │
│                   └──────┬──────┘                   │
│                          │                          │
│                   ┌──────▼──────┐                   │
│                   │  Proposals  │                   │
│                   │   Storage   │                   │
│                   └─────────────┘                   │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ UniverseRegistry│ ← Stage changes (pending)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Runner Loop    │ ← Activate at loop start
└─────────────────┘
```

### LLM Provider Abstraction

**Module:** `src/app/llm/providers/`

The advisor supports multiple LLM providers through an abstract base class:

**Provider Interface** (`src/app/llm/providers/base.py`):
```python
class LLMProvider(ABC):
    @abstractmethod
    def generate_structured_json(
        self, prompt: str, schema: dict, temperature: float, max_tokens: int
    ) -> dict:
        """Generate structured JSON response from LLM."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name (e.g., 'openai', 'anthropic')."""
        pass
```

**Implementations:**
- `OpenAIProvider` (`openai_provider.py`) - Uses OpenAI JSON mode
- `AnthropicProvider` (`anthropic_provider.py`) - Uses Claude with prompt engineering for JSON extraction

**Provider Modes** (configured in `config.yaml`):

1. **`openai_only`** - Single OpenAI call
2. **`anthropic_only`** - Single Anthropic call
3. **`primary_fallback`** - Try primary provider, fallback to secondary on error
4. **`ensemble`** - Call both providers, apply consensus rules:
   - **Agreement**: Both recommend same direction (enable/disable) → create ensemble proposal with averaged confidence
   - **Contradiction**: Providers disagree on direction → drop proposal, record as disagreement (read-only display)
   - **Single provider**: Only one mentions a sector → use that recommendation

**Factory Pattern** (`src/app/llm/factory.py`):
```python
def get_providers_for_mode(
    mode: ProviderMode,
    primary: ProviderType = "openai",
    openai_model: str | None = None,
    anthropic_model: str | None = None,
    timeout: int = 30,
) -> tuple[LLMProvider, ...]:
    """Get provider instances for a given mode."""
```

**Lazy Loading:** Providers use `__getattr__` in `__init__.py` to avoid requiring `openai` or `anthropic` packages when not used.

### Market Regime Detection

**Module:** `src/app/universe_advisor/regime.py`

Market regime is determined by two factors:
1. **Trend**: SPY price vs 50-day moving average (bull if SPY ≥ MA50, bear otherwise)
2. **Volatility**: 20-day rolling standard deviation of returns (annualized)

**Volatility Buckets:**
- Low: < 15% annualized
- Medium: 15-25% annualized
- High: > 25% annualized

**Regime Classification:**
```python
class MarketRegime(str, Enum):
    BULL_LOW_VOL = "bull_low_vol"      # SPY ≥ MA50, vol < 25%
    BULL_HIGH_VOL = "bull_high_vol"    # SPY ≥ MA50, vol ≥ 25%
    BEAR_LOW_VOL = "bear_low_vol"      # SPY < MA50, vol < 25%
    BEAR_HIGH_VOL = "bear_high_vol"    # SPY < MA50, vol ≥ 25%
    UNKNOWN = "unknown"                 # Insufficient data
```

**Algorithm:**
1. Fetch SPY data from market data provider
2. Calculate 20-day returns: `[(close[i] - close[i-1]) / close[i-1]]`
3. Compute standard deviation and annualize: `std_dev * sqrt(252)`
4. Compare SPY price to MA50 for trend
5. Classify into regime bucket
6. Calculate confidence based on data quality (0.0-1.0)

### RSS Integration

**Module:** `src/app/universe_advisor/generate.py` (function: `load_recent_rss_events`)

**RSS Event Loading:**
- Reads from `out/selector/events.jsonl` (generated by RSS selector)
- Filters by recency: default 24-hour lookback window
- Hard cap: 100 headlines maximum
- Deduplicates by headline text
- Prioritizes: `candidate_created` > `headline_processed`, then by confidence, then by recency

**Event Types Used:**
- `candidate_created` - High-confidence trading candidates
- `headline_processed` - General news headlines

**LLM Prompt Construction:**
The prompt includes:
1. Current market regime (regime type, SPY price/MA50, trend, volatility)
2. Recent headlines (up to 50 shown in prompt, numbered 1-N)
3. Available sectors (description + first 5 symbols)
4. Task instructions and JSON schema

### Proposal Generation

**Module:** `src/app/universe_advisor/generate.py` (function: `generate_proposals`)

**Generation Flow:**
1. Detect market regime via `detect_market_regime()`
2. Load recent RSS events via `load_recent_rss_events()`
3. Build prompt with regime + events + sectors
4. Call LLM provider(s) based on mode
5. Parse LLM responses into Proposal objects
6. Apply consensus logic (if ensemble mode)
7. Return ProposalSet

**Proposal Model:**
```python
@dataclass
class Proposal:
    proposal_id: str                      # UUID
    sector_name: str                      # Sector identifier
    confidence: float                     # 0.0-1.0
    rationale: str                        # LLM explanation
    supporting_headlines: list[str]       # Top 3-5 headlines
    provider: str                         # "openai", "anthropic", "ensemble"
    created_at: str                       # ISO timestamp
    expires_at: str                       # ISO timestamp (TTL)
    status: ProposalStatus                # "NEW", "APPROVED", "REJECTED", "APPLIED", "EXPIRED"
    proposal_type: ProposalType           # "sector_toggle" or "constituent_change"
    recommended_enabled: bool | None      # Enable/disable (sector_toggle only)
    constituent_change: ConstituentChange | None  # Ticker changes (constituent_change only)
```

**Proposal Types:**

The system supports two types of proposals:

1. **SECTOR_TOGGLE** - Enable or disable an entire sector
   - Uses `recommended_enabled` field (True/False)
   - Affects all tickers in the sector
   - Example: "Disable mega_cap_tech sector due to market volatility"

2. **CONSTITUENT_CHANGE** - Add or remove specific tickers from a sector
   - Uses `constituent_change` field (ConstituentChange object)
   - Allows fine-grained portfolio adjustments
   - Example: "Add ROK to mega_cap_tech based on strong earnings"

**ConstituentChange Model:**
```python
@dataclass
class ConstituentChange:
    action: ConstituentChangeAction       # "add" or "remove"
    tickers: list[str]                    # List of ticker symbols
    reason: str                           # Explanation for the change
    constraints_checked: dict[str, bool]  # Validation results
```

**ConstituentChangeAction Enum:**
```python
class ConstituentChangeAction(str, Enum):
    ADD = "add"       # Add tickers to sector
    REMOVE = "remove" # Remove tickers from sector
```

**Constraints Checked:**

When generating CONSTITUENT_CHANGE proposals, the system validates:
- `not_blacklisted`: Ticker is not on the blacklist
- `not_in_sector`: Ticker is not already in the sector (for ADD)
- `cooldown_ok`: Ticker respects cooldown period
- `tradable`: Ticker is tradable on the broker

**ProposalSet Model:**
```python
@dataclass
class ProposalSet:
    generation_id: str                    # UUID for this generation run
    proposals: list[Proposal]             # Actionable proposals
    disagreements: list[Disagreement]     # Provider contradictions (read-only)
    regime: RegimeData                    # Market regime snapshot
    headline_count: int                   # Number of headlines analyzed
    generated_at: str                     # ISO timestamp
```

**Ensemble Merge Rules:**
- **Agreement**: `openai.recommended_enabled == anthropic.recommended_enabled` → Averaged confidence, combined rationale, "ensemble" provider
- **Contradiction**: `openai.recommended_enabled != anthropic.recommended_enabled` → Drop proposal, record Disagreement
- **Single provider**: Only one mentions sector → Use that recommendation with original provider name

### Constituent Proposal Generation

**Module:** `src/app/universe_advisor/generate_constituents.py`

The system can generate CONSTITUENT_CHANGE proposals for fine-grained ticker-level adjustments within sectors.

**Generation Flow:**
1. Load recent RSS events with sector/ticker context
2. Analyze market regime for sector compatibility
3. Extract ticker-level signals (earnings, product launches, etc.)
4. Generate ADD/REMOVE proposals for specific tickers
5. Validate constraints (blacklist, duplicates, cooldown, tradability)
6. Create proposals with supporting evidence

**Example Constituent Proposal:**
```json
{
  "proposal_id": "uuid-123",
  "sector_name": "mega_cap_tech",
  "proposal_type": "constituent_change",
  "confidence": 0.88,
  "rationale": "Rockwell Automation shows strong earnings momentum...",
  "supporting_headlines": [
    "Rockwell Automation (ROK) beats Q3 earnings with record revenue",
    "Industrial automation demand surges amid AI infrastructure buildout"
  ],
  "constituent_change": {
    "action": "add",
    "tickers": ["ROK"],
    "reason": "Strong earnings, high confidence automation play",
    "constraints_checked": {
      "not_blacklisted": true,
      "not_in_sector": true,
      "cooldown_ok": true,
      "tradable": true
    }
  },
  "provider": "openai",
  "status": "NEW"
}
```

**Constraint Validation:**

Before creating a proposal, the system checks:
- **not_blacklisted**: Ticker not on `universe_config.blacklist`
- **not_in_sector**: For ADD, ticker not already in sector's ticker list
- **cooldown_ok**: Ticker hasn't been added/removed recently
- **tradable**: Ticker is tradable on the broker (via `get_tradable_assets()`)

If any constraint fails, the proposal is filtered out during generation.

**Generation Trigger:**

Constituent proposals can be generated:
- **Manually**: Via dashboard "Generate" button or API call
- **Automatically**: Not currently implemented (safety consideration)
- **On-demand**: Via test/development scripts

### Safety Guardrails

**Module:** `src/app/universe_advisor/guardrails.py`

Guardrails filter proposals to prevent excessive or risky changes:

**Guardrail Rules:**
1. **`min_confidence`** (default: 0.70) - Drops proposals below confidence threshold
2. **`proposal_ttl_minutes`** (default: 120) - Proposals expire after TTL, status becomes "EXPIRED"
3. **`max_sector_toggles_per_day`** (default: 1) - Limits toggles per sector within 24-hour window
4. **`cooldown_days`** (default: 3) - Enforces cooldown period after last approved toggle for a sector

**History Tracking:**
- Append-only file: `out/universe_proposals_history.jsonl`
- Records APPROVED and REJECTED proposals
- Used by guardrails to enforce daily limits and cooldown

**Guardrails Application:**
```python
def apply_guardrails(
    proposal_set: ProposalSet,
    config: dict,
    history_file: Path,
) -> ProposalSet:
    """Filter proposals based on safety rules."""
```

**Example Filtering:**
- Proposal with confidence 0.65 and min_confidence=0.70 → Filtered
- Sector toggled 1 hour ago and max_toggles_per_day=1 → Filtered
- Sector last approved 2 days ago and cooldown_days=3 → Filtered
- Proposal created 3 hours ago with TTL=120 minutes → Status changed to EXPIRED

### Auto-Generation

**Module:** `src/app/runner.py` (integration point)

**Auto-Generation Timing:**
- Triggered at **start of each loop iteration** (before market data fetch)
- Runs only if `config.llm_auto_generate_enabled == True`
- Checks if `llm_auto_generate_interval_hours` has elapsed since last generation
- Default interval: 4 hours

**Best-Effort Execution:**
- All exceptions caught and logged as warnings
- **Never blocks trading** - if generation fails, loop continues normally
- Logs success/failure but doesn't halt execution

**Generation Steps:**
1. Check if `out/universe_proposals.json` exists
2. If exists, parse `generated_at` timestamp
3. Calculate elapsed hours since last generation
4. If elapsed ≥ interval, trigger generation:
   - Detect market regime
   - Load RSS events
   - Generate proposals via LLM
   - Apply guardrails
   - Save to `out/universe_proposals.json` (atomic write)
   - Log to ledger with event type `universe_proposals_generated`
5. If generation fails, log warning and continue

**Code Location:** `src/app/runner.py`, lines 836-937

### Storage

**Module:** `src/app/universe_advisor/storage.py`

**Proposals File** (`out/universe_proposals.json`):
- **Purpose:** Current proposals awaiting review
- **Format:** JSON with atomic write (temp file + rename)
- **Contents:**
  - `generation_id` - UUID for this generation
  - `generated_at` - ISO timestamp
  - `regime` - Market regime snapshot
  - `proposals` - List of proposal objects
  - `disagreements` - List of provider contradictions
  - `headline_count` - Number of headlines analyzed

**History File** (`out/universe_proposals_history.jsonl`):
- **Purpose:** Append-only audit trail
- **Format:** JSONL (one JSON object per line)
- **Events Recorded:**
  - Proposals approved (status: "APPROVED")
  - Proposals rejected (status: "REJECTED")
  - Proposals applied (status: "APPLIED")
- **Common Fields:** `timestamp`, `action`, `proposal_id`, `sector_name`, `confidence`, `provider`, `status`, `proposal_type`
- **Type-Specific Fields:**
  - **SECTOR_TOGGLE**: `recommended_enabled` (bool)
  - **CONSTITUENT_CHANGE**: `constituent_change` (object with `action`, `tickers`)

**Example History Entries:**

Sector toggle:
```json
{
  "timestamp": "2026-01-06T22:00:00.000000+00:00",
  "action": "APPROVED",
  "proposal_id": "uuid-456",
  "sector_name": "core_index",
  "proposal_type": "sector_toggle",
  "recommended_enabled": true,
  "confidence": 0.75,
  "provider": "openai",
  "status": "APPROVED"
}
```

Constituent change:
```json
{
  "timestamp": "2026-01-06T22:15:00.000000+00:00",
  "action": "APPROVED",
  "proposal_id": "uuid-789",
  "sector_name": "mega_cap_tech",
  "proposal_type": "constituent_change",
  "constituent_change": {
    "action": "add",
    "tickers": ["ROK", "ABB"]
  },
  "confidence": 0.88,
  "provider": "openai",
  "status": "APPROVED"
}
```

**Atomic Write Pattern:**
```python
with NamedTemporaryFile(mode="w", dir=file_path.parent, delete=False) as tmp:
    json.dump(data, tmp, indent=2)
    tmp_path = Path(tmp.name)
tmp_path.replace(file_path)  # Atomic on POSIX and Windows
```

### API Endpoints

**Module:** `src/ui_api/app.py`

**GET Endpoints:**

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `GET /universe/proposals` | Get current proposals and disagreements | `ProposalsListResponse` with proposals, disagreements, regime, headline count |

**POST Endpoints:**

| Endpoint | Purpose | Request Body | Returns |
|----------|---------|--------------|---------|
| `POST /universe/proposals/generate` | Generate new proposals manually | `{force: bool}` | `ChangeResponse` with success, message, proposal/disagreement count |
| `POST /universe/proposals/{id}/approve` | Approve proposal and stage UniverseRegistry change | None | `ChangeResponse` with success, message, pending_version |
| `POST /universe/proposals/{id}/reject` | Reject proposal | None | `ChangeResponse` with success, message |

**Approval Flow:**
1. Operator clicks "Approve" on proposal in dashboard
2. API endpoint validates proposal exists and status is "NEW"
3. Calls `apply_proposal()` which:
   - **For SECTOR_TOGGLE**: Stages enable/disable in UniverseRegistry via `stage_change()`
   - **For CONSTITUENT_CHANGE**: Stages ticker add/remove via `stage_constituent_change()`
   - Both operations set a new pending_version for the sector
   - Updates proposal status to "APPROVED"
   - Saves updated proposals file (atomic write)
   - Appends to history file
   - Logs to ledger with event type `universe_proposal_approved`
4. Returns `pending_version` to UI
5. Dashboard refreshes to show pending indicator

**Constituent Change Staging:**

When a CONSTITUENT_CHANGE proposal is approved:
```python
new_version = universe_registry.stage_constituent_change(
    sector_name="mega_cap_tech",
    action="add",  # or "remove"
    tickers=["ROK", "ABB"],
)
```

This:
- Loads current sector tickers
- Applies the add/remove operation
- Creates new pending version with updated ticker list
- Preserves enabled status
- Waits for activation on next loop tick

**Rejection Flow:**
1. Operator clicks "Reject" on proposal
2. API endpoint updates status to "REJECTED"
3. Reconstructs Proposal object with proper enum conversions:
   - Converts `proposal_type` string to ProposalType enum
   - Converts `constituent_change.action` string to ConstituentChangeAction enum
   - Ensures proper serialization for history file
4. Saves updated proposals file (atomic write)
5. Appends to history file with serialized enums
6. Logs to ledger with event type `universe_proposal_rejected`

**Important**: Both approve and reject endpoints properly handle enum serialization when persisting to history file, preventing `'str' object has no attribute 'value'` errors.

**Force Generation:**
- If `force=false`, checks if generation interval has elapsed
- If `force=true`, skips interval check and always generates

### Dashboard UI

**Module:** `src/ui_api/dashboard.html`

**Advisor Suggestions Section:**
- **Header:** Displays proposal count and disagreement count
- **Generate Button:** Triggers manual generation via POST endpoint
- **Regime Display:** Shows current market regime (regime type, SPY price/MA50, volatility)
- **Proposals List:** Grid of proposal cards, each showing:
  - Sector name
  - **Badge (Proposal Type)**:
    - **SECTOR_TOGGLE**: ENABLE (green) or DISABLE (red)
    - **CONSTITUENT_CHANGE**: ADD (green) or REMOVE (red) with ticker symbols
  - Confidence score (0.00-1.00)
  - Provider badge (openai, anthropic, ensemble)
  - Status badge (NEW, APPROVED, REJECTED, APPLIED, EXPIRED)
  - Rationale (LLM explanation)
  - **For CONSTITUENT_CHANGE**: Displays action, ticker list, and reason
  - Collapsible supporting headlines
  - Expiration timestamp
  - Action buttons: "Approve" and "Reject" (only for NEW status)
- **Disagreements Section:** Collapsible details list showing:
  - Sector name
  - Provider A recommendation + confidence
  - Provider B recommendation + confidence
  - Highlighted to show contradiction

**JavaScript Functions:**
- `loadProposals()` - Fetches current proposals from GET endpoint
- `renderProposals(data)` - Updates DOM with proposals and disagreements
- `generateProposals()` - Calls POST generate endpoint
- `approveProposal(proposalId)` - Calls POST approve endpoint with confirmation
- `rejectProposal(proposalId)` - Calls POST reject endpoint

**User Feedback:**
- Success messages (green) for approvals/rejections
- Pending version shown on approved proposals
- Expired proposals grayed out with opacity
- Auto-refresh every 30 seconds includes proposals

**Code Location:** `src/ui_api/dashboard.html`, lines vary (embedded in HTML file)

### Runner Integration

**Module:** `src/app/runner.py`

**Integration Point 1: Auto-Generation** (lines 836-937)
- Location: After UniverseRegistry initialization, before main loop
- Checks if auto-generation is enabled
- Checks if interval has elapsed
- Generates proposals if conditions met
- All exceptions caught (best-effort)

**Integration Point 2: Mark Applied** (lines 956-974)
- Location: After `universe_registry.check_and_activate_pending()`
- When UniverseRegistry activates a pending change
- Finds APPROVED proposals for that sector
- Updates status to "APPLIED"
- Appends to history file
- Logs to ledger with event type `universe_proposal_applied`

**Activation Flow:**
1. Operator approves proposal → status becomes "APPROVED", UniverseRegistry has pending_version
2. Loop iteration starts
3. `universe_registry.check_and_activate_pending()` promotes pending to active
4. Returns list of activated changes: `[(sector_name, old_version, new_version)]`
5. For each activated change:
   - Print log: "sector_name: vX → vY"
   - Call `mark_applied(sector_name, proposals_file, history_file)`
   - Updates APPROVED proposals to APPLIED
   - Logs to ledger
6. Trading proceeds with new universe configuration

### Ledger Events

**Event Types Added:**

1. **`universe_proposals_generated`**
   - Emitted when proposals are generated (auto or manual)
   - Fields: `generation_id`, `proposal_count`, `disagreement_count`, `regime`, `headline_count`

2. **`universe_proposal_approved`**
   - Emitted when operator approves a proposal
   - Fields: `proposal_id`, `sector_name`, `recommended_enabled`, `pending_version`

3. **`universe_proposal_rejected`**
   - Emitted when operator rejects a proposal
   - Fields: `proposal_id`, `sector_name`

4. **`universe_proposal_applied`**
   - Emitted when approved proposal activates in UniverseRegistry
   - Fields: `sector_name`, `version`

### Configuration

**Config File:** `config/config.yaml`

**Added Section:**
```yaml
# LLM Universe Advisor Configuration
llm:
  # Provider mode: primary_fallback | ensemble | openai_only | anthropic_only
  mode: "primary_fallback"

  # Primary provider (for primary_fallback mode)
  primary: "openai"  # openai | anthropic

  # Model specifications
  openai_model: "gpt-4-turbo-preview"
  anthropic_model: "claude-3-5-sonnet-20241022"

  # API timeouts
  timeout_seconds: 30

  # Safety guardrails
  min_confidence: 0.70
  proposal_ttl_minutes: 120
  max_sector_toggles_per_day: 1
  cooldown_days: 3

  # RSS event filtering
  rss_lookback_hours: 24
  rss_max_headlines: 100

  # Auto-generation
  auto_generate_enabled: true
  auto_generate_interval_hours: 4
```

**Environment Variables Required:**
- `OPENAI_API_KEY` - If using OpenAI provider
- `ANTHROPIC_API_KEY` - If using Anthropic provider

**Config Model:** `src/app/config.py`
- Added fields: `llm_mode`, `llm_primary`, `llm_openai_model`, `llm_anthropic_model`, `llm_timeout`, `llm_min_confidence`, `llm_proposal_ttl_minutes`, `llm_max_sector_toggles_per_day`, `llm_cooldown_days`, `llm_rss_lookback_hours`, `llm_rss_max_headlines`, `llm_auto_generate_enabled`, `llm_auto_generate_interval_hours`

### Testing

**Test Files:**
- `tests/mocks/mock_llm_provider.py` - Mock LLM provider with deterministic responses
- `tests/test_mock_llm_provider.py` - Tests for mock provider (3 tests)
- `tests/test_universe_advisor.py` - Comprehensive unit tests (15+ tests)
- `tests/test_constituent_proposals.py` - Constituent change tests (5 tests)

**Test Coverage:**
- Provider modes (openai_only, ensemble, primary_fallback)
- Ensemble merge rules (agreement, contradiction, single provider)
- Guardrails (confidence filter, TTL expiry, max toggles, cooldown)
- Market regime detection
- RSS event loading (filtering, deduplication, prioritization)
- Proposal creation and lifecycle (SECTOR_TOGGLE and CONSTITUENT_CHANGE)
- Storage (save/load proposals, append history with both proposal types)
- Constituent change constraint validation (blacklist, duplicates, cooldown, tradability)
- UniverseRegistry staging for ticker add/remove operations
- API endpoints (approve/reject with enum serialization)

**Mock Provider:**
- No network calls required
- Returns deterministic responses
- Records call history for verification
- Supports custom responses for testing

**Test Strategy:**
- All tests use MockLLMProvider (no OpenAI/Anthropic API calls)
- Temporary directories for file I/O
- Fixtures for sample regime, events, sectors
- Isolated unit tests with no external dependencies

### Safety Guarantees

1. **Operator Gating:**
   - All proposals require explicit approval
   - No automatic sector changes
   - Clear approve/reject buttons in UI
   - Confirmation dialog on approve action

2. **Next-Tick Activation:**
   - Approved proposals stage changes immediately
   - Changes activate at loop boundary only (via UniverseRegistry)
   - No mid-loop configuration drift
   - Deterministic activation timing

3. **Best-Effort Generation:**
   - Generation failures logged but never block trading
   - All exceptions caught and logged as warnings
   - Loop continues normally if generation fails
   - Feature is fully optional (can be disabled via config)

4. **Guardrails Enforcement:**
   - Confidence threshold prevents low-quality proposals
   - TTL prevents stale proposals from being applied
   - Daily limits prevent excessive toggling
   - Cooldown prevents flip-flopping

5. **Audit Trail:**
   - All proposals recorded in history file (append-only)
   - Ledger events for all actions (generate, approve, reject, apply)
   - Proposal IDs track specific recommendations
   - Full context preserved (regime, headlines, rationale)

6. **Version Tracking:**
   - UniverseRegistry tracks active_version and pending_version
   - Dashboard shows pending indicator
   - Operators know when changes will activate

7. **Graceful Degradation:**
   - Missing API keys → provider mode falls back or skips generation
   - Missing RSS events → empty event list
   - Missing regime data → UNKNOWN regime, low confidence
   - All edge cases handled without crashing

### File Structure

```
src/app/
├── llm/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py              # Lazy imports
│   │   ├── base.py                  # LLMProvider abstract interface
│   │   ├── openai_provider.py       # OpenAI implementation
│   │   └── anthropic_provider.py    # Anthropic implementation
│   └── factory.py                   # Provider factory with mode logic
│
└── universe_advisor/
    ├── __init__.py
    ├── models.py                    # Proposal, ProposalSet, MarketRegime, Disagreement
    ├── regime.py                    # Market regime detection
    ├── generate.py                  # Generate sector toggle proposals from LLMs
    ├── generate_constituents.py     # Generate ticker-level constituent change proposals
    ├── guardrails.py                # Enforce safety constraints
    ├── apply.py                     # Apply approved proposals (both types)
    └── storage.py                   # Proposals file I/O

out/
├── universe_proposals.json          # Current proposals (atomic write)
└── universe_proposals_history.jsonl # Applied/rejected history (append-only)

tests/
├── mocks/
│   ├── __init__.py
│   └── mock_llm_provider.py         # Mock LLM provider for testing
├── test_mock_llm_provider.py        # Mock provider tests
├── test_universe_advisor.py         # Advisor unit tests (sector toggle)
└── test_constituent_proposals.py    # Constituent change tests
```

---

## Known Constraints
- Alpaca free tier uses IEX feed
- Minute bars require regular-session windowing
- Historical minute data must end at market close
