# PR Summary: Small Cap Swing Trading Mode with Execution Gate

## Overview

Added "Small Cap Swing" trading mode with **hard execution gates** to shift the system toward small/mid cap stocks for swing trading while preventing trades on mega caps. This implementation provides centralized, config-driven tradability filtering that applies to ALL orders regardless of strategy or universe configuration.

**Implementation Date:** 2026-02-04

---

## Motivation

Previously, universe/sector gating was inconsistent and could be bypassed by strategies. There was no mechanism to enforce market cap, price, or liquidity constraints at execution time. This PR solves two key problems:

1. **Inconsistent Gating:** Universe sectors could be enabled, but strategies might still try to trade mega caps
2. **No Market Cap Targeting:** System had no way to target specific market cap ranges (small/mid/large)

**Solution:** Centralized execution gate that runs BEFORE broker submission, blocking orders that violate constraints.

---

## What's New

### 1. Fundamentals Cache Module

**New File:** `src/market_data/fundamentals_cache.py`

Provides market cap, volume, and spread data for tradability filtering.

**Features:**
- In-memory + disk cache (`data/cache/fundamentals.json`, TTL: 24h)
- Manual mappings override file (`data/cache/fundamentals_manual.json`)
- Stub interface for future API integration (Polygon/IEX/FMP)
- Atomic writes with expiration handling

**Data Model:**
```python
@dataclass
class TickerFundamentals:
    symbol: str
    market_cap_usd: float | None
    avg_dollar_volume_20d: float | None
    price: float | None
    spread_bps: float | None
    last_updated: str | None
```

**Example Manual Mapping:**
```json
{
  "AFRM": {
    "symbol": "AFRM",
    "market_cap_usd": 9000000000,
    "avg_dollar_volume_20d": 200000000,
    "price": 35.0,
    "spread_bps": 15
  }
}
```

---

### 2. Execution Gate (Tradability Filter)

**New File:** `src/app/execution/tradability_filter.py`

Centralized hard gate that enforces constraints on ALL orders.

**Config Parameters:**
```yaml
execution_gate:
  min_market_cap_usd: 300000000        # $300M floor
  max_market_cap_usd: 10000000000      # $10B ceiling
  min_price: 3.00                      # Avoid penny stocks
  max_price: 80.00                     # Upper bound
  min_avg_dollar_volume_20d: 5000000   # $5M/day liquidity
  max_spread_bps: 100                  # 1.00% max spread
  exclude_symbols: []                  # Ban list
  allow_symbols: []                    # Allowlist (bypass all checks)
  require_fundamentals: false          # Block if data unavailable
  strict_mode: true                    # Hard block vs advisory
```

**Block Reasons:**
- `market_cap_below_minimum`
- `market_cap_above_maximum`
- `price_below_minimum`
- `price_above_maximum`
- `avg_dollar_volume_below_minimum`
- `bid_ask_spread_above_maximum`
- `symbol_in_exclude_list`
- `fundamentals_data_not_available`

**Key Methods:**
```python
class TradabilityGate:
    def check_tradability(symbol, price) -> TradabilityResult
    def get_blocked_symbols(symbols) -> dict[symbol, reason]
    def get_allowed_symbols(symbols) -> list[symbol]
```

---

### 3. Small Cap Swing Mode Profile

**Updated File:** `config/modes.yaml`

New profile: `small_cap_swing`

**Strategy:**
- AI_COPILOT_WEIGHTED: enabled, weight=0.50, execution_enabled=true
- Higher allocation for focused swing trading

**Universe:**
- core_index: disabled (no SPY/QQQ)
- mega_cap_tech: disabled (no AAPL/MSFT/NVDA)
- us_sector_etfs: disabled
- automation: enabled

**Selector (Swing Profile):**
- candidates_max_count: 60
- candidates_min_confidence: 0.55
- ttl_minutes_buy: 720 (12 hours - swing setups)
- ttl_minutes_sell: 480 (8 hours)

**AI Co-Pilot:**
- trade_rationale: enabled
- daily_journal: disabled (save tokens)
- strategy_critique: disabled (save tokens)
- universe_ticker_manager: enabled (discovery)

**Execution Gate:**
- Full small/mid cap constraints (see above)

---

### 4. Executor Integration

**Modified File:** `src/app/execution/alpaca_executor.py`

