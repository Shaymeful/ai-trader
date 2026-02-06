# Capital Utilization and Hidden Mode Fixes

**Date:** 2026-01-20
**Status:** Fixed - Ready for Testing

## Issues Identified

### 1. Capital Utilization Exceeding Limits ❌

**Problem:** The system was allocating more than the configured total capital ($50,000).

**Root Cause:**
The allocator calculated available budget without accounting for:
- Current position values ($36,542.52)
- Reserved notional from open orders ($12,931.56)
- Total committed: $49,474.08

When trying to place new orders, it exceeded the $50,000 limit:
```
ERROR: Total exposure $51,623.64 (positions: $36,542.52 + reserved: $12,931.56 + new: $2,149.56) would exceed max $50000
```

**Fix Applied:**
Modified `src/app/allocator.py` to:
1. Calculate current position values from broker
2. Get reserved notional from open BUY orders
3. Subtract both from target budget to get available budget
4. Only allocate new orders within available budget

**Code Changes:**
- File: `src/app/allocator.py` (lines 160-211)
- Now calculates: `available_budget = target_budget - current_positions_value - reserved_notional`
- Logs show: positions, reserved orders, and available budget

### 2. Loop Still Showing Pop-up Windows ❌

**Problem:** Despite `-WindowStyle Hidden` flag, windows still appearing.

**Root Cause:**
Task Scheduler's "Hidden" setting was not enabled, only the PowerShell `-WindowStyle Hidden` flag.

**Fix Available:**
Run `fix_hidden_mode.ps1` as Administrator to:
1. Enable Task Scheduler's Hidden setting
2. Verify configuration
3. Instructions to restart task

## How to Apply Fixes

### Step 1: Fix Hidden Mode (Requires Administrator)

```powershell
# Right-click PowerShell -> Run as Administrator
cd C:\dev\ai-trader

# Run the fix script
.\fix_hidden_mode.ps1

# Restart the task
schtasks /End /TN "AITrader-Loop"
schtasks /Run /TN "AITrader-Loop"
```

### Step 2: Verify Capital Utilization Fix

The code fix is already applied. Next time the loop runs, you should see logs like:

```
Capital Allocation: broker_equity=$100000.00, total_capital=$50000.00, effective_cap=$50000.00, target_util=97.00%, target_budget=$48500.00
Current commitments: positions=$36542.52, reserved_orders=$12931.56, available_budget=$1025.92
```

This shows the allocator correctly accounting for existing commitments.

## Expected Behavior After Fixes

### Capital Utilization
- ✅ Target budget: $50,000 * 97% = $48,500
- ✅ Minus current positions: $36,542.52
- ✅ Minus open orders: $12,931.56
- ✅ Available for new orders: $1,025.92 (or whatever is left)
- ✅ Never exceeds $50,000 total exposure

### Hidden Mode
- ✅ No PowerShell windows appear
- ✅ Task runs silently in background
- ✅ Can monitor via:
  - Task Manager (python.exe process)
  - Log files in `logs/loop/`
  - Dashboard UI

## Monitoring

### Check if Loop is Running (Hidden)
```powershell
# Check process
Get-Process python -ErrorAction SilentlyContinue

# Check task status
Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object State, LastRunTime, NextRunTime

# View recent activity
Get-Content logs\loop_status.log -Tail 10
```

### Monitor Capital Utilization
```powershell
# Check today's allocation logs
Get-Content logs\loop\loop_$(Get-Date -Format "yyyyMMdd").log | Select-String "Capital Allocation|Current commitments"

# Check for errors
Get-Content logs\loop\loop_$(Get-Date -Format "yyyyMMdd").log | Select-String "ERROR|would exceed"
```

## Verification Checklist

After applying fixes:

- [ ] Run `fix_hidden_mode.ps1` as Administrator
- [ ] Restart the AITrader-Loop task
- [ ] Verify no pop-up windows appear
- [ ] Check logs show "Current commitments" calculations
- [ ] Verify no "would exceed max" errors
- [ ] Confirm total exposure stays under $50,000

## Rollback (If Needed)

If issues occur, you can:

1. **Stop the loop:**
   ```powershell
   schtasks /End /TN "AITrader-Loop"
   taskkill /F /IM python.exe
   ```

2. **Revert allocator changes:**
   ```powershell
   git diff src/app/allocator.py
   git checkout src/app/allocator.py
   ```

## Technical Details

### Allocator Logic (Before Fix)
```python
budget_base = effective_equity_cap * target_utilization_pct
# Always allocated as if starting fresh
```

### Allocator Logic (After Fix)
```python
target_budget = effective_equity_cap * target_utilization_pct
current_positions_value = sum(abs(pos.qty) * pos.current_price)
reserved_notional = sum(open_order.qty * open_order.limit_price for buy orders)
available_budget = max(0, target_budget - current_positions_value - reserved_notional)
# Only allocate within available budget
```

### Task Scheduler Settings
- **Before:** Hidden = false, only `-WindowStyle Hidden` flag
- **After:** Hidden = true, plus `-WindowStyle Hidden` flag

## Files Modified

1. `src/app/allocator.py` - Fixed capital utilization calculation
2. `fix_hidden_mode.ps1` - New script to enable Hidden mode properly

## Next Steps

1. Apply the fixes as described above
2. Monitor the loop for one full market day
3. Verify capital utilization stays within limits
4. Confirm no pop-up windows appear
5. If everything works correctly, commit the allocator.py changes

## Questions or Issues?

If you encounter any problems:
1. Check logs in `logs/loop/loop_YYYYMMDD.log`
2. Verify task status with `Get-ScheduledTask -TaskName "AITrader-Loop"`
3. Check for error patterns in recent logs
