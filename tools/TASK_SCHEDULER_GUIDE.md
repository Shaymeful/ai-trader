# Windows Task Scheduler Setup Guide

This guide shows how to set up the AI Trader to run automatically every hour using Windows Task Scheduler.

## Quick Setup (Recommended)

### 1. Run Setup Script as Administrator

```powershell
# Open PowerShell as Administrator
# Navigate to project root
cd C:\dev\ai-trader

# Run setup script (shadow mode, default)
.\tools\setup_task_scheduler.ps1

# OR: Paper mode with dry-run
.\tools\setup_task_scheduler.ps1 -Mode paper -DryRun

# OR: Custom task name and start time
.\tools\setup_task_scheduler.ps1 -TaskName "AI-Trader-Market-Hours" -StartTime "09:30"
```

### 2. Test the Task

```powershell
# Start the task manually to test
Start-ScheduledTask -TaskName "AI-Trader-Hourly"

# Monitor logs (Ctrl+C to stop)
Get-Content logs\loop_status.log -Tail 10 -Wait

# Stop the task
Stop-ScheduledTask -TaskName "AI-Trader-Hourly"
```

### 3. Remove the Task (if needed)

```powershell
# Remove the task
.\tools\setup_task_scheduler.ps1 -Remove
```

---

## Manual Setup (Advanced)

If you prefer to set up the task manually:

### Step 1: Open Task Scheduler

1. Press `Win + R`
2. Type `taskschd.msc`
3. Press Enter

### Step 2: Create Basic Task

1. Click "Create Basic Task..." in the Actions pane
2. Name: `AI-Trader-Hourly`
3. Description: `AI Trader hourly loop runner`
4. Click "Next"

### Step 3: Configure Trigger

1. Select "Daily"
2. Click "Next"
3. Start time: `09:30:00` (market open)
4. Recur every: `1` day
5. Click "Next"

### Step 4: Configure Action

1. Select "Start a program"
2. Click "Next"
3. Program/script: `PowerShell.exe`
4. Add arguments:
   ```
   -NoProfile -ExecutionPolicy Bypass -File "C:\dev\ai-trader\tools\run_loop.ps1" -Mode shadow -SleepSeconds 3600
   ```
5. Start in: `C:\dev\ai-trader`
6. Click "Next"

### Step 5: Configure Advanced Settings

1. Check "Open the Properties dialog..."
2. Click "Finish"

In Properties dialog:

**General Tab:**
- Run whether user is logged on or not: ✓
- Run with highest privileges: ✓

**Triggers Tab:**
- Click "Edit"
- Check "Repeat task every: 1 hour"
- For a duration of: 23 hours 30 minutes
- Check "Enabled"
- Click "OK"

**Settings Tab:**
- Allow task to be run on demand: ✓
- Run task as soon as possible after scheduled start is missed: ✓
- If task fails, restart every: 10 minutes (attempt 3 times)
- Stop task if runs longer than: 1 day
- If running task does not end when requested: Stop the existing instance

Click "OK" to save.

---

## Configuration Options

### Available Modes

```powershell
# Shadow mode (no orders, default)
.\tools\run_loop.ps1 -Mode shadow

# Paper mode (place orders on paper account)
.\tools\run_loop.ps1 -Mode paper

# Paper mode with dry-run (print orders only)
.\tools\run_loop.ps1 -Mode paper -DryRun
```

### Sleep Interval

```powershell
# Default: 1 hour (3600 seconds)
.\tools\run_loop.ps1 -SleepSeconds 3600

# Custom: 30 minutes
.\tools\run_loop.ps1 -SleepSeconds 1800

# Custom: 4 hours
.\tools\run_loop.ps1 -SleepSeconds 14400
```

---

## Log Files

All logs are written to the `logs/` directory:

| File | Description |
|------|-------------|
| `task_scheduler.log` | Task scheduler script logs (startup, shutdown) |
| `loop_status.log` | Loop iteration status (SUCCESS/ERROR per run) |
| `loop_errors.log` | Full stack traces when exceptions occur |
| `loop_stdout.log` | Standard output from Python runner |
| `loop_stderr.log` | Standard error from Python runner |

### Monitor Logs

```powershell
# View task scheduler log
Get-Content logs\task_scheduler.log -Tail 20

# Watch loop status in real-time
Get-Content logs\loop_status.log -Tail 10 -Wait

# Check for errors
Get-Content logs\loop_errors.log

# View last 5 iterations
Get-Content logs\loop_status.log -Tail 5
```

