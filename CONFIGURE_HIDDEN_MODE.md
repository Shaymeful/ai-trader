# Configure Loop to Run Hidden & Only During Market Hours

**Date:** 2026-01-16
**Status:** Ready for Configuration

## Changes Made

### 1. ✅ Market Hours Check Added
The loop now automatically checks if the market is open before each iteration:
- **Market Hours:** Monday-Friday, 9:30 AM - 4:00 PM ET
- **Behavior:** Skips iterations when market is closed, sleeps and checks again

**File Modified:** `src/app/runner.py`

### 2. ✅ Hidden Mode Scripts Created
Two new scripts to run the loop without pop-up windows:
- `tools/windows/start_loop_hidden.ps1` - Starts loop hidden
- `tools/windows/update_task_simple.cmd` - Updates Task Scheduler task

## How to Enable Hidden Mode

### Option 1: Update Task Scheduler Task (Recommended)

**Run as Administrator:**
```powershell
# Right-click PowerShell -> Run as Administrator
cd C:\dev\ai-trader

# Update the task
schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 300 -LogToFile"
```

**Verify the update:**
```powershell
Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object -ExpandProperty Actions
```

Should show:
```
Arguments: -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File...
```

### Option 2: Use Update Script (Easier)

**Run as Administrator:**
1. Right-click `tools\windows\update_task_simple.cmd`
2. Select "Run as administrator"
3. Follow the prompts

### Option 3: Manual Task Scheduler Update

1. Open Task Scheduler (Win+R → taskschd.msc)
2. Find "AITrader-Loop" task
3. Right-click → Properties
4. Go to "Actions" tab
5. Edit the action:
   - **Program:** `PowerShell.exe`
   - **Arguments:**
     ```
     -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -SleepSeconds 300 -LogToFile
     ```
6. Go to "General" tab
7. Check "Run whether user is logged on or not"
8. Check "Hidden" (if available)
9. Click OK

## Configuration Options

### Sleep Interval
Default is now **5 minutes** (300 seconds) for more responsive trading.

**To change:**
```powershell
# For 1-hour intervals
schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 3600 -LogToFile"

# For 15-minute intervals
schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 900 -LogToFile"
```

### Market Hours
Default: 9:30 AM - 4:00 PM ET, Monday-Friday

**To customize** (edit `src/app/market_hours.py`):
```python
is_market_hours(
    market_open_hour=9,      # Hour (24-hour format)
    market_open_minute=30,   # Minute
    market_close_hour=16,    # Hour (24-hour format)
    market_close_minute=0,   # Minute
)
```

## How It Works

### Market Hours Check
```
Loop starts
  ↓
Check if market open (9:30 AM - 4:00 PM ET, weekdays)
  ↓
├─ Market OPEN → Run iteration, place orders
  ↓
└─ Market CLOSED → Skip iteration, log message, sleep
  ↓
Sleep for interval (e.g., 5 minutes)
  ↓
Repeat
```

**Example Output (Market Closed):**
```
================================================================================
MARKET CLOSED - 2026-01-16T20:15:00-05:00
================================================================================
Market is currently closed (weekday 9:30 AM - 4:00 PM ET)
Next market open in: 13.2 hours (795 minutes)
Will check again after sleep interval: 300 seconds
================================================================================
```

### Hidden Mode
When running with `-WindowStyle Hidden`:
- No pop-up windows appear
- Process runs in background
- Logs continue writing to `logs/loop/loop_YYYYMMDD.log`
- Can be monitored via Task Manager or log files

## Starting the Loop

### Via Task Scheduler (Hidden)
```powershell
schtasks /Run /TN "AITrader-Loop"
```

### Manually (Hidden)
```powershell
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -SleepSeconds 300 -LogToFile
```

### Manually (Visible, for testing)
```powershell
cd C:\dev\ai-trader
.venv\Scripts\python.exe -m src.app.runner --mode paper --loop --sleep-seconds 300
```

## Monitoring

### Check if Loop is Running
```powershell
# Check for python processes
tasklist /FI "IMAGENAME eq python.exe"

# Check Task Scheduler status
Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object TaskName, State, LastRunTime, NextRunTime
```

