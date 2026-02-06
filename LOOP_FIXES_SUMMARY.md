# Loop Status Fixes - January 15, 2026

## Issues Fixed

### 1. Loop Interval Mismatch ✅
- **Problem**: UI set to 0.1 hr (360 seconds) but runtime.json had 300 seconds
- **Fixed**: Updated `state/runtime.json` to 360 seconds

### 2. Dashboard Shows "Overdue" Instead of Error Message ✅
- **Problem**: When loop fails, dashboard just shows "Overdue (X minutes)"
- **Fixed**:
  - Added `last_error` and `last_error_at` fields to `RuntimeState` model
  - Runner now records error details when iteration fails
  - Dashboard now displays: "Error: {error_message}" instead of generic "overdue"
  - Hover over error shows timestamp
- **Files changed**:
  - `src/app/state.py` - Added error fields to RuntimeState
  - `src/app/runner.py` - Set error on failure, clear on success
  - `src/ui_api/app.py` - Expose error fields in API
  - `src/ui_api/dashboard.html` - Display error messages

### 3. Scheduled Task Interval Mismatch ⏳ (NEEDS ADMIN)
- **Problem**: Scheduled task passes `-SleepSeconds 3600` which overrides UI setting
- **Fixed**:
  - Updated `tools/windows/start_loop.ps1` to default `-SleepSeconds 0` (use runtime state)
  - Created `update_task.ps1` to update scheduled task
- **Action Required**: Run as administrator:
  ```powershell
  powershell -ExecutionPolicy Bypass -File "C:\dev\ai-trader\update_task.ps1"
  ```

## Current Status

**Loop Status at 2:17 PM**:
- Last run: 2:00 PM (crashed with exposure limit error)
- Next scheduled run: 3:00 PM
- Loop interval: 360 seconds (6 minutes)
- Error: "TLN: Total exposure $50523.06 would exceed max $50000"

**Root Issue**: All orders are being skipped due to reserved buying power ($43k reserved from previous duplicate orders that may still exist). The order hygiene system is correctly preventing new orders, but there's no room left for any trades.

## Recommendations

1. **Update Scheduled Task (Admin Required)**:
   ```powershell
   # Run as Administrator
   powershell -ExecutionPolicy Bypass -File "C:\dev\ai-trader\update_task.ps1"
   ```

2. **Check for Remaining Duplicate Orders**:
   ```powershell
   python cancel_all_orders.py
   ```

3. **Restart Loop to Test Fixes**:
   ```powershell
   # Stop current loop if running
   Get-Process python | Where-Object { $_.CommandLine -like "*runner*" } | Stop-Process

   # Start fresh
   powershell -ExecutionPolicy Bypass -File tools\windows\start_loop.ps1 -Mode paper -LogToFile
   ```

4. **Monitor Dashboard**: Dashboard will now show specific error messages when iterations fail

## Files Modified

- `state/runtime.json` - Loop interval corrected to 360s
- `src/app/state.py` - Added error tracking fields
- `src/app/runner.py` - Record/clear errors on iteration complete/fail
- `src/ui_api/app.py` - Expose error fields in RuntimeResponse
- `src/ui_api/dashboard.html` - Display error messages
- `tools/windows/start_loop.ps1` - Default SleepSeconds to 0 (use runtime state)
- `update_task.ps1` - Script to update scheduled task (needs admin)
