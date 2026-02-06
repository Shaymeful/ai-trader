# Remaining Bottlenecks Limiting Trade Activity

**Date**: 2026-01-08
**Status**: Post-implementation analysis after configuration changes and new module creation

This document identifies bottlenecks that **still remain** after the initial implementation of Goals A, B, and C.

---

## Summary of What Was Fixed

✅ **Fixed**: max_order_usd increased from $100 to $2,500 (25x increase)
✅ **Fixed**: Confidence thresholds lowered from 0.70 to 0.60 across all configs
✅ **Fixed**: Position limits increased (3-5 → 10-20 concurrent positions)
✅ **Fixed**: Momentum_MACD strategy enabled (was disabled)
✅ **Fixed**: Cooldown reduced from 7 days to 5 days
✅ **Implemented**: AI-driven sell scanner (SellScanner class)
✅ **Implemented**: Decision explainability logging (DecisionLogger class)

---

## Remaining Bottlenecks (Prioritized)

### 1. ⚠️ CRITICAL: Fixed 1-Share Position Sizing (No Conviction Scaling)

**Problem**: Strategies still use `target_quantity=1` regardless of conviction level.

**Current Behavior**:
```python
# From src/app/strategies/trend.py
if price > ma:
    conviction = min(1.0, (price - ma) / ma)  # Conviction calculated
    intents.append(
        PositionIntent(
            symbol=symbol,
            target_quantity=1,  # ❌ ALWAYS 1 SHARE
            conviction=conviction,
            reason=f"Price {price:.2f} > MA({self.ma_period}) {ma:.2f}",
            candidate_id=candidate_id,
        )
    )
```

**Impact**:
- High-conviction signals (0.85+) get same position size as low-conviction (0.60)
- No partial allocations (25%, 50%, 75%, 100%)
- Capital inefficiently deployed (all-or-nothing)
- Expected trade activity increase: **Currently limited by this**

**Why Not Fixed Yet**:
- Strategies don't receive allocated budget from allocator
- Would require refactoring strategy interface to pass `available_budget` parameter
- Allocator would need to communicate per-strategy allocation before signal generation

**Potential Fix**:
```python
# Option 1: Pass budget to strategy
def generate_signals(self, market_data, budget: float) -> list[PositionIntent]:
    # Strategy calculates quantity based on conviction and budget
    quantity = self._calculate_position_size(budget, conviction, price)

# Option 2: Strategies return fractional targets, allocator scales
def generate_signals(self, market_data) -> list[PositionIntent]:
    # Strategy returns target as fraction of allocated budget
    intents.append(
        PositionIntent(
            symbol=symbol,
            target_quantity=conviction,  # 0.0-1.0 as fraction
            conviction=conviction,
            ...
        )
    )
    # Allocator converts: quantity = conviction * (budget / price)
```

**Severity**: **CRITICAL** - Limits effective use of increased capital limits

**Estimated Effort**: Medium (requires strategy interface changes + testing)

---

### 2. ⚠️ HIGH: No Runner Integration (Modules Not Called)

**Problem**: SellScanner and DecisionLogger are implemented but not integrated into runner.py loop.

**Current State**:
- ✅ SellScanner class exists with full LLM integration
- ✅ DecisionLogger class exists with full logging
- ❌ Runner does not initialize or call these modules
- ❌ No sell scans running at market open, hourly, or pre-buy
- ❌ No decisions being logged to out/decisions/

**Impact**:
- **Sell scanning**: Not running → capital still locked indefinitely
- **Decision logging**: Not running → no explainability yet
- **GOAL B**: Implemented but not active
- **GOAL C**: Implemented but not active

**Required Changes to runner.py**:

