# Order Frequency Diagnosis - 2026-02-23

## Problem Statement
Loop running every 10-14 minutes but placing 0 orders since 11:19 AM.
Last orders: 11:19 AM (1), 11:05 AM (2), 10:56 AM (4).

## Root Causes Identified

### 1. RSS Selector Candidate Starvation
**File**: `src/app/selector/rss_selector.py:385-500` (`process_headline()`)

**Evidence**:
- Input: 85 headlines processed
- Created: 4 candidates (ESA, TMMC, FLT:CA, D, IDYA)
- Filtered: All 4 rejected by `src/app/candidates/store.py:get_tradeable_candidates()`
- Output: 0 tradeable candidates

**Why candidates fail**:
- Non-US/invalid tickers (ESA=European Space Agency, TMMC=Toyota Canada, FLT:CA=Canadian)
- Most are WATCH action (only BUY/SELL are tradeable per `is_tradeable()` check)

### 2. Execution Gate Blocking Energy Stocks
**File**: `src/app/execution/tradability_filter.py` + `config/modes.yaml:184-185`

**Blocks (from logs)**:
- FSLR: $235-242 (blocked, max_price=$150)
- BE: $152-153 (blocked, max_price=$150)
- PLUG: $1.84-1.88 (blocked, min_price=$5)

**Config source**: `config/modes.yaml` aggressive_small_mid_sentiment:
```yaml
execution_gate:
  min_price: 5.00
  max_price: 150.00
```

### 3. AI Copilot Symbol Mismatch
**File**: `config/modes.yaml:140-148` vs `out/universe_overrides.json`

**AI Copilot wants** (per_sector_weights):
- Automation: ARRY (10%), FROG (8%), PATH (8%)
- Energy: FSLR (12%), ENPH (10%), RUN (8%)

**Universe has**:
- Automation: TPL, ROK, HRI, DAVA, CRH, PNR (NO OVERLAP with wanted)
- Energy: FSLR, ENPH, RUN, PLUG, SEDG, BE, CHPT (partial overlap)

**Result**: AI Copilot can't find its preferred symbols (ARRY, FROG, PATH missing from universe).

### 4. Order Sizing (Not Fully Traced Yet)
**File**: `src/app/allocation.py` + `src/app/allocator.py`

- Uses `compute_target_notional(strategy_budget, conviction, caps)`
- Allocator divides equity by strategy weights
- Need to check if underutilization logic exists

## Immediate Actions Needed

1. **RSS Selector Fallback**: Add fallback to use mode's per_sector_weights symbols when RSS produces 0 candidates
2. **Execution Gate Override**: Raise max_price for aggressive_small_mid_sentiment mode (e.g., $250)
3. **Universe Alignment**: Add ARRY, FROG, PATH to automation sector OR update mode config to use current universe symbols
4. **Target Utilization Allocator**: Implement logic to size orders toward 60% exposure cap
