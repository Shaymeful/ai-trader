# ✅ AITrader Scheduler Tasks - Fixes Implemented

**Date**: 2026-01-07
**Status**: Partially Complete - Requires Administrator Action

---

## 🎯 What Was Fixed

### ✅ 1. Universe Sectors Enabled (CRITICAL FIX)
**Problem**: All universe sectors were disabled, causing loop to fail with "No symbols in universe"

**Solution**: Enabled `core_index` sector via API
```json
{
  "sector_name": "core_index",
  "enabled": true,
  "symbols": ["SPY", "QQQ", "DIA", "IWM"],
  "symbol_count": 4,
  "pending_version": 2
}
```

**Status**: ✅ **COMPLETE** - Universe now has 4 active symbols
**Effect**: Next loop iteration (top of hour) will succeed instead of failing immediately

---

### ✅ 2. Manual Test Processes Killed
**Problem**: Background test processes conflicting with scheduled tasks

**Actions Taken**:
- ✅ Killed manual test runner (PID 271436)
- ✅ Killed manual dashboard (PID 282120)
- ✅ Removed lock file `logs\paper_dryrun.lock`

**Status**: ✅ **COMPLETE** - No process conflicts

---

### ⚠️ 3. AITrader-Loop DryRun Flag (REQUIRES ADMIN)
**Problem**: AITrader-Loop task runs in **LIVE PAPER TRADING MODE** (will place real orders)

**Solution Prepared**:
- Created modified task XML: `AITrader-Loop.xml`
- Added `-DryRun` flag to task arguments
- Created installer script: `fix_scheduler_tasks.cmd`

**Status**: ⚠️ **PENDING** - Requires Administrator privileges to update

**What You Need To Do**:
1. Right-click `C:\dev\ai-trader\fix_scheduler_tasks.cmd`
2. Select "Run as administrator"
3. Follow prompts to update task

**Alternatively**, manually edit the task:
1. Open Task Scheduler (taskschd.msc)
2. Find "AITrader-Loop"
3. Edit Action → Edit Arguments
4. Change from: `-Mode paper -SleepSeconds 3600 -LogToFile`
5. Change to: `-Mode paper -DryRun -SleepSeconds 3600 -LogToFile`

---

### ⚠️ 4. Delete AI-Trader-Hourly Task (REQUIRES ADMIN)
**Problem**: Obsolete task still exists (disabled but cluttering task list)

**Status**: ⚠️ **PENDING** - Requires Administrator privileges to delete

**What You Need To Do**:
- Run `fix_scheduler_tasks.cmd` as administrator (handles both tasks)

**OR** manually delete:
1. Open Task Scheduler (taskschd.msc)
2. Find "AI-Trader-Hourly"
3. Right-click → Delete

---

## 📊 Current Task Status

| Task Name | Status | Mode | Dry-Run | Next Run | Health |
|-----------|--------|------|---------|----------|--------|
| **AITrader-Dashboard** | ✅ Running | N/A | N/A | Daily 8:45 AM | ✅ Healthy |
| **AITrader-Selector** | ✅ Running | N/A | N/A | Every 15 min | ✅ Healthy |
| **AITrader-Loop** | ⚠️ Needs Fix | Paper | ❌ NO (LIVE!) | Hourly from 9 AM | ⚠️ Fixed universe, needs dry-run |
| **AI-Trader-Hourly** | ❌ Disabled | N/A | N/A | N/A | ❌ Obsolete - Delete |

---

## 🔧 Quick Fix Command (Run as Administrator)

```cmd
cd C:\dev\ai-trader
fix_scheduler_tasks.cmd
```

This will:
1. ✅ Update AITrader-Loop to add `-DryRun` flag
2. ✅ Delete obsolete AI-Trader-Hourly task
3. ✅ Show summary of all tasks

---

## 🔍 Verification Steps

### After Running Fix Script:

1. **Verify Task Updated**:
   ```cmd
   schtasks /Query /TN AITrader-Loop /V /FO LIST | findstr "Task To Run"
   ```
   Should show: `... -Mode paper -DryRun -SleepSeconds 3600 -LogToFile`

2. **Verify Universe Enabled**:
   ```cmd
   curl http://localhost:8000/universe/sectors
   ```
   Should show `"total_symbols": 4`

3. **Check Next Loop Run**:
   Wait until top of next hour, then check:
   ```cmd
   type logs\loop\loop_20260107.log
   ```
   Should show successful iteration with SPY, QQQ, DIA, IWM in universe

---

## 📈 Expected Behavior After Fixes

### Next Loop Iteration (Top of Hour):
1. ✅ Universe has 4 symbols (SPY, QQQ, DIA, IWM)
2. ✅ Loop will activate pending version 2 for core_index sector
3. ✅ Loop will run in **DRY-RUN mode** (no actual orders) ← *After fix script*
4. ✅ Loop will complete successfully and log to `logs\loop\loop_YYYYMMDD.log`
5. ✅ Loop will sleep for 3600 seconds (1 hour) and repeat

### Current Behavior (Before Fix Script):
- ⚠️ Loop runs in **LIVE mode** (will place real orders on paper account)
- ✅ Universe is enabled (will not crash)
- ⚠️ Need to run fix script to add safety `-DryRun` flag

---

## 🚨 IMPORTANT SAFETY NOTES

1. **AITrader-Loop is currently in LIVE mode**
   - It WILL place real orders on your paper Alpaca account
   - Once universe is activated (next hour), trades will execute
   - **Run the fix script BEFORE next hour to enable dry-run safety**

2. **Universe Activation**
   - Changes to universe take effect at next loop iteration
   - Current: pending_version = 2 (will activate at top of hour)
   - After activation: 4 symbols will be available for trading

3. **Dashboard Port**
   - AITrader-Dashboard runs on **port 8000**
   - Access at: http://localhost:8000
   - No authentication - secure your network

---

## 📝 Files Created

1. **AITrader-Loop.xml** - Modified task definition (with -DryRun)
2. **fix_scheduler_tasks.cmd** - Master fix script (run as admin)
3. **update_loop_task.cmd** - Updates loop task only (run as admin)
4. **delete_legacy_task.cmd** - Deletes AI-Trader-Hourly (run as admin)
5. **SCHEDULER_FIXES_SUMMARY.md** - This document

---

## ✅ Completion Checklist

- [x] Enable universe sectors (core_index enabled)
- [x] Kill manual test processes (PIDs 271436, 282120)
- [x] Remove lock file (logs\paper_dryrun.lock)
- [ ] **Add -DryRun flag to AITrader-Loop** ← **RUN AS ADMIN**
- [ ] **Delete AI-Trader-Hourly task** ← **RUN AS ADMIN**
- [ ] Verify next loop iteration succeeds
- [ ] Confirm dry-run mode active in logs

---

## 🔗 Next Steps

1. **IMMEDIATE**: Run `fix_scheduler_tasks.cmd` as administrator
2. **VERIFY**: Check task was updated successfully
3. **MONITOR**: Wait for next loop iteration (top of hour)
4. **CONFIRM**: Check `logs\loop\loop_20260107.log` shows:
   - "Dry-run: True" (after fix)
   - Universe: SPY, QQQ, DIA, IWM
   - Successful completion

---

**Questions or Issues?**
- Check logs: `logs\loop\loop_YYYYMMDD.log`
- Dashboard: http://localhost:8000
- Universe status: http://localhost:8000/universe/sectors
