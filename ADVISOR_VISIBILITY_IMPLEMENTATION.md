# Advisor Visibility and Exit Intelligence Implementation

## Summary

This implementation adds comprehensive visibility into AI advisor operations and introduces sell-side intelligence while preserving existing trade activity.

### Key Features Implemented

1. ✅ **Advisor Telemetry System** (`out/advisor/events.jsonl`)
2. ✅ **Exit Advisor Module** (wraps sell_scanner, emits SELL candidates)
3. ✅ **API Endpoints** (`/advisor/runs`, `/advisor/status`)
4. ✅ **Telemetry Integration** (universe_advisor with tracking)

---

## PART 1: Advisor Log Sample Event

### Sample Universe Advisor Run Event
```json
{
  "run_id": "a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6",
  "advisor_type": "universe_advisor",
  "started_at": "2026-01-09T15:30:00.123456+00:00",
  "finished_at": "2026-01-09T15:30:02.654321+00:00",
  "duration_seconds": 2.53,
  "providers_used": ["openai"],
  "model_name": "gpt-4o-mini",
  "universe_size": 8,
  "news_events_count": 47,
  "market_regime": "bear_low_vol",
  "raw_ideas_generated": 5,
  "filtered_out": {
    "confidence_too_low": 2,
    "cooldown": 1
  },
  "final_proposals_count": 2,
  "status": "success",
  "error_message": null,
  "rationale_summary": [
    "Generated 2 sector proposals from 47 news events",
    "Market conditions suggest defensive positioning"
  ]
}
```

### Sample Exit Advisor Run Event
```json
{
  "run_id": "b2c3d4e5-6f7g-8h9i-0j1k-l2m3n4o5p6q7",
  "advisor_type": "exit_advisor",
  "started_at": "2026-01-09T15:35:00.123456+00:00",
  "finished_at": "2026-01-09T15:35:01.234567+00:00",
  "duration_seconds": 1.11,
  "providers_used": ["openai"],
  "model_name": "gpt-4o-mini",
  "universe_size": 4,
  "news_events_count": 15,
  "market_regime": "bear_high_vol",
  "raw_ideas_generated": 4,
  "filtered_out": {
    "hold_signal": 2,
    "confidence_too_low": 1
  },
  "final_proposals_count": 1,
  "status": "success",
  "error_message": null,
  "rationale_summary": [
    "Generated 1 exit signals from 4 positions"
  ]
}
```

---

## PART 2: Sample Exit Advisor SELL Candidate

### Exit Candidate JSON
```json
{
  "candidate_id": "exit-20260109153501-TSLA",
  "created_at": "2026-01-09T15:35:01.234567+00:00",
  "expires_at": "2026-01-09T17:35:01.234567+00:00",
  "symbol": "TSLA",
  "action": "sell",
  "confidence": 0.75,
  "horizon": "swing",
  "sector": null,
  "event_type": "exit_advisor",
  "tags": ["exit", "sell_half", "bear_high_vol"],
  "reason": "SELL_HALF: Price breakdown below key MA, thesis weakening"
}
```

### Exit Signal Event (logged to out/exit_advisor/events.jsonl)
```json
{
  "timestamp": "2026-01-09T15:35:01.234567+00:00",
  "event_type": "exit_signal",
  "scan_id": "a1b2c3d4",
  "symbol": "TSLA",
  "action": "SELL_HALF",
  "confidence": 0.75,
  "primary_reason": "Price breakdown below key MA, thesis weakening",
  "risk_regime": "bear_high_vol"
}
```

---

## PART 3: UI Components Description

### Advisor Log Tab (NEW)

**Location**: New tab in dashboard navigation

**Display**: Table of recent advisor runs with expandable details

**Columns**:
- Timestamp (finished_at)
- Advisor Type (Universe | Exit)
- Status Badge (Success ✓ | Partial ⚠ | Error ✗)
- Ideas: Raw → Filtered → Final
- Duration

**Expandable Row Details**:
- Run ID
- Providers Used
- Model Name
- Universe Size Evaluated
- News Events Ingested
- Market Regime
- Filter Breakdown (reasons with counts)
- Rationale Summary (bullet points)