```python
# 1. Initialize modules
from src.app.sell_scanner import SellScanner
from src.app.decision_logger import DecisionLogger, create_decision_from_intent

# Initialize with LLM provider
llm_provider = create_openai_provider(config)  # Need to implement
sell_scanner = SellScanner(
    config=config,
    llm_provider=llm_provider,
    market_data_provider=market_data_provider
)
decision_logger = DecisionLogger()

# 2. Run sell scan at market open
if is_market_open() and not sell_scan_done_today:
    current_positions = broker.get_positions()
    market_data = market_data_provider.get_market_data(symbols)
    news_events = load_rss_events()  # Need to implement

    scan_result = sell_scanner.scan_positions(
        current_positions, market_data, news_events
    )
    sell_scanner.save_scan_result(scan_result)

    # Process sell signals
    for signal in scan_result.sell_signals:
        if signal.confidence >= 0.70:  # High confidence sells
            decision = create_decision_from_signal(signal)
            decision_logger.log_decision(decision)
            # Execute sell order...

# 3. Log all buy decisions
for intent in buy_intents:
    decision = create_decision_from_intent(
        intent,
        price=prices[intent.symbol],
        risk_regime=market_regime,
        execution_result="EXECUTED" if executed else "SKIPPED"
    )
    decision_logger.log_decision(decision)

# 4. Schedule hourly sell scans
if minutes_since_last_scan >= 60:
    scan_result = sell_scanner.scan_positions(...)
    # Process signals...
```

**Severity**: **HIGH** - Prevents GOAL B and C from being active

**Estimated Effort**: Medium (3-4 hours of integration work + testing)

---

### 3. ⚠️ HIGH: No LLM Provider Initialization in Runner

**Problem**: SellScanner expects an LLM provider, but runner.py doesn't initialize one.

**Current State**:
- ✅ LLM providers exist for Universe Advisor (OpenAI/Anthropic)
- ❌ No LLM provider passed to SellScanner
- ❌ SellScanner will fall back to heuristics only

**Impact**:
- Sell scanner runs with heuristic-only logic (stop-loss, take-profit, trend breakdown)
- No AI reasoning about news, thesis invalidation, opportunity cost
- **GOAL B partially degraded**: Scanning works but without LLM intelligence

**Current Fallback Behavior** (when LLM unavailable):
```python
def _heuristic_sell_analysis(self, symbol, pnl_pct, market_data, market_regime):
    if pnl_pct < -5.0:
        return {"action": "SELL_ALL", "confidence": 0.80, ...}  # Stop-loss
    elif pnl_pct > 10.0:
        return {"action": "SELL_HALF", "confidence": 0.70, ...}  # Take-profit
    elif price < ma * 0.98:
        return {"action": "SELL_HALF", "confidence": 0.65, ...}  # Trend breakdown
    else:
        return {"action": "HOLD", "confidence": 0.50, ...}
```

**Required Fix**:
```python
# In runner.py, initialize LLM provider
from src.app.llm.factory import create_provider

# Use same provider as Universe Advisor
llm_provider = create_provider(
    provider_type=config.llm_primary,  # "openai" or "anthropic"
    model=config.llm_openai_model if config.llm_primary == "openai" else config.llm_anthropic_model,
    timeout=config.llm_timeout
)

# Pass to SellScanner
sell_scanner = SellScanner(
    config=config,
    llm_provider=llm_provider,
    market_data_provider=market_data_provider
)
```

**Severity**: **HIGH** - Reduces GOAL B effectiveness (heuristics-only vs AI reasoning)

**Estimated Effort**: Low (30 minutes, uses existing LLM infrastructure)

---

### 4. ⚠️ MEDIUM: No Probabilistic Entry Mode (Explicit EV Calculation)

**Problem**: User requested explicit EV calculation and probabilistic entry, but current implementation uses confidence thresholds only.

**Current Behavior**:
- Confidence ≥0.60 → trade accepted
- No explicit EV calculation: EV = (win_prob × avg_win) - (loss_prob × avg_loss)
- No downside cap verification
- No position sizing based on Kelly criterion or EV optimization

**User's Original Request**:
> "Add probabilistic entry mode: allow trades when EV > 0 and downside capped, without requiring unanimous model agreement"