**Changes:**
1. Added imports for TradabilityGate and FundamentalsCache
2. Updated `__init__` to accept `execution_gate_config` and `fundamentals_cache` params
3. Inserted gate check in `_execute_orders()` before broker submission (line ~380)

**Flow:**
```python
# For each order slice:
if self.execution_gate:
    result = self.execution_gate.check_tradability(symbol, price)
    if not result.allowed:
        orders_skipped.append((symbol, result.message))
        continue  # Skip order

# Place order (if gate passed)
broker.submit_order(...)
```

**Logging:**
```
AAPL: BLOCKED by execution gate: Market cap $3,500,000,000,000 above maximum $10,000,000,000
```

---

### 5. Runner Integration

**Modified File:** `src/app/runner.py`

**Changes:**
1. Added imports for mode profile loading and execution gate config
2. Load execution gate config from active mode profile (lines 1073-1105)
3. Pass config to AlpacaExecutor initialization

**Console Output:**
```
Execution gate ENABLED (mode: small_cap_swing)
  Market cap range: $300,000,000 - $10,000,000,000
  Price range: $3.00 - $80.00
  Min liquidity: $5,000,000/day
```

---

### 6. Dashboard UI Enhancements

**Modified File:** `src/ui_api/dashboard.html`

**Added:**
1. **Small Cap Swing Button** (3rd mode option)
   - Purple badge color
   - Description: "Small/mid caps only, swing trading, 12hr+ holds"

2. **Execution Filters Panel** (NEW)
   - Shows active gate constraints
   - Market cap range (formatted: $300M - $10B)
   - Price range ($3.00 - $80.00)
   - Min daily volume ($5M/day)
   - Max spread (100 bps)
   - Only visible when gate configured

**CSS Classes:**
- `.mode-badge.small-cap` - Purple badge
- `.execution-filters-panel` - Container
- `.filters-grid` - 2x2 layout
- `.badge-success` - "ACTIVE" indicator

**JavaScript:**
- Updated `loadModeStatus()` to handle `small_cap_swing`
- Added `loadExecutionGateFilters()` to populate filter panel

---

### 7. API Endpoint Updates

**Modified File:** `src/ui_api/app.py`

**Changes:**
- Added `execution_gate` to coordinated_settings in GET /api/mode response

**Response Format:**
```json
{
  "active_profile": "small_cap_swing",
  "coordinated_settings": {
    "strategies": {...},
    "universe": {...},
    "selector": {...},
    "ai_copilot": {...},
    "execution_gate": {
      "min_market_cap_usd": 300000000,
      "max_market_cap_usd": 10000000000,
      ...
    }
  }
}
```

---

### 8. Tests

**New Files:**
- `tests/test_tradability_filter.py` - 25+ tests for execution gate
- `tests/test_small_cap_mode.py` - Mode profile integration tests

**Coverage:**
- Market cap constraints (min, max, range)
- Price constraints (min, max)
- Liquidity and spread constraints
- Exclude/allow symbol lists
- Strict vs advisory mode
- Fundamentals unavailable handling
- Batch operations
- Mode profile validation

**Run Tests:**
```bash
pytest tests/test_tradability_filter.py -v
pytest tests/test_small_cap_mode.py -v
```

---

### 9. Documentation

**Updated File:** `docs/ARCHITECTURE.md`

Added comprehensive section (~400 lines):
- Small Cap Swing mode overview
- Execution gate architecture
- Fundamentals cache design
- Order execution flow diagram
- API endpoint specs
- Testing strategy
- Operational notes
- Safety constraints
- Future enhancements

**Compliance:** Spec Sync Rule ✓

---

## Files Changed

### New Files (5)
```
src/market_data/__init__.py                       # Module init
src/market_data/fundamentals_cache.py             # Fundamentals cache
src/app/execution/tradability_filter.py           # Execution gate
tests/test_tradability_filter.py                  # Gate tests
tests/test_small_cap_mode.py                      # Mode tests
data/cache/fundamentals_manual.json               # Manual mappings
```

### Modified Files (6)
```
config/modes.yaml                     # Added small_cap_swing profile
src/app/execution/alpaca_executor.py  # Integrated execution gate
src/app/runner.py                     # Load gate config from mode
src/ui_api/dashboard.html             # Added mode button + filters panel
src/ui_api/app.py                     # Added execution_gate to API response
docs/ARCHITECTURE.md                  # Comprehensive documentation
```

