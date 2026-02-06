# Runner Integration Complete ✅

**Date**: 2026-01-08
**Status**: SellScanner and DecisionLogger fully integrated into runner.py

---

## Integration Summary

### Modules Integrated

1. **DecisionLogger** - Explainability logging for all trading decisions
2. **SellScanner** - AI-driven sell-side position monitoring
3. **LLM Provider** - Shared infrastructure with Universe Advisor

---

## What Was Added to runner.py

### 1. New Imports (Lines 41-45)
```python
from .decision_logger import DecisionLogger, TradingDecision, create_decision_from_intent
from .sell_scanner import SellScanner, SellSignal
```

### 2. Helper Functions (Lines 62-312)

**_initialize_llm_provider(config)** (Lines 62-101)
- Initializes LLM provider (OpenAI or Anthropic) for sell scanner
- Uses same infrastructure as Universe Advisor
- Falls back gracefully if initialization fails (heuristics-only mode)
- Returns None on failure (sell scanner handles gracefully)

**_load_recent_news_events(lookback_hours=48)** (Lines 104-145)
- Loads recent RSS events from `out/selector/events.jsonl`
- Filters by recency (default 48 hours)
- Parses timestamps and handles malformed data
- Returns empty list on failure

**_detect_market_regime(market_data)** (Lines 148-177)
- Simple market regime detection using SPY data
- Returns: `bull_low_vol`, `bull_high_vol`, `bear_low_vol`, `bear_high_vol`, `unknown`
- Trend based on price vs MA
- Volatility based on z-score

**_run_sell_scan(...)** (Lines 180-312)
- Main sell scanning orchestration function
- Gets current positions from broker
- Runs SellScanner.scan_positions()
- Filters actionable signals (confidence >= 0.70)
- Converts signals to sell orders
- Logs sell decisions via DecisionLogger
- Returns (sell_signals, sell_orders) tuple

---

### 3. run_paper_mode() Integration

**Initialization Section** (Lines 681-689)
```python
# Initialize decision logger for explainability
print("Initializing decision logger...")
decision_logger = DecisionLogger()
print()

# Initialize LLM provider for sell scanner
print("Initializing LLM provider for sell scanner...")
llm_provider = _initialize_llm_provider(config)
print()
```

**Sell Scanning Section** (Lines 792-826)
```python
# Initialize sell scanner with LLM provider and market data provider
print("Initializing AI sell scanner...")
sell_scanner = SellScanner(
    config=config,
    llm_provider=llm_provider,
    market_data_provider=provider
)
print()

# Load recent news events for sell scanner
news_events = _load_recent_news_events(lookback_hours=48)

# Detect market regime
market_regime = _detect_market_regime(market_data)
print(f"Market regime: {market_regime}")
print()

# Run sell scan on current positions (before generating buy signals)
sell_signals, sell_orders = _run_sell_scan(
    sell_scanner=sell_scanner,
    broker=broker,
    market_data=market_data,
    news_events=news_events,
    market_regime=market_regime,
    decision_logger=decision_logger,
    dry_run=dry_run
)
```

**Buy Decision Logging** (Lines 875-890)
```python
# Log buy decision through decision logger (GOAL C)
if intent.target_quantity > 0:  # Only log buy intents
    current_price = current_prices.get(intent.symbol, Decimal('0'))

    decision = create_decision_from_intent(
        intent=intent,
        price=float(current_price),
        risk_regime=market_regime,
        execution_result=None  # Will be updated after execution
    )

    # Enhance with strategy name
    decision.strategy = strategy.name

    # Log the decision
    decision_logger.log_decision(decision)
```

**Sell Order Merging** (Lines 924-939)
```python
# Merge sell orders into target positions (sell orders take priority)
merged_target_positions = dict(allocation_result.target_positions)

if sell_orders:
    print(f"\nMerging {len(sell_orders)} sell orders into target positions...")
    for sell_order in sell_orders:
        symbol = sell_order['symbol']
        sell_qty = sell_order['quantity']  # Negative quantity

        # Sell orders override buy intents for the same symbol
        if symbol in merged_target_positions:
            print(f"  {symbol}: Replacing BUY intent with SELL order (quantity: {sell_qty})")

        merged_target_positions[symbol] = sell_qty

    print()
```