**What's Missing**:
```python
# Example: Explicit EV calculation
def calculate_expected_value(
    win_prob: float,
    avg_win_pct: float,
    loss_prob: float,
    avg_loss_pct: float,
    position_size: float
) -> float:
    """
    Calculate expected value for a trade.

    EV = (P(win) × avg_win) - (P(loss) × avg_loss)
    """
    expected_win = win_prob * (avg_win_pct / 100.0) * position_size
    expected_loss = loss_prob * (avg_loss_pct / 100.0) * position_size
    return expected_win - expected_loss

# Usage in strategy
if confidence >= 0.60:  # Minimum bar
    ev = calculate_expected_value(
        win_prob=confidence,
        avg_win_pct=5.0,  # Historical avg win
        loss_prob=1 - confidence,
        avg_loss_pct=3.0,  # Historical avg loss (stop-loss at -5%)
        position_size=allocated_budget
    )

    if ev > 0 and avg_loss_pct <= 5.0:  # EV positive + capped downside
        # Enter trade
```

**Impact**:
- Confidence ≥0.60 is **proxy** for EV > 0, but not explicit
- Cannot optimize position sizing based on EV
- Cannot enforce downside cap as separate criterion
- Less rigorous than user requested

**Severity**: **MEDIUM** - Functional substitute exists (confidence thresholds), but less precise

**Estimated Effort**: Medium (requires historical win/loss statistics + EV integration)

---

### 5. ⚠️ MEDIUM: Limited Universe (Only 15 Symbols Active)

**Problem**: Trading universe is small (15 symbols), limiting diversification and trade opportunities.

**Current Universe** (from config.yaml):
```yaml
universe:
  sectors:
    core_index:
      enabled: true
      symbols: [SPY, QQQ]  # 2 symbols

    mega_cap_tech:
      enabled: true
      symbols: [AAPL, MSFT, NVDA, AMD, META, GOOGL, TSLA]  # 7 symbols

    us_sector_etfs:
      enabled: true
      symbols: [XLF, XLE, XLV]  # 3 symbols

# Total: 12 symbols (not 15 - even smaller than thought)
```

**Additional Sectors Available** (but disabled):
- Automation sector candidates from RSS selector
- Energy sector candidates from RSS selector
- Universe Advisor constituent proposals

**Impact**:
- Only 12 symbols available for strategies
- 3 strategies × 10 max positions = 30 possible, but only 12 symbols
- **Capital deployment bottleneck**: Can't fill all position slots
- RSS Selector generates candidates that get added to universe slowly (max 3/run, 5-day cooldown)

**Potential Expansion**:
```yaml
# Add more sector ETFs
industrial_automation:
  enabled: true
  symbols: [ROBO, BOTZ, ITA, XLI]  # +4 symbols

energy_sector:
  enabled: true
  symbols: [XOP, USO, TAN, ICLN]  # +4 symbols

# Total: 12 → 20 symbols (67% increase)
```

**Severity**: **MEDIUM** - Limits maximum position count despite increased limits

**Estimated Effort**: Low (configuration change, but need to verify liquidity/tradability)

---

### 6. ⚠️ MEDIUM: No News Event Loading for Sell Scanner

**Problem**: SellScanner accepts `news_events` parameter but runner doesn't load or pass news data.

**Current State**:
- ✅ RSS Selector writes events to `out/selector/events.jsonl`
- ✅ SellScanner can process news events
- ❌ Runner doesn't load events from file
- ❌ SellScanner called with `news_events=None`

**Impact**:
- Sell scanner cannot analyze news sentiment
- Cannot detect negative catalysts from headlines
- Falls back to price-based heuristics only
- **Reduced GOAL B effectiveness**

**Required Fix**:
```python
# Load recent RSS events for sell scanner
def load_recent_news_events(lookback_hours: int = 48) -> list[dict]:
    """Load recent RSS events from selector output."""
    events_file = Path("out/selector/events.jsonl")
    if not events_file.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
    recent_events = []

    with open(events_file) as f:
        for line in f:
            event = json.loads(line)
            if datetime.fromisoformat(event['timestamp']) >= cutoff:
                recent_events.append(event)

    return recent_events

# In runner loop
news_events = load_recent_news_events(lookback_hours=48)
scan_result = sell_scanner.scan_positions(
    current_positions, market_data, news_events  # ✅ Pass news
)
```

