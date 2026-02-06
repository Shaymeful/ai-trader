# Implementation Plan: Capital Utilization + Exits + Universe Fix

## Status: IN PROGRESS
Branch: feature/utilization-exits-universe-fix

---

## ✅ COMPLETED

### 1. Config Schema Updates
- ✅ Added `risk.target_utilization_pct` (default 0.97)
- ✅ Added `risk.use_total_capital_as_equity_cap` (default true)
- ✅ Added `execution.order_style` ("limit" or "market")
- ✅ Added `execution.limit_offset_bps_buy` (default 10 bps)
- ✅ Added `execution.limit_offset_bps_sell` (default 10 bps)
- ✅ Added `execution.allow_market_in_paper` (default true)
- ✅ Updated `llm.allow_constituent_removals` to true
- ✅ Added LLM removal rubric parameters
- ✅ Updated Config model in `src/app/config.py`
- ✅ Updated YAML loader in `load_config_with_yaml()`

---

## 🔄 IN PROGRESS

### 2. Capital Utilization Implementation

**Files to Modify:**
1. `src/app/allocator.py` - Main allocation logic
2. `src/app/allocation.py` - Budget computation functions
3. Create `src/app/account_summary.py` - Helper to load account_summary.json

**Implementation Steps:**

#### A. Account Summary Loader
```python
# src/app/account_summary.py
def load_account_summary() -> dict | None:
    """Load account_summary.json if it exists."""
    path = Path("out/account_summary.json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None

def get_total_capital() -> Decimal | None:
    """Get total_capital from account_summary.json."""
    summary = load_account_summary()
    if summary and "total_capital" in summary:
        return Decimal(str(summary["total_capital"]))
    return None
```

#### B. Allocator Enhancement
In `src/app/allocator.py:_allocate_with_registry()`:

1. **Load total_capital:**
```python
from src.app.account_summary import get_total_capital

total_capital = get_total_capital()
```

2. **Compute effective_equity_cap:**
```python
# Get broker equity
account_info = self.broker.client.get_account()
broker_equity = float(account_info.equity)

# Apply cap logic
if self.config.use_total_capital_as_equity_cap and total_capital:
    effective_equity_cap = min(Decimal(broker_equity), total_capital)
else:
    effective_equity_cap = Decimal(broker_equity)

# Apply target utilization
budget_base = float(effective_equity_cap) * self.config.target_utilization_pct
```

3. **Log capital details:**
```python
self.logger.info(
    f"Capital Allocation: broker_equity=${broker_equity:.2f}, "
    f"total_capital=${total_capital or 'N/A'}, "
    f"effective_cap=${effective_equity_cap:.2f}, "
    f"target_util={self.config.target_utilization_pct:.2%}, "
    f"budget_base=${budget_base:.2f}"
)
```

4. **Implement top-off pass:**
After initial allocation, compute remaining budget and distribute:
```python
# Calculate used notional
used_notional = sum(
    float(current_prices[sym]) * abs(qty)
    for sym, qty in target_positions.items()
)

# Calculate remaining budget
remaining_budget = budget_base - used_notional

# Top-off pass
if remaining_budget > 50:  # Threshold
    self.logger.info(f"Top-off pass: ${remaining_budget:.2f} remaining")
    # Distribute to highest-conviction BUY intents
    # ... implementation
```

#### C. Add Fractional Share Support
In `src/app/allocation.py:compute_qty_from_notional()`:

```python
def compute_qty_from_notional(
    target_notional: Decimal,
    price: Decimal,
    allow_fractional: bool = False,
) -> int | float:
    """Compute quantity from notional with fractional support."""
    if price <= 0:
        return 0

    qty = target_notional / price

    if allow_fractional:
        return float(qty)  # Keep fractional
    else:
        return int(qty)  # Truncate to whole shares
```

---

### 3. Exit Overlay Implementation

**Status:** Already partially implemented via ExitAdvisor + SellScanner

