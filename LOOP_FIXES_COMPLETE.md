# Loop Runtime State and Error Handling Fixes

## Issues Fixed

### 1. Runtime State Not Updating on Loop Failure
**Problem:** The dashboard showed "Overdue (2571m)" even though the loop ran at 9:30 AM today and placed a trade at 9:31 AM. The `next_loop_at` field in `state/runtime.json` had a stale timestamp from Feb 4.

**Root Cause:** When the loop failed partway through (after placing trades but before completing), the `next_loop_at` field wasn't being updated. The exception handler updated it, but if the failure happened outside the try-except block or if the save failed, the state would remain stale.

**Fix:** Added a `finally` block that ALWAYS updates the loop timing state, regardless of success or failure:
```python
finally:
    # CRITICAL: ALWAYS update loop timing state
    loop_end_utc = datetime.now(UTC)
    runtime_state.last_loop_end = loop_end_utc.isoformat()
    next_run_utc = loop_end_utc + timedelta(seconds=sleep_seconds)
    runtime_state.next_loop_at = next_run_utc.isoformat()

    # Save with error handling
    try:
        save_runtime_state(runtime_state)
    except Exception as e:
        print(f"CRITICAL: Failed to save runtime state: {e}")
```

### 2. XLV Pricing Error Causing Loop Crash
**Problem:** Loop failed with "ERROR: Loop failed: XLV: No price available, skipping". This error message came from a symbol without price data, which should have been skipped with a warning but instead caused the entire iteration to fail.

**Root Cause:** No defensive handling for catastrophic market data failures. If all symbols failed to fetch data, the loop would continue with empty data structures and potentially crash downstream.

**Fix:** Added comprehensive error handling for market data fetching:
1. Try-except wrapper around `get_market_data()` call
2. Early return with empty RunResult if data fetch fails completely
3. Check for completely empty market_data and skip iteration gracefully
4. Better logging to diagnose the actual failure point

```python
try:
    market_data = provider.get_market_data(universe)
except Exception as e:
    print(f"ERROR: Failed to fetch market data: {e}")
    traceback.print_exc()
    return RunResult(mode="paper", dry_run=dry_run, orders_placed=0, ...)

if not market_data:
    print("WARNING: No market data available for any symbol")
    print("Skipping this iteration - will retry next cycle")
    return RunResult(mode="paper", dry_run=dry_run, orders_placed=0, ...)
```

## Changes Made

### `src/app/runner.py`
1. Added `iteration_success` flag to track completion status
2. Moved all loop timing state updates to a `finally` block
3. Added error handling wrapper around `get_market_data()` calls
4. Added validation for empty market data (all symbols missing)
5. Added DEBUG logging for state save operations

### `docs/ARCHITECTURE.md`
1. Updated "Loop Timing Instrumentation" section to document finally block
2. Clarified that state updates ALWAYS happen regardless of success/failure
3. Added notes about error handling in state save operations

## Testing Recommendations

1. **Verify State Updates:**
   ```powershell
   # Start loop
   python -m src.app.runner --mode paper --loop --sleep-seconds 600

   # Check state is updated after each iteration
   cat state/runtime.json
   ```

2. **Test Market Data Failure Handling:**
   - Run loop during pre-market hours (before 9:30 AM ET)
   - Verify graceful skip with clear warning message
   - Verify state still updates correctly

3. **Test Dashboard Display:**
   - Start loop
   - Open dashboard at http://localhost:8001
   - Verify "Next Run" time updates after each iteration
   - Verify "Overdue" status only shows when loop is actually overdue

## Expected Behavior After Fix

1. **State Always Updates:** `next_loop_at` field in `state/runtime.json` will ALWAYS be updated after each loop iteration, even if the iteration fails
2. **Graceful Data Failures:** Missing price data for individual symbols will be logged as warnings and skipped, but won't crash the loop
3. **Clear Error Messages:** When market data fetching fails completely, a clear error message will be logged with full traceback
4. **Dashboard Accuracy:** Dashboard "Next Run" time will always reflect the actual next scheduled run

## Monitoring

After deploying this fix, monitor:
1. `state/runtime.json` - Verify `next_loop_at` updates after each iteration
2. `logs/loop/loop_YYYYMMDD.log` - Check for "DEBUG: Saved loop state" messages
3. Dashboard UI - Verify "Overdue" status is accurate

## Related Files
- `src/app/runner.py` - Main fix
- `src/app/state.py` - Runtime state management (unchanged)
- `docs/ARCHITECTURE.md` - Updated documentation
