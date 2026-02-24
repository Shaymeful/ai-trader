# Implementation Plan: Target Utilization & Order Frequency Fixes

## Quick Wins (Do These First)

### 1. Fix Execution Gate for aggressive_small_mid_sentiment
**File**: config/modes.yaml:184
- Change max_price: 150.00 → 250.00
- This unblocks FSLR ($235-242) and BE ($152)
- **Impact**: Immediate - 2 more symbols tradeable

### 2. Add Universe Symbols to Match AI Copilot Targets
**Option A** (Preferred): Update mode config to use current universe
- Change per_sector_weights in modes.yaml to use TPL, ROK, HRI, DAVA, CRH, PNR
- **Impact**: Immediate - AI Copilot can actually trade

### 3. RSS Selector Fallback
**File**: src/app/selector/rss_selector.py
- Add fallback: if 0 candidates, use mode's per_sector_weights symbols
- Create synthetic "watch" candidates for those symbols
- **Impact**: Always have candidate pool