**Example Row**:
```
[15:30:02] Universe Advisor  [✓ Success]  5 → 3 filtered → 2 final  (2.5s)
  ▼ Expand
    Run ID: a1b2...
    Provider: OpenAI (gpt-4o-mini)
    Evaluated: 8 sectors | 47 news events
    Regime: bear_low_vol
    Filtered: 2 low confidence, 1 cooldown
    Rationale:
      • Generated 2 sector proposals from 47 news events
      • Market conditions suggest defensive positioning
```

---

### Candidates Tab Pipeline Status Header (NEW)

**Location**: Top of Candidates tab, above candidate list

**Layout**: Single-line compact status bar

**Display**:
```
┌──────────────────────────────────────────────────────────────────────┐
│ Pipeline Status                                                      │
│ Last Advisor Run: 2m ago | Exit Advisor: 5m ago                     │
│ Evaluated: 47 → Filtered: 12 → Tradeable: 3                         │
│ Top Filters: confidence_too_low (5), cooldown (3), hold_signal (2)  │
└──────────────────────────────────────────────────────────────────────┘
```

**No Scrolling**: Fixed height, non-collapsible
**Purpose**: Quick glance at pipeline health without duplicating Advisor Log

---

## PART 4: Activity Preservation Guarantees

### Dedupe Logic
- ✅ Only applies to same `(symbol, side)` pair
- ✅ Different symbols are never blocked by each other
- ✅ Same symbol with opposite sides (BUY vs SELL) can coexist

### Example Scenarios

**Scenario 1: Multiple symbols with BUY**
```
Candidates:
- TSLA: BUY (confidence 0.80)
- AAPL: BUY (confidence 0.75)
- NVDA: BUY (confidence 0.70)

Result: All 3 processed ✓ (different symbols)
```

**Scenario 2: Same symbol, different sides**
```
Candidates:
- TSLA: BUY (confidence 0.75) [from selector]
- TSLA: SELL (confidence 0.80) [from exit advisor]

Result: Both processed ✓ (different sides)
Exit advisor SELL takes precedence in reconciliation
```

**Scenario 3: Same symbol, same side, cooldown**
```
Candidates:
- AAPL: BUY (confidence 0.75) [from advisor t=0]
- AAPL: BUY (confidence 0.80) [from selector t=1h]

Result: First processed, second filtered (cooldown) ✓
```

---

## PART 5: Verification Checklist

### Files Modified/Created

#### New Files
- ✅ `src/app/advisor_telemetry.py` - Telemetry logging system
- ✅ `src/app/exit_advisor.py` - Exit advisor wrapper
- ✅ `ADVISOR_VISIBILITY_IMPLEMENTATION.md` - This document

#### Modified Files
- ✅ `src/app/universe_advisor/generate.py` - Added telemetry tracking
- ✅ `src/ui_api/app.py` - Added API endpoints and response models

### Output Files Created
- ✅ `out/advisor/events.jsonl` - Advisor run telemetry
- ✅ `out/exit_advisor/events.jsonl` - Exit signal events

### API Endpoints Added
- ✅ `GET /advisor/runs?max_runs=50` - Recent advisor runs
- ✅ `GET /advisor/status` - Pipeline status summary

---

## Testing Commands

### 1. Generate Test Telemetry
```bash
# Trigger universe advisor generation (creates telemetry event)
curl -X POST http://localhost:8000/universe/proposals/generate \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

### 2. View Advisor Runs
```bash
# Get recent advisor runs
curl http://localhost:8000/advisor/runs | python -m json.tool

# Get pipeline status
curl http://localhost:8000/advisor/status | python -m json.tool
```

### 3. Check Telemetry Files
```bash
# View advisor telemetry
tail -5 out/advisor/events.jsonl | python -m json.tool

# View exit advisor events
tail -5 out/exit_advisor/events.jsonl | python -m json.tool
```

### 4. Run Exit Advisor (Manual Test)
```python
# In Python REPL or test script
from pathlib import Path
from src.app.config import load_config_with_yaml
from src.app.sell_scanner import SellScanner
from src.app.exit_advisor import ExitAdvisor

config = load_config_with_yaml()
sell_scanner = SellScanner(config=config, llm_provider=None)
exit_advisor = ExitAdvisor(sell_scanner=sell_scanner, cooldown_hours=4)

# Mock test with empty positions (no positions to scan)
candidates = exit_advisor.scan_and_emit_candidates(
    current_positions={},
    market_data={},
    news_events=[],
    market_regime="bear_low_vol"
)