---

## Testing

### Manual Testing with curl

#### 1. Switch to Small Cap Swing Mode
```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"profile": "small_cap_swing"}'
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Mode switched to 'small_cap_swing'. Changes will take effect on next loop iteration.",
  "pending_version": 5
}
```

#### 2. Verify Mode Status
```bash
curl -s http://localhost:8000/api/mode | python -m json.tool
```

**Expected Output:**
```json
{
  "active_profile": "small_cap_swing",
  "available_profiles": ["normal", "aggressive_tech_energy", "small_cap_swing"],
  "profile_description": "Small/mid cap swing trading with market cap constraints...",
  "coordinated_settings": {
    "execution_gate": {
      "min_market_cap_usd": 300000000,
      "max_market_cap_usd": 10000000000,
      "min_price": 3.0,
      "max_price": 80.0,
      ...
    }
  }
}
```

#### 3. Check Blocked Trades in Logs
```bash
grep "BLOCKED by execution gate" logs/loop/loop_*.log
```

**Expected Output:**
```
AAPL: BLOCKED by execution gate: Market cap $3,500,000,000,000 above maximum $10,000,000,000
NVDA: BLOCKED by execution gate: Market cap $1,800,000,000,000 above maximum $10,000,000,000
MSFT: BLOCKED by execution gate: Market cap $3,000,000,000,000 above maximum $10,000,000,000
```

#### 4. Verify Small Cap Trades Allowed
```bash
grep "Order placed.*AFRM\|SOFI\|IONQ" logs/loop/loop_*.log
```

**Expected Output:**
```
Order placed: AFRM BUY 50 @ $35.00 (slice 1/1, ID: abc123)
Order placed: SOFI BUY 100 @ $8.50 (slice 1/1, ID: def456)
```

---

### Dashboard UI Testing

1. **Open Dashboard:** http://localhost:8000
2. **Locate "Trading Mode" Panel** (below health panel)
3. **Observe Current Mode:** Should show "Normal" badge (blue)
4. **Click "Small Cap Swing" Button**
5. **Expected Changes:**
   - Badge changes to "Small Cap Swing" (purple)
   - Success notification appears
   - Description updates
   - **Execution Filters panel appears** below mode selector
   - Shows: Market cap $300M - $10B, Price $3-$80, Volume $5M/day, Spread 100 bps
6. **Wait for Next Loop** or trigger manually
7. **Verify in Logs:** Execution gate blocks mega caps, allows small caps

---

## Architecture Highlights

### Execution Gate Flow

```
Strategy generates intents
    ↓
Allocator creates target_positions
    ↓
Executor reconciles with current positions
    ↓
Generate OrderInstructions
    ↓
Slice orders to max_order_notional
    ↓
FOR EACH ORDER SLICE:
    ├─ Check max_positions_notional (risk cap)
    │
    ├─ **EXECUTION GATE CHECK** ◄── NEW
    │  ├─ Load fundamentals for symbol
    │  ├─ Check allow_symbols (bypass)
    │  ├─ Check exclude_symbols (block)
    │  ├─ Check market_cap_usd (min/max)
    │  ├─ Check price (min/max)
    │  ├─ Check avg_dollar_volume (min)
    │  ├─ Check spread_bps (max)
    │  └─ If blocked: log reason, skip order
    │
    ├─ broker.submit_order(...) [if gate passed]
    └─ Update exposure tracking
```

### Configuration Precedence

**Order (highest to lowest):**
1. `allow_symbols` - Bypass all checks
2. `exclude_symbols` - Hard block
3. Market cap constraints
4. Price constraints
5. Liquidity constraints
6. Spread constraints
7. Fundamentals availability check

**First violation blocks the order.** Subsequent checks not evaluated.

---

## Safety Gates

### 1. Hard Block (Not Advisory)
- Execution gate BLOCKS orders, does not warn
- No orders placed for blocked symbols

### 2. Strategy-Agnostic
- Applies to ALL strategies (AI_COPILOT_WEIGHTED, MeanReversion, Trend)
- Cannot be bypassed by strategy config

### 3. Universe-Independent
- Enforces even if universe allows symbol
- Universe enablement necessary but not sufficient

### 4. Allow List Override
- If symbol in `allow_symbols`, ALL checks bypassed
- Use for temporary exceptions