**Files to Integrate:**
1. `src/app/runner.py` - Call ExitAdvisor at loop start
2. `src/app/exit_advisor.py` - Already implements exit logic
3. `src/app/sell_scanner.py` - Already scans for sell signals

**Integration Steps:**

#### A. Runner Loop Integration
In `src/app/runner.py:run_paper_mode()`:

```python
# Before strategy execution, scan for exits
if not dry_run and config.alpaca_api_key:
    from src.app.exit_advisor import ExitAdvisor

    # Get current positions
    positions = broker.get_positions()

    # Scan for exit signals
    exit_advisor = ExitAdvisor(config)
    exit_candidates = exit_advisor.scan_and_emit_candidates(
        positions, market_data
    )

    # Merge with selector candidates
    all_candidates = selector_candidates + exit_candidates
```

#### B. Strategy Target Override
Strategies should respect EXIT candidates:

```python
# In strategy.generate_intents()
for candidate in candidates:
    if candidate.action == Action.SELL:
        # Override target to 0 for this symbol
        intents.append(PositionIntent(
            symbol=candidate.symbol,
            target_quantity=0,  # Sell all
            conviction=candidate.confidence,
            reason=f"Exit: {candidate.reason}"
        ))
```

**Result:** Allocator will see target=0, executor will compute negative delta, SELL orders generated.

---

### 4. Universe/Sector Integration Fix

**Files to Modify:**
1. `src/app/runner.py` - Use universe_registry.resolve()
2. `src/app/selector/run_once.py` - Read from active universe
3. Create `out/universe_active.json` - Canonical active universe file

**Implementation Steps:**

#### A. Export Active Universe
In `src/app/runner.py` loop:

```python
# After registry activation
from src.app.universe_registry import UniverseRegistry

universe_registry = UniverseRegistry()
activated = universe_registry.check_and_activate_pending()

# Export active universe
active_universe = universe_registry.resolve()
with open("out/universe_active.json", "w") as f:
    json.dump({
        "symbols": active_universe,
        "timestamp": datetime.now(UTC).isoformat(),
        "sectors": {
            name: {
                "enabled": sector.enabled,
                "symbols": sector.symbols
            }
            for name, sector in universe_registry.sectors.items()
            if sector.enabled
        }
    }, f, indent=2)
```

#### B. Selector Integration
In `src/app/selector/run_once.py`:

```python
# Load universe from active file
def load_active_universe() -> list[str]:
    """Load active universe from runtime file."""
    path = Path("out/universe_active.json")
    if path.exists():
        with open(path) as f:
            data = json.load(f)
            return data.get("symbols", [])

    # Fallback to config
    from src.app.config import load_config_with_yaml
    config = load_config_with_yaml()
    return config.universe_symbols

# Use in selector
universe = load_active_universe()
```

#### C. Data Provider Integration
Pass active universe to data providers:

```python
# In runner
universe_symbols = universe_registry.resolve()

# Pass to AlpacaDataProvider
data_provider = AlpacaDataProvider(
    api_key=config.alpaca_api_key,
    secret_key=config.alpaca_secret_key,
    symbols=universe_symbols  # Use active universe
)
```

---

### 5. Order Style Configuration

**Files to Modify:**
1. `src/app/order_pipeline.py` - Implement order_style logic
2. Use config.order_style, config.limit_offset_bps_*, config.allow_market_in_paper

**Implementation:**

```python
# In submit_signal_order()
if config.order_style == "market":
    if mode == "paper" and config.allow_market_in_paper:
        order_type = OrderType.MARKET
        limit_price = None
    elif mode == "live":
        order_type = OrderType.MARKET
        limit_price = None
    else:
        # Fallback to limit in paper if not allowed
        order_type = OrderType.LIMIT
        limit_price = calculate_limit_price(side, quote, config)
else:
    # Limit orders with tighter offsets
    order_type = OrderType.LIMIT
    limit_price = calculate_limit_price_tight(
        side, quote, config.limit_offset_bps_buy, config.limit_offset_bps_sell
    )
```

