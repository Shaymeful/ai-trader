# Example Decision Logs

This document shows example outputs from the new DecisionLogger and SellScanner modules.

---

## Example 1: BUY Decision (Human-Readable Console Output)

```
================================================================================
📈 BUY DECISION: NVDA
================================================================================
Timestamp:   2026-01-08T14:32:15.123456Z
Decision ID: a1b2c3d4

ACTION:      BUY 5 shares @ $875.50
Confidence:  0.82 (HIGH)
Risk Regime: bull_low_vol

Expected Value: $245.00
Strategy:    Trend_MA20

PRIMARY REASON:
  Strong uptrend confirmed: Price $875.50 trading 8.2% above 20-period MA

DETAILED REASONING:
  1. Price broke above $850 resistance with strong volume (2.5x avg)
  2. Tech sector showing relative strength vs SPY (+3.2% vs +1.1% this week)
  3. Positive news catalyst: AI chip demand exceeds supply (Reuters, 2h ago)
  4. RSI at 62 (not overbought, room to run)
  5. Conviction score 0.82 based on trend strength and momentum alignment

SUPPORTING DATA:
  current_price: 875.50
  ma_20: 808.35
  zscore: 1.45
  volume_ratio: 2.51
  sector_relative_strength: 3.18

INVALIDATION CRITERIA:
  Price drops below MA20 ($808) or negative earnings surprise or sector rotation out of tech

EXECUTION: EXECUTED
================================================================================
```

**Structured JSON Log** (from decisions_all.jsonl):
```json
{
  "decision_id": "a1b2c3d4",
  "timestamp": "2026-01-08T14:32:15.123456Z",
  "symbol": "NVDA",
  "action": "BUY",
  "quantity": 5,
  "price": 875.50,
  "confidence": 0.82,
  "expected_value": 245.00,
  "risk_regime": "bull_low_vol",
  "strategy": "Trend_MA20",
  "primary_reason": "Strong uptrend confirmed: Price $875.50 trading 8.2% above 20-period MA",
  "detailed_reasoning": [
    "Price broke above $850 resistance with strong volume (2.5x avg)",
    "Tech sector showing relative strength vs SPY (+3.2% vs +1.1% this week)",
    "Positive news catalyst: AI chip demand exceeds supply (Reuters, 2h ago)",
    "RSI at 62 (not overbought, room to run)",
    "Conviction score 0.82 based on trend strength and momentum alignment"
  ],
  "supporting_data": {
    "current_price": 875.50,
    "ma_20": 808.35,
    "zscore": 1.45,
    "volume_ratio": 2.51,
    "sector_relative_strength": 3.18
  },
  "invalidation_criteria": "Price drops below MA20 ($808) or negative earnings surprise or sector rotation out of tech",
  "position_context": null,
  "execution_result": "EXECUTED"
}
```

---

## Example 2: SELL Decision from AI Sell Scanner (Negative Catalyst)

```
================================================================================
📉 SELL DECISION: TSLA
================================================================================
Timestamp:   2026-01-08T15:45:32.789012Z
Decision ID: e5f6g7h8

ACTION:      SELL 8 shares @ $245.25
Confidence:  0.87 (HIGH)
Risk Regime: bull_high_vol

Expected Value: -$180.00
Strategy:    SellScanner

PRIMARY REASON:
  Negative catalyst detected: DOJ investigation into autopilot safety announced

DETAILED REASONING:
  1. Breaking news (Bloomberg, 15min ago): DOJ opens criminal probe into autopilot claims
  2. Stock down -4.2% pre-market on news, likely to continue on market open
  3. Original thesis (autonomous driving leadership) now under regulatory scrutiny
  4. Better opportunities available: EV sector rotating to battery suppliers (ALBM +8.5%)
  5. Position currently +12.3% from entry ($218.50) - lock in gains before further downside

SUPPORTING DATA:
  entry_price: 218.50
  current_price: 245.25
  pnl_pct: 12.25
  news_sentiment: -0.85
  headline_count: 3
  sector_performance_vs_spy: -2.10

INVALIDATION CRITERIA:
  DOJ investigation dismissed or Tesla announces major partnership to offset news

EXECUTION: EXECUTED
================================================================================
```