### View Logs
```powershell
# Recent activity
Get-Content C:\dev\ai-trader\logs\loop_status.log -Tail 20

# Today's full log
Get-Content C:\dev\ai-trader\logs\loop\loop_$(Get-Date -Format "yyyyMMdd").log -Tail 100

# Watch live (visible mode only)
Get-Content C:\dev\ai-trader\logs\loop\loop_$(Get-Date -Format "yyyyMMdd").log -Wait
```

### Check Market Hours Behavior
```powershell
# Look for "MARKET CLOSED" messages
Select-String "MARKET CLOSED" C:\dev\ai-trader\logs\loop\loop_*.log | Select-Object -Last 10
```

## Stopping the Loop

### Stop Task Scheduler Task
```powershell
schtasks /End /TN "AITrader-Loop"
```

### Kill Processes (if needed)
```powershell
taskkill /F /IM python.exe
```

## Testing

### Test Market Hours Check (Outside Market Hours)
```powershell
cd C:\dev\ai-trader

# Run one iteration (will show "MARKET CLOSED" if outside hours)
.venv\Scripts\python.exe -m src.app.runner --mode paper --once
```

Expected output when market is closed:
```
Market is currently closed (weekday 9:30 AM - 4:00 PM ET)
```

### Test Hidden Mode
```powershell
# Start hidden
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\dev\ai-trader\tools\windows\start_loop.ps1" -Mode paper -SleepSeconds 300 -LogToFile

# Check it's running
tasklist /FI "IMAGENAME eq python.exe"

# Stop it
taskkill /F /IM python.exe
```

## Troubleshooting

### Pop-ups Still Appearing
1. Verify task was updated: `Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object -ExpandProperty Actions`
2. Check for `-WindowStyle Hidden` in arguments
3. Make sure using the correct Task Scheduler trigger (not manual start)

### Loop Not Running During Market Hours
1. Check system time zone is correct
2. Check logs: `Get-Content logs\loop\loop_$(Get-Date -Format "yyyyMMdd").log -Tail 50`
3. Verify market hours logic: `python -c "from src.app.market_hours import is_market_hours; print(is_market_hours())"`

### Task Won't Update
- Must run as Administrator
- Try manual Task Scheduler update (Option 3 above)
- Check for typos in the command

## Recommended Configuration

**For Production:**
```powershell
# Update task to run hidden, 5-minute intervals
schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\dev\ai-trader\tools\windows\start_loop.ps1\" -Mode paper -SleepSeconds 300 -LogToFile"

# Start the task
schtasks /Run /TN "AITrader-Loop"

# Verify it's running hidden
tasklist /FI "IMAGENAME eq python.exe"

# Check logs
Get-Content logs\loop_status.log -Tail 10
```

**Benefits:**
- ✅ No pop-up windows
- ✅ Only runs during market hours (9:30 AM - 4:00 PM ET)
- ✅ Responsive 5-minute intervals
- ✅ Automatic market hours checking
- ✅ Logs all activity

## Files Created/Modified

### New Files
1. `src/app/market_hours.py` - Market hours checking utilities
2. `tools/windows/start_loop_hidden.ps1` - Hidden mode launcher
3. `tools/windows/update_task_simple.cmd` - Task updater (admin)
4. `tools/windows/update_task_hidden.ps1` - Advanced task updater
5. `CONFIGURE_HIDDEN_MODE.md` (this file) - Configuration guide

### Modified Files
1. `src/app/runner.py` - Added market hours check to run_loop()

## Next Steps

1. **Update Task Scheduler** (requires admin)
2. **Start the loop** via Task Scheduler
3. **Verify behavior**:
   - No pop-ups appearing
   - Loop running in background
   - Skipping iterations when market closed
4. **Monitor logs** to confirm working correctly

The loop is now configured to:
- ✅ Run only during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
- ✅ Run hidden without pop-up windows (once task is updated)
- ✅ Check every 5 minutes for responsive trading
- ✅ Log all activity for monitoring
