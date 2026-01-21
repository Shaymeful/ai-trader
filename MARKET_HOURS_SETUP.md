# Market Hours Automation Setup

This document explains how to configure the AI Trader to run automatically during market hours with no manual intervention.

## Quick Start

**Run this command as Administrator:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\setup_market_hours_task.ps1
```

This will configure the loop to:
- ✅ Start automatically at **9:30 AM ET** every weekday
- ✅ Stop automatically at **4:00 PM ET** every weekday
- ✅ Run with **hidden window** (no popups)
- ✅ Log all activity to `logs/loop/loop_YYYYMMDD.log`
- ✅ Use **5-minute intervals** by default

## What Got Fixed

### 1. PowerShell Window Hiding ✅
**Commit:** 02a3056

The `start_loop.ps1` script now detects when running from Task Scheduler and automatically:
- Uses `-WindowStyle Hidden` to prevent PowerShell window popup
- Uses `Start-Process` with hidden window for Python subprocess
- Logs output to file instead of console

**How it works:**
```powershell
$IsScheduledTask = -not [Environment]::UserInteractive

if ($IsScheduledTask -or $env:HIDE_PYTHON_WINDOW -eq "1") {
    # Use hidden window for both PowerShell and Python
    $ProcessArgs = @{
        FilePath = $PythonExe
        ArgumentList = $Args
        WindowStyle = 'Hidden'  # 👈 No window popup
        Wait = $true
        PassThru = $true
    }
    $Process = Start-Process @ProcessArgs
}
```

### 2. Market Hours Automation 🆕
**New feature**

The `setup_market_hours_task.ps1` script configures Task Scheduler to:
- Run Monday-Friday only (skips weekends)
- Start at 9:30 AM ET (market open)
- Stop at 4:00 PM ET via 7-hour timeout (6.5 hours from open to close + buffer)
- Automatically repeat every weekday

## Customization

### Change the Loop Interval
```powershell
# Run every 10 minutes instead of 5
powershell -ExecutionPolicy Bypass -File tools\windows\setup_market_hours_task.ps1 -SleepSeconds 600
```

### Change Trading Mode
```powershell
# Run in shadow mode (read-only)
powershell -ExecutionPolicy Bypass -File tools\windows\setup_market_hours_task.ps1 -Mode shadow
```

### Combined
```powershell
# Shadow mode with 15-minute intervals
powershell -ExecutionPolicy Bypass -File tools\windows\setup_market_hours_task.ps1 -Mode shadow -SleepSeconds 900
```

## Manual Controls

### Start the loop now (without waiting for 9:30 AM)
```powershell
Start-ScheduledTask -TaskName "AITrader-Loop"
```

### Stop the loop
```powershell
Stop-ScheduledTask -TaskName "AITrader-Loop"
```

### Check task status
```powershell
Get-ScheduledTask -TaskName "AITrader-Loop" | Format-List
Get-ScheduledTaskInfo -TaskName "AITrader-Loop" | Format-List
```

### View logs (live tail)
```powershell
Get-Content logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log -Tail 50 -Wait
```

### View logs (last 100 lines)
```powershell
Get-Content logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log -Tail 100
```

## Verification

After running the setup script, verify it's configured correctly:

1. **Check next run time:**
   ```powershell
   (Get-ScheduledTaskInfo -TaskName "AITrader-Loop").NextRunTime
   ```
   Should show tomorrow at 9:30 AM if after market hours, or next weekday if weekend.

2. **Check task configuration:**
   ```powershell
   Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object TaskName, State, @{N='NextRun';E={(Get-ScheduledTaskInfo -InputObject $_).NextRunTime}}
   ```

3. **Test hidden window (optional):**
   ```powershell
   Start-ScheduledTask -TaskName "AITrader-Loop"
   # Watch for 30 seconds - you should NOT see any PowerShell or Python windows
   # Check logs to verify it's running:
   Get-Content logs\loop\loop_$(Get-Date -Format 'yyyyMMdd').log -Tail 20
   # Stop it:
   Stop-ScheduledTask -TaskName "AITrader-Loop"
   ```

## Troubleshooting

### Loop not starting at 9:30 AM
Check if task is enabled:
```powershell
(Get-ScheduledTask -TaskName "AITrader-Loop").State
# Should show "Ready"
```

If disabled, enable it:
```powershell
Enable-ScheduledTask -TaskName "AITrader-Loop"
```

### Still seeing PowerShell windows
1. Verify you're running via Task Scheduler (not manually)
2. Check that `HIDE_PYTHON_WINDOW=1` environment variable is set in task
3. Run the setup script again to ensure latest configuration

### Loop not stopping at 4:00 PM
The task has a 7-hour execution limit which stops it automatically.
If it's still running after 4:00 PM:
```powershell
Stop-ScheduledTask -TaskName "AITrader-Loop"
```

### Market holidays
The current setup does NOT skip market holidays. The loop will start but:
- Alpaca broker will reject orders (market closed)
- Loop will run in dry-run mode effectively

**Future enhancement:** Add holiday calendar checking to start_loop.ps1

## How It Works

```
9:30 AM ET ────────────────────────────────────> 4:00 PM ET
    │                                                   │
    │  Task Scheduler triggers start                   │
    │  └─> start_loop.ps1                              │
    │      └─> python -m src.app.runner --loop         │
    │          └─> Runs continuously                   │
    │              └─> Fetches data every 5 min        │
    │                  └─> Generates orders            │
    │                      └─> Executes trades         │
    │                                                   │
    └───────────────────────────────────────────────────┘
                    7-hour timeout stops loop
```

## Files Modified

- `tools/windows/start_loop.ps1` - Added Task Scheduler detection and hidden window support (02a3056)
- `tools/windows/setup_market_hours_task.ps1` - New script for market hours automation
- `src/app/market_hours.py` - Market hours utilities (already existed)

## Next Steps

After setup is complete:
1. ✅ Loop will start automatically tomorrow at 9:30 AM
2. ✅ No manual intervention needed
3. ✅ Check logs daily to verify successful runs
4. ✅ Monitor dashboard at http://localhost:8001

**Your trading bot is now fully automated for market hours! 🎉**