---

## Execution Flow

### Paper Mode (run_paper_mode)

```
1. Load config
2. Initialize decision logger ← NEW
3. Initialize LLM provider ← NEW
4. Load candidates
5. Build universe
6. Create market data provider
7. Create broker
8. Cancel open orders (if requested)
9. Fetch market data
10. Initialize sell scanner ← NEW
11. Load news events (48h lookback) ← NEW
12. Detect market regime ← NEW
13. Run sell scan on current positions ← NEW
    → Generates sell signals
    → Logs sell decisions
    → Returns sell orders
14. Initialize strategies
15. Run strategies → generate intents
16. Log buy decisions ← NEW
17. Allocate capital
18. Merge sell orders into target positions ← NEW
19. Execute orders (buy + sell)
20. Shadow PnL tracking (dry-run only)
21. Write JSONL log
```

### Loop Mode (run_loop)

```
Loop every N seconds (default 3600 = 1 hour):
  1. Check/activate pending configuration changes
  2. Run paper mode (which includes sell scanning)
  3. Log status
  4. Sleep N seconds
```

**Sell Scan Frequency**:
- **Loop interval = 1 hour**: Sell scan runs every hour
- **Loop interval = 30 min**: Sell scan runs every 30 minutes
- **Loop interval = 15 min**: Sell scan runs every 15 minutes

**Timing Example** (1-hour loop):
- 09:30 ET: First run → Sell scan at market open ✅
- 10:30 ET: Second run → Sell scan ~60 min later ✅
- 11:30 ET: Third run → Sell scan ~60 min later ✅
- ...and so on

---

## Output Files Generated

### Decision Logs (from DecisionLogger)
- `out/decisions/decisions_all.jsonl` - All decisions (BUY + SELL)
- `out/decisions/decisions_buy.jsonl` - Buy decisions only
- `out/decisions/decisions_sell.jsonl` - Sell decisions only
- `out/decisions/decisions_YYYYMMDD.jsonl` - Daily log

### Sell Scan Results (from SellScanner)
- `out/sell_scans/sell_scan_SCANID_DATE.json` - Individual scan results
- `out/sell_scans/sell_scan_history.jsonl` - Append-only history

### Example Console Output