**Structured JSON Log**:
```json
{
  "decision_id": "e5f6g7h8",
  "timestamp": "2026-01-08T15:45:32.789012Z",
  "symbol": "TSLA",
  "action": "SELL",
  "quantity": 8,
  "price": 245.25,
  "confidence": 0.87,
  "expected_value": -180.00,
  "risk_regime": "bull_high_vol",
  "strategy": "SellScanner",
  "primary_reason": "Negative catalyst detected: DOJ investigation into autopilot safety announced",
  "detailed_reasoning": [
    "Breaking news (Bloomberg, 15min ago): DOJ opens criminal probe into autopilot claims",
    "Stock down -4.2% pre-market on news, likely to continue on market open",
    "Original thesis (autonomous driving leadership) now under regulatory scrutiny",
    "Better opportunities available: EV sector rotating to battery suppliers (ALBM +8.5%)",
    "Position currently +12.3% from entry ($218.50) - lock in gains before further downside"
  ],
  "supporting_data": {
    "entry_price": 218.50,
    "current_price": 245.25,
    "pnl_pct": 12.25,
    "news_sentiment": -0.85,
    "headline_count": 3,
    "sector_performance_vs_spy": -2.10
  },
  "invalidation_criteria": "DOJ investigation dismissed or Tesla announces major partnership to offset news",
  "position_context": {
    "quantity": 8,
    "avg_entry_price": 218.50,
    "current_value": 1962.00,
    "unrealized_pnl": 214.00,
    "holding_period_days": 12
  },
  "execution_result": "EXECUTED"
}
```

---

## Example 3: SELL_HALF Decision (Take Profit + Opportunity Cost)

```
================================================================================
📉 SELL_HALF DECISION: AAPL
================================================================================
Timestamp:   2026-01-08T16:22:10.456789Z
Decision ID: i9j0k1l2

ACTION:      SELL_HALF 6 shares @ $195.80
Confidence:  0.73 (MEDIUM)
Risk Regime: bull_low_vol

Expected Value: $320.00
Strategy:    SellScanner

PRIMARY REASON:
  Take profit at +15.2% and redeploy to higher-conviction opportunities

DETAILED REASONING:
  1. Position up +15.2% from entry ($170.00), approaching typical resistance zone
  2. Tech sector showing early signs of profit-taking (QQQ -0.8% today)
  3. Better opportunity cost: Automation sector candidates showing 0.85+ confidence
  4. Trim 50% to lock gains while maintaining exposure if uptrend continues
  5. Relative performance flattening: AAPL +1.1% vs SPY +1.3% this week

SUPPORTING DATA:
  entry_price: 170.00
  current_price: 195.80
  pnl_pct: 15.18
  ma_20: 190.50
  price_vs_ma: 2.78
  qqq_performance_today: -0.82

INVALIDATION CRITERIA:
  Price breaks above $200 with volume or new product launch announcement

EXECUTION: EXECUTED
================================================================================
```

**Structured JSON Log**:
```json
{
  "decision_id": "i9j0k1l2",
  "timestamp": "2026-01-08T16:22:10.456789Z",
  "symbol": "AAPL",
  "action": "SELL_HALF",
  "quantity": 6,
  "price": 195.80,
  "confidence": 0.73,
  "expected_value": 320.00,
  "risk_regime": "bull_low_vol",
  "strategy": "SellScanner",
  "primary_reason": "Take profit at +15.2% and redeploy to higher-conviction opportunities",
  "detailed_reasoning": [
    "Position up +15.2% from entry ($170.00), approaching typical resistance zone",
    "Tech sector showing early signs of profit-taking (QQQ -0.8% today)",
    "Better opportunity cost: Automation sector candidates showing 0.85+ confidence",
    "Trim 50% to lock gains while maintaining exposure if uptrend continues",
    "Relative performance flattening: AAPL +1.1% vs SPY +1.3% this week"
  ],
  "supporting_data": {
    "entry_price": 170.00,
    "current_price": 195.80,
    "pnl_pct": 15.18,
    "ma_20": 190.50,
    "price_vs_ma": 2.78,
    "qqq_performance_today": -0.82
  },
  "invalidation_criteria": "Price breaks above $200 with volume or new product launch announcement",
  "position_context": {
    "quantity": 12,
    "avg_entry_price": 170.00,
    "current_value": 2349.60,
    "unrealized_pnl": 309.60,
    "holding_period_days": 8
  },
  "execution_result": "EXECUTED"
}
```

---

## Example 4: SELL_ALL Decision (Stop-Loss Triggered)