---

## Task Management

### View Task Status

```powershell
# Get task information
Get-ScheduledTask -TaskName "AI-Trader-Hourly"

# Get last run result
Get-ScheduledTask -TaskName "AI-Trader-Hourly" | Get-ScheduledTaskInfo
```

### Start/Stop Task

```powershell
# Start manually
Start-ScheduledTask -TaskName "AI-Trader-Hourly"

# Stop running task
Stop-ScheduledTask -TaskName "AI-Trader-Hourly"
```

### Enable/Disable Task

```powershell
# Disable (won't run on schedule)
Disable-ScheduledTask -TaskName "AI-Trader-Hourly"

# Enable
Enable-ScheduledTask -TaskName "AI-Trader-Hourly"
```

### Remove Task

```powershell
# Using setup script (recommended)
.\tools\setup_task_scheduler.ps1 -Remove

# Manual removal
Unregister-ScheduledTask -TaskName "AI-Trader-Hourly" -Confirm:$false
```

---

## Troubleshooting

### Task Not Starting

1. **Check task status:**
   ```powershell
   Get-ScheduledTask -TaskName "AI-Trader-Hourly" | Select-Object TaskName, State, LastRunTime, LastTaskResult
   ```

2. **Check task history:**
   - Open Task Scheduler GUI (`taskschd.msc`)
   - Find your task
   - Click "History" tab
   - Look for errors

3. **Verify environment variables:**
   ```powershell
   # Check if required env vars are set
   Get-ChildItem Env: | Where-Object { $_.Name -like "ALPACA_*" }
   ```

### Task Runs But Bot Fails

1. **Check loop error log:**
   ```powershell
   Get-Content logs\loop_errors.log
   ```

2. **Check stderr:**
   ```powershell
   Get-Content logs\loop_stderr.log
   ```

3. **Test manually:**
   ```powershell
   # Run directly to see errors
   python -m src.app.runner --mode shadow --loop --sleep-seconds 10
   ```

### Task Doesn't Run Hourly

1. **Check trigger configuration:**
   ```powershell
   Get-ScheduledTask -TaskName "AI-Trader-Hourly" | Select-Object -ExpandProperty Triggers
   ```

2. **Verify repetition settings:**
   - Open Task Scheduler GUI
   - Double-click task
   - Go to Triggers tab
   - Edit trigger
   - Ensure "Repeat task every: 1 hour" is checked

---

## Production Recommendations

### For Market Hours Only

Set up task to run during market hours only (9:30 AM - 4:00 PM ET):

```powershell
# Start at market open
.\tools\setup_task_scheduler.ps1 -StartTime "09:30"

# Manually set end time in Task Scheduler GUI:
# - Edit trigger
# - Set "Repeat task every: 1 hour"
# - Set "For a duration of: 6 hours 30 minutes"
```

### Environment Variables

Ensure environment variables are set system-wide (not just in your PowerShell session):

1. Open System Properties (`sysdm.cpl`)
2. Go to "Advanced" tab
3. Click "Environment Variables"
4. Add to "System variables" or "User variables":
   - `ALPACA_PAPER_KEY_ID`
   - `ALPACA_PAPER_SECRET_KEY`
   - (Optional) `ALPACA_LIVE_KEY_ID`, `ALPACA_LIVE_SECRET_KEY`

### Safety Settings

For production use:

- **Start with shadow mode** (no orders) to verify behavior
- **Use paper mode with --dry-run** before live trading
- **Monitor logs daily** for the first week
- **Set up alerts** for error logs (e.g., email on file change)
- **Test task manually** before relying on schedule

---

## Example Setup Scenarios

### Scenario 1: Development/Testing (Shadow Mode)

```powershell
# Run every hour in shadow mode (no orders)
.\tools\setup_task_scheduler.ps1 -Mode shadow -StartTime "00:00"
```

### Scenario 2: Paper Trading (Dry-Run)

```powershell
# Run every hour in paper mode with dry-run (print orders only)
.\tools\setup_task_scheduler.ps1 -Mode paper -DryRun -StartTime "09:30"
```

### Scenario 3: Paper Trading (Live Orders on Paper Account)

```powershell
# Run every hour in paper mode (place orders on paper account)
.\tools\setup_task_scheduler.ps1 -Mode paper -StartTime "09:30"
```

---

## Questions?

- See `docs/ARCHITECTURE.md` for detailed documentation
- Check `logs/loop_status.log` for execution history
- Review `tests/test_loop_runner.py` for expected behavior