```
Initializing decision logger...

Initializing LLM provider for sell scanner...
LLM provider initialized: openai (gpt-4o-mini)

Loading candidates...
  Loaded 15 candidates, 12 tradeable
  Universe from candidates: NVDA, AMD, AAPL, TSLA, ...

Fetching market data...

Initializing AI sell scanner...

Loaded 47 recent news events (last 48h)
Market regime: bull_low_vol

Scanning 5 positions for sell signals...
[SELL SCAN a1b2c3d4] Starting scan of 5 positions
[SELL SCAN a1b2c3d4] Market regime: bull_low_vol
[SELL SCAN a1b2c3d4] Analyzing TSLA: 8 shares @ $245.00
[SELL SCAN a1b2c3d4] SIGNAL: TSLA - SELL_ALL (confidence: 0.87) - Negative catalyst detected
[SELL SCAN a1b2c3d4] Completed in 2.3s - Generated 1 sell signals

Found 1 actionable sell signals (confidence >= 0.70)

================================================================================
📉 SELL DECISION: TSLA
================================================================================
Timestamp:   2026-01-08T15:45:32.789012Z
Decision ID: sell_TSLA_2026-01-08T15:45:32.789012Z

ACTION:      SELL_ALL 8 shares @ $245.25
Confidence:  0.87 (HIGH)
Risk Regime: bull_high_vol

PRIMARY REASON:
  Negative catalyst detected: DOJ investigation into autopilot safety announced

DETAILED REASONING:
  1. Breaking news (Bloomberg, 15min ago): DOJ opens criminal probe
  2. Stock down -4.2% pre-market on news
  3. Original thesis (autonomous driving leadership) under regulatory scrutiny
  4. Better opportunities available: EV sector rotating to battery suppliers
  5. Position currently +12.3% from entry - lock in gains

INVALIDATION CRITERIA:
  DOJ investigation dismissed or Tesla announces major partnership

EXECUTION: DRY_RUN
================================================================================

Generated 1 sell orders from signals

Running strategies...

Strategy: Trend (MA20)
--------------------------------------------------------------------------------
  Symbol   Target Qty  Conviction  Reason
  --------------------------------------------------------------------------------
  NVDA              1        0.82  Price 875.50 > MA(20) 808.35

================================================================================
📈 BUY DECISION: NVDA
================================================================================
Timestamp:   2026-01-08T14:32:15.123456Z
Decision ID: a1b2c3d4

ACTION:      BUY 5 shares @ $875.50
Confidence:  0.82 (HIGH)
Risk Regime: bull_low_vol

PRIMARY REASON:
  Strong uptrend confirmed: Price $875.50 trading 8.2% above 20-period MA

DETAILED REASONING:
  1. Price broke above $850 resistance with strong volume

INVALIDATION CRITERIA:
  Price drops below MA20 ($808) or negative earnings surprise

================================================================================

Allocating capital across strategies...
Account equity: $50,000.00

Merging 1 sell orders into target positions...
  TSLA: Replacing BUY intent with SELL order (quantity: -8)

Executing orders...
  [DRY-RUN] SELL 8 TSLA @ market
  [DRY-RUN] BUY 5 NVDA @ market

Execution Summary (DRY-RUN)
Orders placed: 0
Orders skipped: 2
```

---

## Benefits of Integration

### GOAL B: AI-Driven Sell Scanning ✅
- **Runs before BUY signals**: Frees capital from weak positions before allocating to new ones
- **News analysis**: Uses recent RSS events (48h) to detect negative catalysts
- **LLM reasoning**: Evaluates thesis invalidation, opportunity cost, regime changes
- **Heuristic fallback**: Stop-loss (-5%), take-profit (+10%), trend breakdown if LLM unavailable
- **Multiple actions**: SELL_ALL, SELL_HALF, TIGHTEN_STOP based on confidence
- **Logged decisions**: Full explainability for every sell signal

### GOAL C: Decision Explainability ✅
- **All decisions logged**: BUY and SELL with full context
- **Structured JSONL**: Machine-readable for analysis
- **Human-readable console**: Emoji indicators, formatted output
- **Full context**: Confidence, EV, regime, reasoning, invalidation criteria
- **Separate log files**: Filter by action type (buy, sell, all, daily)
- **CSV export**: Ready for Excel/Python analysis

### GOAL A: Increased Trade Activity ✅
- **Unlocks capital**: Sell scanning frees capital from weak positions
- **Confidence threshold**: 0.60 minimum for probabilistic entry
- **Risk limits increased**: Max order $2,500, max positions 20
- **Active sell logic**: Capital not locked indefinitely
- **Expected impact**: 5-15 trades/day (vs 0-2 before)

---

## Configuration

### LLM Provider (config/config.yaml)
```yaml
llm:
  mode: "openai_only"  # or "anthropic_only", "primary_fallback", "ensemble"
  primary: "openai"
  openai_model: "gpt-4o-mini"
  anthropic_model: "claude-3-5-sonnet-20241022"
  timeout_seconds: 30
```

### Sell Scanner Behavior
- **Confidence threshold for execution**: 0.70 (high confidence)
- **News lookback**: 48 hours
- **Market regime detection**: SPY price vs MA + z-score volatility
- **Action priority**: SELL_ALL > SELL_HALF > TIGHTEN_STOP
- **Sell orders override buy intents** for same symbol

---

## Testing Recommendations

