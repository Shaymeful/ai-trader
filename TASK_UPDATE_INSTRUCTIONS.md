# Update Task Scheduler - Quick Instructions

## Current Status
✅ Task is stopped and ready to update
✅ Scripts created
⚠️ Requires Administrator privileges to update

## Option 1: Double-Click Method (Easiest)

1. Go to: `C:\dev\ai-trader`
2. Find: `update_task_hidden.cmd`
3. **Right-click** → **Run as administrator**
4. When prompted, click "Yes" (UAC prompt)
5. Press any key to start the loop

## Option 2: PowerShell Method

**Step 1:** Open PowerShell as Administrator
- Press `Win` key
- Type "PowerShell"
- Right-click "Windows PowerShell"
- Click "Run as administrator"

**Step 2:** Run this command:
```powershell
cd C:\dev\ai-trader

schtasks /Change /TN "AITrader-Loop" /TR "PowerShell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\dev\ai-trader\tools\windows\start_loop.ps1`" -Mode paper -SleepSeconds 300 -LogToFile"
```

**Step 3:** Start the loop:
```powershell
schtasks /Run /TN "AITrader-Loop"
```

## Verify It Worked

```powershell
# Check task arguments (should show "-WindowStyle Hidden" and "SleepSeconds 300")
(Get-ScheduledTask -TaskName "AITrader-Loop").Actions.Arguments

# Check if running
tasklist /FI "IMAGENAME eq python.exe"

# Check logs (should show "MARKET CLOSED" messages since it's after hours)
Get-Content logs\loop_status.log -Tail 5
```

## What Changed

**Before:**
- Pop-up windows every iteration
- Ran continuously (even outside market hours)
- 1-hour interval

**After:**
- ✅ Runs **hidden** (no pop-ups!)
- ✅ Only runs during **market hours** (Mon-Fri 9:30 AM - 4:00 PM ET)
- ✅ Checks every **5 minutes** (more responsive)
- ✅ Skips iterations when market closed

## Expected Behavior

**Right Now (Friday 9:00 PM):**
```
MARKET CLOSED - 2026-01-16T21:00:00-05:00
Next market open in: 60.5 hours
Will check again after sleep interval: 300 seconds
```

Loop sleeps 5 minutes, checks again, sees market still closed, repeats.

**Monday Morning (9:30 AM):**
```
LOOP ITERATION 1 - 2026-01-19T09:30:00-05:00
Running strategies...
Placing orders...
```

Loop runs normally every 5 minutes until 4:00 PM.

## Troubleshooting

**"Access is denied" error:**
- You didn't run as Administrator
- Right-click the file/PowerShell → "Run as administrator"

**Task still shows old settings:**
- Run: `(Get-ScheduledTask -TaskName "AITrader-Loop").Actions.Arguments`
- Should show: `-WindowStyle Hidden` and `SleepSeconds 300`
- If not, try Option 2 above

**Pop-ups still appearing:**
- Check task arguments include `-WindowStyle Hidden`
- Make sure you started the task AFTER updating it
- Old loop process might still be running: `taskkill /F /IM python.exe`

## Files Created

1. **update_task_hidden.cmd** - Double-click to update (easiest)
2. **update_task_now.ps1** - PowerShell version
3. **TASK_UPDATE_INSTRUCTIONS.md** (this file)

## Quick Start Summary

1. **Stop old loop** (if running): `schtasks /End /TN "AITrader-Loop"` ✅ DONE
2. **Update task** (as admin): Double-click `update_task_hidden.cmd` → Run as administrator
3. **Start loop**: `schtasks /Run /TN "AITrader-Loop"`
4. **Verify**: No pop-ups, check `logs\loop_status.log`

That's it! The loop will now run invisibly in the background, only during market hours.
