# Market Hours Loop - Automatic Startup

This guide explains how to set up automatic loop startup that only runs during market hours on weekdays.

## Overview

The smart loop starter:
- ✓ Only runs Monday-Friday (skips weekends)
- ✓ Only runs 9:30 AM - 4:00 PM Eastern Time (market hours)
- ✓ Checks if loop is already running (no duplicates)
- ✓ Cleans up stale lock files
- ✓ Safe to run repeatedly

## Quick Start

### Option 1: Windows Task Scheduler (Recommended for Windows)

1. Open PowerShell as Administrator
2. Run the scheduler setup script:

```powershell
cd C:\dev\ai-trader
powershell -ExecutionPolicy Bypass -File tools\windows\schedule_loop_task.ps1
```

This creates a scheduled task that:
- Runs every 15 minutes on weekdays
- Checks market hours before starting
- Starts loop if not already running

### Option 2: Manual Execution

Run the smart starter script anytime:

```bash
cd /c/dev/ai-trader
python tools/start_loop_market_hours.py
```

Output example:
```
============================================================
AI Trader - Smart Loop Starter
============================================================
Current time: 2026-02-10 09:35:00 EST

✓ Weekday check passed
✓ Market hours check passed
⚠ Loop is not running

Starting trading loop...
Started trading loop with PID: 12345
Logging to: logs/loop/loop_20260210.log
✓ Loop started successfully!
```

If market is closed or it's the weekend:
```
============================================================
AI Trader - Smart Loop Starter
============================================================
Current time: 2026-02-08 10:00:00 EST

❌ Not a weekday (today is Saturday)
Loop will not start on weekends
```

## How It Works

### Market Hours Detection

```python
# Market hours: 9:30 AM - 4:00 PM Eastern Time
# Only runs Monday-Friday
```

The script uses `zoneinfo` to handle timezone conversion properly, accounting for:
- Eastern Standard Time (EST)
- Eastern Daylight Time (EDT)
- Automatic daylight saving time transitions

### Duplicate Prevention

The script checks if the loop is already running by:
1. Reading the lock file (`logs/paper_dryrun.lock`)
2. Extracting the PID
3. Checking if that process is still alive
4. Cleaning up stale locks if process died

### Logging

Each day gets its own log file:
- `logs/loop/loop_20260210.log` (example)
- Scheduler logs: `logs/scheduler/` (if using Task Scheduler)

## Configuration

### Change Check Frequency

Edit the scheduled task to run more or less frequently:

```powershell
# Check every 10 minutes instead of 15
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At "6:00 AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 1)
```

### Modify Market Hours

Edit `tools/start_loop_market_hours.py`:

```python
def is_market_hours() -> bool:
    et_now = get_eastern_time()

    # Change these times if needed
    market_open = et_now.replace(hour=9, minute=30, second=0)
    market_close = et_now.replace(hour=16, minute=0, second=0)

    return market_open <= et_now <= market_close
```

### Add Market Holiday Detection

For more advanced setup, integrate with a market calendar API:

```python
import pandas_market_calendars as mcal

def is_market_holiday() -> bool:
    """Check if today is a market holiday."""
    nyse = mcal.get_calendar('NYSE')
    et_now = get_eastern_time()
    schedule = nyse.schedule(start_date=et_now.date(), end_date=et_now.date())
    return schedule.empty
```

## Troubleshooting

### Task Not Running

Check if task is enabled:
```powershell
Get-ScheduledTask -TaskName "AITrader-Loop-MarketHours" | Select-Object TaskName, State
```

Enable if disabled:
```powershell
Enable-ScheduledTask -TaskName "AITrader-Loop-MarketHours"
```

### Manual Test

Run the task manually to see output:
```powershell
schtasks /run /tn "AITrader-Loop-MarketHours"
```

### View Task History

1. Open Task Scheduler (`taskschd.msc`)
2. Find "AITrader-Loop-MarketHours"
3. Click "History" tab to see execution logs

### Loop Not Starting During Market Hours

Check the script output manually:
```bash
python tools/start_loop_market_hours.py
```

Common issues:
- Lock file stuck: Script will clean it up
- Wrong timezone: Verify system timezone settings
- Python path wrong: Check virtual environment is activated

## Uninstall

Remove the scheduled task:

```powershell
schtasks /delete /tn "AITrader-Loop-MarketHours" /f
```

Or keep the task but disable it:

```powershell
schtasks /change /tn "AITrader-Loop-MarketHours" /disable
```

## Alternative: Linux/Mac with Cron

For Linux or Mac systems, add to crontab:

```bash
# Run every 15 minutes on weekdays
*/15 * * * 1-5 cd /path/to/ai-trader && /path/to/.venv/bin/python tools/start_loop_market_hours.py >> logs/scheduler/cron.log 2>&1
```

The script handles market hours checking, so it's safe to run frequently.

## Testing Before Monday

To test the script logic without waiting for market hours:

```python
# Temporarily modify is_market_hours() in start_loop_market_hours.py
def is_market_hours() -> bool:
    return True  # Always return True for testing
```

Run the script and verify it starts the loop. Remember to revert the change!

## Summary

**What you get:**
- Automatic loop startup during market hours
- No manual intervention needed
- Safe handling of weekends and after-hours
- Automatic cleanup of stuck processes
- Daily log files for monitoring

**Next steps:**
1. Run the PowerShell scheduler script
2. Wait until Monday 9:30 AM EST
3. Check logs to verify loop started automatically
4. Monitor throughout the day

The loop will now manage itself during market hours!