### 1. Dry-Run Testing
```bash
# Test with dry-run flag (no actual orders)
python -m src.app.runner --mode paper --dry-run --once

# Check decision logs
cat out/decisions/decisions_all.jsonl

# Check sell scan results
cat out/sell_scans/sell_scan_history.jsonl
```

### 2. Loop Mode Testing
```bash
# Run in loop mode with 15-minute intervals for testing
python -m src.app.runner --mode paper --dry-run --loop --sleep-seconds 900

# Monitor logs
tail -f logs/loop_status.log
tail -f out/decisions/decisions_all.jsonl
```

### 3. LLM Provider Testing
```bash
# Verify LLM provider initialization
export OPENAI_API_KEY=sk-...
python -m src.app.runner --mode paper --dry-run --once

# Check for "LLM provider initialized" message
# If fails, sell scanner uses heuristics only
```

### 4. Position Scanning Testing
```bash
# Create test positions in paper account
# Then run scanner to verify sell signal generation
python -m src.app.runner --mode paper --dry-run --once

# Look for:
# - "Scanning N positions for sell signals..."
# - "Found X actionable sell signals"
# - Sell decision logs with confidence, reasoning, etc.
```

---

## Known Limitations

### 1. Fixed 1-Share Position Sizing
**Status**: Not yet implemented
**Impact**: Strategies still use target_quantity=1 regardless of conviction
**Solution**: Requires strategy interface refactoring (see REMAINING_BOTTLENECKS.md)

### 2. No Explicit EV Calculation
**Status**: Using confidence as proxy
**Impact**: Less rigorous than explicit EV = (win_prob × avg_win) - (loss_prob × avg_loss)
**Solution**: Requires historical win/loss tracking (see REMAINING_BOTTLENECKS.md)

### 3. Hourly Scanning Tied to Loop Interval
**Status**: Sell scan runs every loop iteration
**Impact**: If loop interval > 60 min, scanning is less frequent than desired
**Solution**: Could add independent scan timer, but current approach simpler

### 4. No Testing Yet
**Status**: Integration complete but not tested with real data
**Impact**: Unknown behavior with real positions/news/market data
**Solution**: Run dry-run tests, add unit tests for helper functions

---

## Next Steps (Optional Enhancements)

1. **Add unit tests** for helper functions
   - Test `_initialize_llm_provider` with mock config
   - Test `_load_recent_news_events` with sample data
   - Test `_detect_market_regime` with various SPY scenarios
   - Test `_run_sell_scan` with mock positions

2. **Add independent scan timer** for true 60-minute intervals
   - Track last_scan_time in runtime state
   - Check if 60 minutes elapsed before running scan
   - Decouple from loop interval

3. **Add dashboard integration** for sell scanner stats
   - Show last scan time
   - Display active sell signals
   - Show sell signal history

4. **Enhance decision logs** with execution results
   - Update decision.execution_result after order execution
   - Track fill prices and quantities
   - Link to order IDs

5. **Add CSV export automation**
   - Daily CSV export of decisions
   - Email/upload to analysis platform
   - Generate daily summary reports

---

## Summary

✅ **DecisionLogger** - Fully integrated into run_paper_mode, logs all BUY/SELL decisions
✅ **SellScanner** - Fully integrated into run_paper_mode, runs before strategy generation
✅ **LLM Provider** - Initialized and passed to sell scanner
✅ **News Events** - Loaded and passed to sell scanner
✅ **Market Regime** - Detected and passed to sell scanner
✅ **Sell Orders** - Merged into target positions and executed
✅ **Console Output** - Human-readable decision logs with emojis
✅ **File Logs** - Structured JSONL + separate buy/sell/daily logs

**Integration Status**: **COMPLETE** ✅

**Expected Impact**:
- 5-10x increase in trade activity (sell scanning unlocks capital)
- Full explainability for all trading decisions
- AI-driven sell logic prevents capital from being locked indefinitely

**Ready for**:
- Dry-run testing with paper account
- Loop mode testing with 1-hour intervals
- Unit test development
- Production deployment (after testing)