---

### 6. LLM Removal Rubric

**Files to Modify:**
1. `src/app/llm/generator.py` - Add removal proposal logic
2. Track ticker eligibility failures and activity

**Implementation:**

```python
# Track eligibility failures
ticker_failures = {}  # symbol -> failure_count

# In proposal generation
if config.llm_allow_constituent_removals:
    # Check removal criteria
    for symbol in current_sector_symbols:
        # Criterion 1: Failed eligibility checks
        if ticker_failures.get(symbol, 0) >= config.llm_removal_min_failed_eligibility_checks:
            propose_removal(symbol, "repeated eligibility failures")

        # Criterion 2: No activity
        if days_since_last_activity(symbol) >= config.llm_removal_min_days_no_activity:
            propose_removal(symbol, "no trading activity")

        # Criterion 3: Negative news
        if negative_news_confidence(symbol) >= config.llm_removal_stale_negative_news_confidence:
            propose_removal(symbol, "persistent negative sentiment")
```

---

### 7. Idle Trading Diagnostics

**Files to Modify:**
1. `src/app/runner.py` - Add diagnostic logging
2. `src/ui_api/app.py` - Add /health/detailed endpoint field

**Implementation:**

```python
# In runner, track why no trades occurred
def diagnose_idle_trading(config, universe, candidates, positions) -> str:
    """Diagnose why trading is idle."""

    # Check in precedence order
    if is_paused():
        return "Trading paused via pause flag"

    if not is_market_open():
        return "Market closed"

    if not universe or len(universe) == 0:
        return "No enabled sectors / active universe empty"

    if not candidates or len(candidates) == 0:
        return "No candidates from selector (snapshot missing/stale)"

    expired = [c for c in candidates if c.is_expired()]
    if len(expired) == len(candidates):
        return "All candidates expired"

    eligible = [c for c in candidates if is_eligible(c)]
    if len(eligible) == 0:
        return "All candidates filtered by eligibility checks"

    if risk_caps_preventing_orders():
        return "Risk caps preventing new orders (exposure/loss limits)"

    return "Active - no immediate blocking condition"

# Log in runner
idle_reason = diagnose_idle_trading(...)
logger.info(f"Trading Status: {idle_reason}")

# Expose in API
@app.get("/health/detailed")
async def get_health_detailed():
    return {
        ...
        "why_not_trading": idle_reason
    }
```

---

## TODO

- [ ] Implement account_summary.py helper
- [ ] Enhance allocator with capital utilization
- [ ] Integrate ExitAdvisor into runner loop
- [ ] Export universe_active.json in runner
- [ ] Update selector to read active universe
- [ ] Implement order_style logic in order_pipeline
- [ ] Add LLM removal rubric logic
- [ ] Add idle trading diagnostics
- [ ] Write comprehensive tests
- [ ] Update ARCHITECTURE.md
- [ ] Test end-to-end with real scenarios

---

## Testing Checklist

- [ ] Config loads new parameters correctly
- [ ] total_capital from account_summary.json is used as cap
- [ ] Budget uses target_utilization_pct (97%)
- [ ] Top-off distributes remaining budget
- [ ] Exit candidates cause SELL orders
- [ ] UI-created sectors appear in active universe
- [ ] Selector uses active universe
- [ ] Market orders work in paper mode
- [ ] Limit orders use tighter offsets
- [ ] Removal proposals generated correctly
- [ ] Idle trading diagnostics are accurate

---

## Verification Steps

1. **Set total capital to $30,000 in UI**
2. **Set target_utilization_pct to 0.97**
3. **Switch order_style to market (paper mode)**
4. **Enable a UI-created sector**
5. **Confirm sells occur when exits trigger**
6. **Check logs for capital utilization details**
7. **Verify active universe file is created**
8. **Test selector reads from active universe**