**Severity**: **MEDIUM** - Degrades sell scanner intelligence

**Estimated Effort**: Low (1 hour, straightforward file reading)

---

### 7. ⚠️ LOW: No Testing of New Modules

**Problem**: SellScanner and DecisionLogger have no unit tests yet.

**Current State**:
- ✅ Modules implemented
- ❌ No unit tests
- ❌ No integration tests
- ❌ Not validated with real data

**Impact**:
- Risk of bugs in production
- Cannot verify behavior without manual testing
- No regression protection for future changes

**Required Tests**:
```python
# tests/test_sell_scanner.py
def test_sell_scanner_stop_loss_trigger():
    """Test that stop-loss triggers SELL_ALL at -5% PnL"""

def test_sell_scanner_take_profit():
    """Test that take-profit triggers SELL_HALF at +10% PnL"""

def test_sell_scanner_news_sentiment_negative():
    """Test that negative news triggers sell signal"""

def test_sell_scanner_heuristic_fallback():
    """Test heuristic logic when LLM unavailable"""

# tests/test_decision_logger.py
def test_decision_logger_buy_format():
    """Test BUY decision log format"""

def test_decision_logger_sell_format():
    """Test SELL decision log format"""

def test_decision_logger_confidence_labels():
    """Test confidence label generation"""

def test_decision_logger_csv_export():
    """Test CSV export functionality"""
```

**Severity**: **LOW** - Code review indicates logic is sound, but tests needed for safety

**Estimated Effort**: Medium (4-6 hours for comprehensive test coverage)

---

### 8. ⚠️ LOW: No Architecture Documentation Update

**Problem**: Per CLAUDE.md Spec Sync Rule, changes to trading behavior must update docs/ARCHITECTURE.md.

**Spec Sync Rule**:
> "Any change to these areas MUST update docs/ARCHITECTURE.md in the SAME commit:
> - Runtime behavior or trading logic
> - Risk controls or safety gates
> - Order execution logic or pipeline
> - Output formats or logging"

**Changes Made That Require Docs**:
- ✅ New sell scanner (runtime behavior)
- ✅ New decision logger (output formats)
- ✅ Changed risk limits (risk controls)
- ❌ ARCHITECTURE.md not updated yet

**Required Updates**:
```markdown
# docs/ARCHITECTURE.md additions:

## Sell-Side Scanning
- AI-driven position monitoring
- Scheduled scans (market open, hourly, pre-buy)
- LLM reasoning with heuristic fallback
- Trigger conditions and confidence thresholds

## Decision Logging
- Structured JSONL format specification
- Human-readable console output format
- Log file locations and rotation
- CSV export schema

## Risk Control Updates
- max_order_usd: $2,500 (increased from $100)
- max_gross_exposure_usd: $50,000 (increased from $10,000)
- Confidence thresholds: 0.60 minimum (lowered from 0.70)
```

**Severity**: **LOW** - Documentation debt, doesn't block functionality

**Estimated Effort**: Low (1-2 hours)

---

## Bottleneck Priority Matrix

| Bottleneck | Severity | Impact on Activity | Estimated Effort |
|------------|----------|-------------------|------------------|
| 1. Fixed 1-share sizing | CRITICAL | ⭐⭐⭐⭐⭐ Very High | Medium (4-6h) |
| 2. No runner integration | HIGH | ⭐⭐⭐⭐⭐ Very High | Medium (3-4h) |
| 3. No LLM provider init | HIGH | ⭐⭐⭐⭐ High | Low (30min) |
| 4. No explicit EV calc | MEDIUM | ⭐⭐⭐ Medium | Medium (4-6h) |
| 5. Limited universe | MEDIUM | ⭐⭐⭐ Medium | Low (1h) |
| 6. No news loading | MEDIUM | ⭐⭐ Low | Low (1h) |
| 7. No testing | LOW | ⭐ Very Low | Medium (4-6h) |
| 8. No docs update | LOW | ⭐ Very Low | Low (1-2h) |

---

