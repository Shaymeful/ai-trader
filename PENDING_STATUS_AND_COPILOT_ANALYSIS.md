# Pending Status and AI Copilot Sector Exit Analysis

## Issue 1: Pending Status Persisting Too Long

### Root Cause

The "pending" status on universe sectors indicates that proposals have been approved but not yet "activated" into the live configuration. The activation should happen automatically at the start of each loop iteration.

**Why It's Stuck:**

1. **Loop Not Running**: PID 49428 (the loop process) is no longer running
2. **Historical Failures**: Earlier loop attempts failed due to PowerShell wrapper incorrectly treating "No price available, skipping" warnings as fatal errors
3. **Activation Timing**: The activation code runs at line 1505 of `runner.py`, at the START of each loop iteration, BEFORE fetching market data

**Evidence:**
- `out/universe_overrides.json` shows pending_versions for multiple sectors
- Loop logs show no "Universe configuration changes activated" messages
- Process check confirms loop PID 49428 is dead

### Current Pending Versions

From `out/universe_overrides.json`:
```json
{
  "mega_cap_tech": {"active_version": 11, "pending_version": 12},
  "us_sector_etfs": {"active_version": 6, "pending_version": 7},
  "automation": {"active_version": 2, "pending_version": 3},
  "energy": {"active_version": 0, "pending_version": 1}
}
```

### Solution

**Immediate Fix:**
1. Restart the loop process properly
2. Ensure it runs continuously without PowerShell wrapper interference
3. Activation will happen automatically on next iteration

**Long-term Prevention:**
- Activation should be resilient to market data failures
- Consider manual activation endpoint in UI for stuck pending versions
- Add health check that alerts when pending versions are stuck >24 hours

---

## Issue 2: AI Copilot Cannot Exit Disabled Sector Positions

### Current Behavior

The AI Copilot Weighted Strategy (`ai_copilot_weighted.py`) can only trade symbols that are in the active universe. The universe is built from enabled sectors only (line 733-736 in `runner.py`):

```python
if universe_registry is not None:
    resolution = universe_registry.resolve()  # Only returns enabled sector symbols
    universe = resolution.symbols
```

**Problem:**
- If you disable a sector, its symbols are removed from the universe
- AI Copilot can't generate sell intents for symbols not in the universe
- You get "stuck" with positions in disabled sectors that can't be exited

### Desired Behavior

**For Buy Signals:**
- AI Copilot should ONLY buy from enabled sectors ✓ (already works)

**For Sell Signals:**
- AI Copilot should be able to exit positions from disabled sectors
- Should PREFER exiting disabled sector positions over enabled ones
- Should NOT be able to buy from disabled sectors

### Solution Approach

**Option 1: Augment Universe with Existing Positions (Recommended)**

Modify `runner.py` line 733-741 to include existing positions even from disabled sectors:

```python
if universe_registry is not None:
    resolution = universe_registry.resolve()
    universe = resolution.symbols

    # Add existing positions to universe (for exits only)
    positions = broker.get_positions()
    position_symbols = set(positions.keys())
    universe_with_exits = list(set(universe) | position_symbols)

    print(f"  Universe from registry: {', '.join(universe)} ({resolution.source})")
    if position_symbols - set(universe):
        print(f"  + Existing positions from disabled sectors: {', '.join(position_symbols - set(universe))}")

    universe = universe_with_exits
```

Then modify `AICopilotWeightedStrategy._filter_to_active_universe()` to:
1. Include symbols from config that are in universe
2. Include symbols NOT in config but that have existing positions
3. Set weight=0 for symbols not in config (forces exit)

**Option 2: Separate Exit Universe**

Create two universes:
- `buy_universe`: Only enabled sectors
- `sell_universe`: Enabled sectors + existing positions

Pass both to strategies, use buy_universe for new positions, sell_universe for exits.

**Option 3: Add "exit_only" Flag to Sectors**

Extend `SectorOverride` with `exit_only: bool` flag. When true:
- Symbols included in universe
- Strategy receives them but with weight=0 (exit signal)
- Prevents new buys while allowing exits

### Recommendation

**Use Option 1** - simplest and most robust:
1. Augment universe with existing position symbols
2. Modify AI Copilot to treat unlisted symbols (not in config) as exit candidates
3. Set conviction=0 for these symbols to force position reduction

This ensures:
- ✓ Can exit disabled sector positions
- ✓ Cannot buy from disabled sectors (not in config)
- ✓ Minimal code changes
- ✓ Works with existing reconciliation logic

---

## Implementation Plan

### Phase 1: Fix Pending Activation (Immediate)

1. Restart loop process cleanly
2. Verify activation happens on next iteration
3. Monitor for "Universe configuration changes activated" messages

### Phase 2: AI Copilot Exit Enhancement (Next)

1. Modify `run_paper_mode()` to augment universe with existing positions
2. Update `AICopilotWeightedStrategy._filter_to_active_universe()` to handle unlisted symbols
3. Add logic to set weight=0 for positions not in config (exit signal)
4. Test with disabled sector position exit scenario
5. Update `docs/ARCHITECTURE.md` with new behavior

### Testing Scenarios

**Scenario 1: Normal Operation**
- Enabled sector: automation (TPL, RYAAY, ROK)
- AI Copilot should allocate normally

**Scenario 2: Sector Disabled with Position**
- Disable automation sector
- Have existing position in TPL
- AI Copilot should generate exit signal for TPL
- Should NOT buy more TPL

**Scenario 3: Exit Priority**
- Enabled sector: energy (WEC)
- Disabled sector with position: automation (TPL)
- AI Copilot should prefer exiting TPL before reducing WEC

---

## Files to Modify

### For Pending Activation Fix:
- `src/app/runner.py` - Already correct, just need loop running

### For AI Copilot Exit Enhancement:
- `src/app/runner.py` (lines 733-741) - Augment universe with positions
- `src/app/strategies/ai_copilot_weighted.py` (lines 133-158) - Handle unlisted symbols
- `docs/ARCHITECTURE.md` - Document new behavior

### Testing:
- Manual test: disable sector with position, verify exit generated
- Unit test: `test_ai_copilot_exit_disabled_sectors.py`

---

## Current State Summary

**Loop Status:** Not running (PID 49428 dead)
**Pending Versions:** 4 sectors have pending changes
**AI Copilot:** Cannot exit disabled sector positions
**Impact:** Stuck positions in disabled sectors, pending changes not activating

**Next Actions:**
1. Restart loop
2. Verify pending activations
3. Implement AI copilot exit enhancement