```
================================================================================
📉 SELL DECISION: META
================================================================================
Timestamp:   2026-01-08T10:15:45.234567Z
Decision ID: m3n4o5p6

ACTION:      SELL 4 shares @ $445.50
Confidence:  0.92 (VERY HIGH)
Risk Regime: bear_high_vol

Expected Value: -$125.00
Strategy:    SellScanner

PRIMARY REASON:
  Stop-loss triggered: Position down -6.8% from entry, cut losses

DETAILED REASONING:
  1. Position breached -5% stop-loss threshold (currently -6.8% from $478.00 entry)
  2. Trend breakdown: Price dropped below MA20 ($465) two sessions ago
  3. News headwind: EU regulatory fines announced ($1.2B, FT 24h ago)
  4. Market regime shifted from bull_low_vol to bear_high_vol (VIX spike to 28)
  5. No signs of reversal: RSI at 32 (oversold but no bounce yet)

SUPPORTING DATA:
  entry_price: 478.00
  current_price: 445.50
  pnl_pct: -6.80
  ma_20: 465.00
  price_vs_ma: -4.19
  rsi: 32.15
  vix: 28.40

INVALIDATION CRITERIA:
  Price recovers above MA20 ($465) with strong volume or regulatory news reversal

EXECUTION: EXECUTED
================================================================================
```

**Structured JSON Log**:
```json
{
  "decision_id": "m3n4o5p6",
  "timestamp": "2026-01-08T10:15:45.234567Z",
  "symbol": "META",
  "action": "SELL_ALL",
  "quantity": 4,
  "price": 445.50,
  "confidence": 0.92,
  "expected_value": -125.00,
  "risk_regime": "bear_high_vol",
  "strategy": "SellScanner",
  "primary_reason": "Stop-loss triggered: Position down -6.8% from entry, cut losses",
  "detailed_reasoning": [
    "Position breached -5% stop-loss threshold (currently -6.8% from $478.00 entry)",
    "Trend breakdown: Price dropped below MA20 ($465) two sessions ago",
    "News headwind: EU regulatory fines announced ($1.2B, FT 24h ago)",
    "Market regime shifted from bull_low_vol to bear_high_vol (VIX spike to 28)",
    "No signs of reversal: RSI at 32 (oversold but no bounce yet)"
  ],
  "supporting_data": {
    "entry_price": 478.00,
    "current_price": 445.50,
    "pnl_pct": -6.80,
    "ma_20": 465.00,
    "price_vs_ma": -4.19,
    "rsi": 32.15,
    "vix": 28.40
  },
  "invalidation_criteria": "Price recovers above MA20 ($465) with strong volume or regulatory news reversal",
  "position_context": {
    "quantity": 4,
    "avg_entry_price": 478.00,
    "current_value": 1782.00,
    "unrealized_pnl": -130.00,
    "holding_period_days": 5
  },
  "execution_result": "EXECUTED"
}
```

---

## Example 5: BUY Decision (Lower Confidence, Probabilistic Entry)

```
================================================================================
📈 BUY DECISION: AMD
================================================================================
Timestamp:   2026-01-08T13:18:22.567890Z
Decision ID: q7r8s9t0

ACTION:      BUY 3 shares @ $165.25
Confidence:  0.63 (MEDIUM)
Risk Regime: bull_low_vol

Expected Value: $48.00
Strategy:    MeanRev_Z1.0

PRIMARY REASON:
  Mean reversion setup: Oversold z-score (-1.42) with positive expected value

DETAILED REASONING:
  1. Z-score at -1.42 suggests 2-3 day bounce opportunity (historical 68% win rate)
  2. News catalyst: AMD announces new data center chip partnership (seeking alpha, 1h ago)
  3. Semiconductor sector rotation in progress (SMH +2.3% today)
  4. Price near 15-period MA support ($162.50), 1.7% below current price
  5. Probabilistic entry: Confidence 0.63 (above 0.60 threshold), EV positive at +$48

SUPPORTING DATA:
  current_price: 165.25
  ma_15: 162.50
  zscore: -1.42
  sector_performance_today: 2.31
  historical_winrate_zscore_below_neg1: 0.68
  expected_bounce_pct: 3.20

INVALIDATION CRITERIA:
  Z-score drops below -2.0 (extreme oversold) or semiconductor sector reverses

EXECUTION: EXECUTED
================================================================================
```

**Structured JSON Log**:
```json
{
  "decision_id": "q7r8s9t0",
  "timestamp": "2026-01-08T13:18:22.567890Z",
  "symbol": "AMD",
  "action": "BUY",
  "quantity": 3,
  "price": 165.25,
  "confidence": 0.63,
  "expected_value": 48.00,
  "risk_regime": "bull_low_vol",
  "strategy": "MeanRev_Z1.0",
  "primary_reason": "Mean reversion setup: Oversold z-score (-1.42) with positive expected value",
  "detailed_reasoning": [
    "Z-score at -1.42 suggests 2-3 day bounce opportunity (historical 68% win rate)",
    "News catalyst: AMD announces new data center chip partnership (seeking alpha, 1h ago)",
    "Semiconductor sector rotation in progress (SMH +2.3% today)",
    "Price near 15-period MA support ($162.50), 1.7% below current price",
    "Probabilistic entry: Confidence 0.63 (above 0.60 threshold), EV positive at +$48"
  ],
  "supporting_data": {
    "current_price": 165.25,
    "ma_15": 162.50,
    "zscore": -1.42,
    "sector_performance_today": 2.31,
    "historical_winrate_zscore_below_neg1": 0.68,
    "expected_bounce_pct": 3.20
  },
  "invalidation_criteria": "Z-score drops below -2.0 (extreme oversold) or semiconductor sector reverses",
  "position_context": null,
  "execution_result": "EXECUTED"
}
```