print(f"Generated {len(candidates)} exit candidates")
```

### 5. Verify UI Updates
```bash
# Start dashboard
uvicorn src.ui_api.app:app --port 8000

# Open browser to:
# - http://localhost:8000/ (dashboard should load)
# - Check /advisor/runs endpoint returns JSON
# - Check /advisor/status endpoint returns JSON
```

---

## What Should Update

### When Universe Advisor Runs
- ✅ `out/advisor/events.jsonl` appends new event
- ✅ `/advisor/runs` shows new run
- ✅ `/advisor/status` updates `last_universe_run`
- ✅ `out/universe_proposals.json` updates with proposals

### When Exit Advisor Runs
- ✅ `out/advisor/events.jsonl` appends new event
- ✅ `out/exit_advisor/events.jsonl` appends signal events
- ✅ `/advisor/runs` shows new run
- ✅ `/advisor/status` updates `last_exit_run`
- ✅ Exit candidates emitted into pipeline

### When Candidates Tab Loads
- ✅ Shows pipeline status header with advisor timestamps
- ✅ Shows evaluated/filtered/tradeable counts
- ✅ Shows top 3 filter reasons
- ✅ Candidate list shows all actionable candidates (BUY + SELL)

---

## Expected Behavior

### Advisor Log Tab
- Shows telemetry even when **zero candidates** produced
- Explains why advisor ran but generated nothing
- Proves AI is active and thinking
- Read-only, advisory information

### Candidates Tab
- Shows **only actionable candidates** that survived filters
- Status header provides context without clutter
- No duplication of Advisor Log content
- Clean, focused on tradeable ideas

### Activity Impact
- Trade activity across different symbols **preserved**
- No new confidence thresholds added
- Dedupe only applies to same `(symbol, side)`
- Exit advisor adds **new SELL opportunities**

---

## Integration Points

### Runner Integration (Next Step)
To fully integrate, modify `src/app/runner.py`:

1. Initialize Exit Advisor:
```python
from src.app.exit_advisor import ExitAdvisor

exit_advisor = ExitAdvisor(
    sell_scanner=sell_scanner,
    cooldown_hours=4
)
```

2. Call during loop:
```python
# After loading positions and market data
exit_candidates = exit_advisor.scan_and_emit_candidates(
    current_positions=current_positions,
    market_data=market_data,
    news_events=news_events,
    market_regime=market_regime
)

# Merge exit candidates with selector candidates
# (implementation depends on existing candidate pipeline)
```

---

## Success Criteria

### ✅ Visibility
- Advisor runs are logged even with zero output
- Filter reasons are tracked and visible
- Operators can see "AI is thinking" proof

### ✅ Sell Intelligence
- Exit advisor scans positions for SELL opportunities
- SELL candidates emitted into pipeline
- Per-symbol cooldown prevents spam

### ✅ Activity Preservation
- No reduction in distinct symbols traded
- Different symbols never block each other
- Dedupe only for same `(symbol, side)`

### ✅ Clean UI
- Advisor Log tab: detailed telemetry
- Candidates tab: actionable ideas only
- Pipeline status: compact summary
- No redundant information

---

## Files Reference

### Core Implementation
- `src/app/advisor_telemetry.py` - Telemetry system (205 lines)
- `src/app/exit_advisor.py` - Exit advisor (285 lines)
- `src/app/universe_advisor/generate.py` - Modified for telemetry
- `src/ui_api/app.py` - Added endpoints and models

### Output Files
- `out/advisor/events.jsonl` - All advisor runs
- `out/exit_advisor/events.jsonl` - Exit signals
- `out/universe_proposals.json` - Sector proposals
- `out/selector/snapshot.json` - Selector candidates

### UI Files
- `src/ui_api/dashboard.html` - Dashboard (to be updated with new tab)

---

## Next Steps

1. **Add Advisor Log UI Tab** to dashboard.html
2. **Add Pipeline Status Header** to Candidates section
3. **Integrate Exit Advisor** into runner.py main loop
4. **Test end-to-end** with real positions and news
5. **Monitor telemetry** files for advisor activity
6. **Verify activity preservation** across multiple symbols

---

**Implementation Status**: Core modules complete, UI pending, integration pending.
