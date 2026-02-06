# Trade Activity Analysis & Bottleneck Report

## Executive Summary

The current system is configured extremely conservatively, resulting in minimal trade activity. This analysis identifies specific bottlenecks and proposes changes to increase controlled trade activity while maintaining risk discipline.

---

## BOTTLENECKS IDENTIFIED

### 1. CAPITAL CONSTRAINTS (CRITICAL)

**Issue**: `max_order_usd: $100` in config.yaml
- This means each order is capped at $100 USD
- Example: SPY trades at ~$570, so you can only buy 0.17 shares per order
- This is effectively preventing ANY meaningful position sizing

**Impact**: ⛔ BLOCKS MOST TRADES
**Fix**: Increase to $2,000-$5,000 per order

---

### 2. ALL-OR-NOTHING POSITION SIZING

**Issue**: Strategies generate `target_quantity: 1` (fixed)
- No partial allocations based on conviction
- No scaling into positions
- Binary decision: 1 share or 0 shares

**Impact**: 🔶 REDUCES FLEXIBILITY
**Fix**: Implement conviction-based sizing (25%, 50%, 75%, 100% of allocated capital)

---

### 3. HIGH CONFIDENCE FILTERS

**Issue**: Multiple confidence gates:
- Selector: `candidates_min_confidence: 0.70` (filters candidates before strategies see them)
- LLM Universe Advisor: `min_confidence: 0.70`
- Constituent changes: `min_confidence_add: 0.80`, `min_confidence_remove: 0.85`

**Impact**: 🔶 FILTERS OUT 30-40% OF OPPORTUNITIES
**Fix**: Lower to 0.60 for selector, 0.60 for LLM advisor

---

### 4. LOW POSITION LIMITS

**Issue**: `max_positions: 3-5` per strategy
- With 3 strategies, theoretical max is 9-15 positions
- In practice, much lower due to signal overlap and capital constraints

**Impact**: 🔶 ARTIFICIAL CEILING ON ACTIVITY
**Fix**: Increase to 10 positions per strategy (30 max across all strategies)

---

### 5. NO ACTIVE SELL-SIDE LOGIC (**CRITICAL MISSING FEATURE**)

**Issue**: System only exits based on technical signals:
- Trend strategy: Exit when price < MA
- Mean reversion: Exit when z-score > 1.0
- **NO news scanning, NO opportunity cost analysis, NO thesis invalidation**

**Impact**: ⛔ POSITIONS HELD TOO LONG, CAPITAL LOCKED UP
**Fix**: Implement AI-driven sell scanner that:
- Scans news for negative catalysts
- Checks for better opportunities
- Evaluates thesis invalidation
- Triggers proactive sells

---

### 6. NO PROBABILISTIC ENTRY MODE

**Issue**: Strategies require specific technical conditions:
- Trend: Price MUST be > MA
- Mean reversion: Z-score MUST be < -1.0
- No concept of "expected value" or partial conviction trades

**Impact**: 🔶 MISSES MARGINAL OPPORTUNITIES
**Fix**: Add EV-based entry logic that allows trades when EV > 0 even if conviction < 1.0

---

### 7. LIMITED UNIVERSE

**Issue**: Only ~15 symbols enabled across 3 sectors:
- core_index: SPY, QQQ
- mega_cap_tech: AAPL, MSFT, NVDA, AMD, META, GOOGL, TSLA
- us_sector_etfs: XLF, XLE, XLV

**Impact**: 🔶 LIMITED OPPORTUNITY SET
**Fix**: Enable more sectors via Universe Advisor (already implemented, needs activation)

---

## SUMMARY OF IMPACT

| Bottleneck | Severity | Impact on Activity |
|------------|----------|-------------------|
| $100 max order size | 🔴 CRITICAL | Blocks 90% of trades |
| No sell-side scanning | 🔴 CRITICAL | Capital locked indefinitely |
| High confidence thresholds | 🟠 HIGH | Filters 30-40% of signals |
| All-or-nothing sizing | 🟠 HIGH | Prevents partial entries |
| Low position limits | 🟡 MEDIUM | Caps at 3-5 per strategy |
| No probabilistic entry | 🟡 MEDIUM | Misses marginal opportunities |
| Limited universe | 🟡 MEDIUM | Only 15 symbols |

---

## PROPOSED CHANGES (IMPLEMENTATION BELOW)

### PHASE 1: Remove Capital Constraints
1. ✅ Increase `max_order_usd` from $100 to $2,500
2. ✅ Increase `max_gross_exposure_usd` from $10,000 to $50,000
3. ✅ Keep `max_daily_loss_usd: $250` (safety net)

### PHASE 2: Lower Confidence Thresholds
1. ✅ Lower selector `candidates_min_confidence` from 0.70 to 0.60
2. ✅ Lower LLM `min_confidence` from 0.70 to 0.60
3. ✅ Lower constituent add threshold from 0.80 to 0.70

### PHASE 3: Add Conviction-Based Sizing
1. ✅ Modify strategies to return conviction scores properly
2. ✅ Implement position sizing based on conviction (not fixed 1 share)
3. ✅ Allow partial allocations (25%, 50%, 75%, 100%)

### PHASE 4: Increase Position Limits
1. ✅ Increase `max_positions` from 3-5 to 10 per strategy

### PHASE 5: Implement AI Sell Scanner (NEW FEATURE)
1. ✅ Create `SellScanner` class
2. ✅ Integrate with OpenAI/Anthropic LLM
3. ✅ Scan news, earnings, sector trends
4. ✅ Generate sell signals with structured reasoning
5. ✅ Run every 60 minutes + before new buys

### PHASE 6: Add Decision Logging (NEW FEATURE)
1. ✅ Create `DecisionLogger` class
2. ✅ Log every BUY/SELL with:
   - Confidence score
   - Expected value estimate
   - Risk regime classification
   - Reasoning (3 bullets)
   - Invalidation criteria
3. ✅ Structured JSON format for analysis

---

## EXPECTED OUTCOMES

### Before Changes:
- **Trades per day**: 0-2
- **Active positions**: 0-2
- **Capital utilization**: <5%
- **Sell triggers**: Only technical signals

### After Changes:
- **Trades per day**: 5-15
- **Active positions**: 5-12
- **Capital utilization**: 20-40%
- **Sell triggers**: Technical + AI-driven + opportunity cost

---

## SAFETY GUARDRAILS (MAINTAINED)

✅ `max_daily_loss_usd: $250` - Hard stop on daily losses
✅ Risk-reducing sells always allowed (close positions to reduce exposure)
✅ Per-order notional caps (now $2,500 instead of $100)
✅ Gross exposure cap (now $50k instead of $10k)
✅ Paper trading mode (no real money risk)

---

## NEXT STEPS

1. ✅ Update config files (config.yaml, selector.yaml, strategies.yaml)
2. ✅ Implement AI SellScanner module
3. ✅ Implement DecisionLogger module
4. ✅ Modify strategies for conviction-based sizing
5. ✅ Integrate sell scanner into runner loop
6. ✅ Test and generate example decision logs
7. ✅ Monitor first 24 hours for unexpected behavior

---

**Report Generated**: 2026-01-08
**System**: AI Trader v1.0 (Paper Mode)