### 5. Fundamentals Fallback
- If data unavailable and `require_fundamentals=false`, allow order
- Logs warning but does not block
- Set `require_fundamentals=true` for strict enforcement

### 6. Atomic Mode Switch
- All coordinated settings applied together
- Persisted to `data/mode_override.json`

---

## Expected Behavior

### In Normal Mode (Default)
- No execution gate active
- Trades can include mega caps (AAPL, MSFT, NVDA, etc.)
- Universe sectors determine eligibility

### In Small Cap Swing Mode
- Execution gate ACTIVE
- Mega caps BLOCKED (AAPL $3.5T > $10B max)
- Small caps ALLOWED (AFRM $9B, SOFI $8B, IONQ $3.5B)
- Penny stocks BLOCKED (price < $3.00)
- Illiquid stocks BLOCKED (volume < $5M/day)
- Wide-spread stocks BLOCKED (spread > 100 bps)

### Example Blocked Orders
- **AAPL:** Market cap $3.5T > $10B max
- **NVDA:** Market cap $1.8T > $10B max
- **PLTR:** Market cap $45B > $10B max
- **SPY:** Market cap $500B (ETF, but > $10B max)
- **PENNY:** Price $0.50 < $3.00 min
- **ILLIQUID:** Volume $500K < $5M min

### Example Allowed Orders
- **AFRM:** $9B cap (within range), $35 price, $200M volume
- **SOFI:** $8B cap (within range), $8.50 price, $150M volume
- **IONQ:** $3.5B cap (within range), $18 price, $80M volume
- **RIVN:** $12B cap (within range... wait, exceeds $10B!)
  - **BLOCKED!** (This is by design - target small/mid caps only)

---

## Operational Notes

### Adding New Fundamentals

Edit `data/cache/fundamentals_manual.json`:
```json
{
  "NEWSYMBOL": {
    "symbol": "NEWSYMBOL",
    "market_cap_usd": 5000000000,
    "avg_dollar_volume_20d": 50000000,
    "price": 25.0,
    "spread_bps": 15
  }
}
```

Restart runner or wait for cache reload.

### Temporarily Allowing Mega Cap

Edit `config/modes.yaml`:
```yaml
small_cap_swing:
  execution_gate:
    allow_symbols: ["NVDA"]  # Bypass all checks for NVDA
```

Restart dashboard, switch modes.

### Disabling Execution Gate

Remove `execution_gate` section from mode profile, or set constraints to None.

---

## Future Enhancements

1. **API Integration:** Polygon/IEX/FMP for auto-refreshing fundamentals
2. **Additional Modes:** Micro Cap Volatility, Large Cap Dividend, Earnings Play
3. **Dynamic Adjustments:** VIX-based spread widening, time-of-day constraints
4. **Candidate Pre-Filtering:** Apply gate before LLM evaluation (save tokens)
5. **Historical Backtesting:** Compare small_cap_swing vs other modes

---

## Migration Notes

**No breaking changes.** Existing installations will:
- Use "normal" profile by default (no execution gate)
- Continue functioning with existing strategy/universe settings
- Need to explicitly switch to `small_cap_swing` to activate gate

**To use small cap swing mode:**
1. Pull latest changes
2. Restart dashboard API server
3. Open dashboard → switch to "Small Cap Swing"
4. Next loop iteration applies gate

---

## Questions for Review

1. **Market cap thresholds:** Is $300M-$10B the right range for "small cap swing"? Should it be $500M-$5B?
2. **Allow list usage:** Should we pre-populate `allow_symbols` with any tickers for testing?
3. **Spread tolerance:** Is 100 bps too wide for small caps? Should it be tighter (50 bps)?
4. **Fundamentals API:** Which API should we prioritize for integration (Polygon, IEX, FMP)?
5. **Mode naming:** Is "Small Cap Swing" clear enough? Alternative: "Small/Mid Cap Swing"?

---

## Acknowledgments

This feature builds on the existing mode profiles architecture (Normal, Aggressive) and follows established patterns:
- StrategyRegistry (staged changes, versioning)
- UniverseRegistry (sector toggles)
- Runtime overrides (mode_override.json)
- Execution flow (AlpacaExecutor)

---

**PR Status:** ✅ COMPLETE
**Tests:** ✅ PASSING
**Documentation:** ✅ UPDATED
**Compliance:** ✅ Spec Sync Rule

Ready for review and testing!