---

## Example 6: Decision Batch Summary

```json
{
  "batch_id": "batch_20260108_1430",
  "timestamp": "2026-01-08T14:30:00.000000Z",
  "iteration_number": 42,
  "market_regime": "bull_low_vol",
  "total_decisions": 8,
  "buy_count": 3,
  "sell_count": 4,
  "hold_count": 1,
  "decisions": [
    {
      "decision_id": "a1b2c3d4",
      "symbol": "NVDA",
      "action": "BUY",
      "confidence": 0.82,
      "primary_reason": "Strong uptrend confirmed: Price $875.50 trading 8.2% above 20-period MA"
    },
    {
      "decision_id": "e5f6g7h8",
      "symbol": "TSLA",
      "action": "SELL",
      "confidence": 0.87,
      "primary_reason": "Negative catalyst detected: DOJ investigation into autopilot safety announced"
    },
    {
      "decision_id": "i9j0k1l2",
      "symbol": "AAPL",
      "action": "SELL_HALF",
      "confidence": 0.73,
      "primary_reason": "Take profit at +15.2% and redeploy to higher-conviction opportunities"
    }
  ]
}
```

**Console Output**:
```
[DECISION BATCH batch_20260108_1430] Logged 8 decisions: 3 BUY, 4 SELL, 1 HOLD
```

---

## Example 7: Daily Summary Report

**Generated via**: `decision_logger.generate_summary_report(start_date="2026-01-08")`

```json
{
  "date_range": "2026-01-08 to 2026-01-08",
  "total_decisions": 23,
  "buy_count": 8,
  "sell_count": 12,
  "hold_count": 3,
  "avg_confidence": 0.742,
  "avg_buy_confidence": 0.768,
  "avg_sell_confidence": 0.823,
  "symbols_traded": [
    "NVDA", "TSLA", "AAPL", "AMD", "META", "GOOGL", "MSFT", "SPY", "QQQ", "XLE"
  ],
  "unique_symbols": 10
}
```

---

## File Locations

**All decision logs saved to**:
- `out/decisions/decisions_all.jsonl` - All decisions (append-only)
- `out/decisions/decisions_buy.jsonl` - Buy decisions only
- `out/decisions/decisions_sell.jsonl` - Sell decisions only
- `out/decisions/decisions_20260108.jsonl` - Daily log
- `out/decisions/batch_*.json` - Batch summaries

**Sell scan results saved to**:
- `out/sell_scans/sell_scan_SCANID_DATE.json` - Individual scans
- `out/sell_scans/sell_scan_history.jsonl` - Append-only history

---

## Key Features Demonstrated

### BUY Decisions:
- ✅ Full context (price, confidence, regime, strategy)
- ✅ Detailed reasoning (3-5 bullet points)
- ✅ Supporting data (indicators, market conditions)
- ✅ Invalidation criteria (what would reverse decision)
- ✅ Expected value estimate
- ✅ Confidence labels (VERY HIGH, HIGH, MEDIUM, LOW)

### SELL Decisions:
- ✅ Trigger identification (stop-loss, take-profit, catalyst, opportunity cost)
- ✅ Position context (entry price, PnL%, holding period)
- ✅ News analysis (headlines, sentiment)
- ✅ Regime change detection (bull → bear)
- ✅ Partial exit support (SELL_HALF for profit-taking)
- ✅ Human-readable with emoji indicators (📈 BUY, 📉 SELL, ✂️ TRIM)

### Probabilistic Entry:
- ✅ Confidence ≥0.60 accepted (not just ≥0.75)
- ✅ Explicit EV calculation shown
- ✅ Historical win rate referenced
- ✅ Risk/reward ratio documented

### Compliance:
- ✅ **GOAL C**: Every decision logged with full explainability
- ✅ **GOAL B**: AI-driven sell signals with LLM reasoning
- ✅ **GOAL A**: Lower confidence threshold enables more activity
- ✅ Structured (JSON) + Human-readable formats
- ✅ Audit trail maintained (append-only logs)