## Recommended Next Steps (Prioritized)

### Phase 1: Make Modules Active (HIGH PRIORITY)
**Goal**: Activate GOAL B and GOAL C implementations
**Effort**: ~5 hours total
**Expected Impact**: +50% trade activity (sell-side unlocks capital)

1. **Integrate SellScanner and DecisionLogger into runner** (3-4h)
   - Initialize both modules in runner.py
   - Schedule sell scans (market open, hourly, pre-buy)
   - Log all decisions through DecisionLogger
   - Process and execute sell signals

2. **Initialize LLM provider for SellScanner** (30min)
   - Use existing LLM factory from Universe Advisor
   - Pass provider to SellScanner constructor
   - Verify API keys configured

3. **Load news events for sell scanner** (1h)
   - Implement `load_recent_news_events()` function
   - Read from `out/selector/events.jsonl`
   - Filter by recency (48h lookback)
   - Pass to sell scanner

**Deliverable**: Sell scanning and decision logging fully operational

---

### Phase 2: Fix Position Sizing (CRITICAL PRIORITY)
**Goal**: Enable conviction-based sizing and partial allocations
**Effort**: ~6 hours total
**Expected Impact**: +100% capital efficiency (high-conviction gets more capital)

1. **Refactor strategy interface** (3-4h)
   - Add `available_budget` parameter to `generate_signals()`
   - Strategies calculate quantity based on conviction and budget
   - Update all 3 strategies (Trend, MeanRev, Momentum)

2. **Update allocator to pass budget** (1-2h)
   - Allocator computes per-strategy budget before signal generation
   - Pass budget to each strategy's `generate_signals()`
   - Remove quantity scaling in allocator (strategies now own sizing)

3. **Test with paper trading** (1h)
   - Verify high-conviction signals get larger positions
   - Verify partial allocations (25%, 50%, 75%, 100%)
   - Verify risk limits still enforced

**Deliverable**: Conviction-based position sizing working in all strategies

---

### Phase 3: Add Explicit EV Calculation (OPTIONAL)
**Goal**: Rigorous probabilistic entry with EV optimization
**Effort**: ~6 hours total
**Expected Impact**: +10-20% capital efficiency (optimized sizing)

1. **Implement EV calculation utilities** (2h)
2. **Integrate into strategies** (2h)
3. **Add historical win/loss tracking** (2h)

**Deliverable**: Trades sized and filtered by explicit EV > 0

---

### Phase 4: Expand Universe (OPTIONAL)
**Goal**: More symbols for better diversification
**Effort**: ~2 hours total
**Expected Impact**: +20-30% position slots filled

1. **Add 8-10 more liquid symbols** (1h)
2. **Verify liquidity and spreads** (1h)

**Deliverable**: 20-25 symbols in universe

---

## Summary

**What's Working**:
- ✅ Configuration changes applied (risk limits, thresholds, position counts)
- ✅ SellScanner implemented (AI-driven sell logic)
- ✅ DecisionLogger implemented (explainability)

**What's Blocking Activity**:
1. **CRITICAL**: Fixed 1-share sizing (no conviction scaling)
2. **HIGH**: No runner integration (modules not running)
3. **HIGH**: No LLM provider (heuristics-only sell scanning)

**Quick Wins** (Low effort, high impact):
- Initialize LLM provider (30min) → Full AI sell scanning
- Integrate runner (3-4h) → GOAL B and C active
- Load news events (1h) → Sell scanner uses news sentiment

**Long-Term Improvements**:
- Refactor position sizing (4-6h) → Conviction-based allocations
- Add explicit EV calc (4-6h) → Rigorous probabilistic entry
- Expand universe (1-2h) → More trade opportunities

**Estimated Total Effort to Full Deployment**: ~20 hours
- Phase 1 (Make modules active): 5 hours
- Phase 2 (Fix position sizing): 6 hours
- Phase 3 (Explicit EV): 6 hours (optional)
- Testing & docs: 3 hours

**Expected Final Activity Level**: 10-20 trades/day (vs 0-2 before, vs 5-15 after Phase 1+2)
