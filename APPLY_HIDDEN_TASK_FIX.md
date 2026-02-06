# Apply Hidden Task Fix

## Immediate Fix Applied ✓
The weekend exit check is now active. The loop will **exit immediately** on Saturdays and Sundays before any windows can appear.

## Complete Fix (Requires Admin)

To completely hide the task and prevent all popups:

### Option 1: Re-run Setup Script (Recommended)
```powershell
# Right-click PowerShell -> Run as Administrator
cd C:\dev\ai-trader
.\tools\windows\setup_market_hours_task.ps1 -Mode paper -SleepSeconds 600
```

### Option 2: Quick Update Script
```cmd
# Right-click update_task_to_hidden.cmd -> Run as Administrator
C:\dev\ai-trader\update_task_to_hidden.cmd
```

### Option 3: Manual schtasks Command
```cmd
# Run Command Prompt as Administrator
cd C:\dev\ai-trader
schtasks /Query /TN "AITrader-Loop" /XML > "%TEMP%\task.xml"
powershell -Command "(Get-Content '%TEMP%\task.xml') -replace '<Hidden>false</Hidden>', '<Hidden>true</Hidden>' | Set-Content '%TEMP%\task-hidden.xml'"
schtasks /Delete /TN "AITrader-Loop" /F
schtasks /Create /TN "AITrader-Loop" /XML "%TEMP%\task-hidden.xml"
```

## Verify the Fix
After running one of the above:
```powershell
Get-ScheduledTask -TaskName 'AITrader-Loop' | Select-Object -ExpandProperty Settings | Select-Object Hidden
```

Should show: `Hidden: True`

## What Was Fixed

1. **Weekend Exit Check** (Active Now)
   - Script exits immediately on Sat/Sun
   - No execution = No popups on weekends
   - Works without admin rights

2. **Task Hidden Setting** (Requires Admin)
   - Hides task from Task Scheduler UI
   - Prevents Windows from showing task notifications
   - Eliminates popup windows completely

## Current Status

✓ Weekend protection: **ACTIVE** (no admin needed)
⏳ Task hidden: **Requires admin command above**
