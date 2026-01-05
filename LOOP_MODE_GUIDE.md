# Loop Mode Setup Guide

This guide explains how to run the AI Trader in continuous hourly loop mode with equity-based allocation.

## Quick Start

### Option 1: Simple Batch File (Easiest)

Double-click the batch file:
```
start_loop_mode.cmd
```

This will:
- ✅ Run paper trading with equity-based allocation
- ✅ Execute strategies every hour (3600 seconds)
- ✅ Show output in the terminal window
- ✅ Stop when you press Ctrl+C or close the window

### Option 2: PowerShell (More Features)

**Foreground mode** (see output, press Ctrl+C to stop):
```powershell
powershell -ExecutionPolicy Bypass -File start_loop_mode.ps1
```

**Background mode** (runs detached, survives terminal close):
```powershell
powershell -ExecutionPolicy Bypass -File start_loop_mode.ps1 -Background
```

**Custom interval** (e.g., every 30 minutes = 1800 seconds):
```powershell
powershell -ExecutionPolicy Bypass -File start_loop_mode.ps1 -SleepSeconds 1800
```

**Dry-run mode** (simulate without placing orders):
```powershell
powershell -ExecutionPolicy Bypass -File start_loop_mode.ps1 -DryRun
```

## What Happens in Loop Mode

### Each Hour, the Bot Will:

1. **Initialize** registry with latest strategy configurations
2. **Fetch market data** from Alpaca (IEX feed)
3. **Generate signals** from all enabled strategies:
   - Trend_MA20 (36.2% of equity)
   - MeanRev_Z1.0 (31.9% of equity)
   - Momentum_MACD (31.9% of equity)
4. **Allocate capital** using equity-based allocation:
   - Fetch account equity from Alpaca (~$100k)
   - Normalize strategy weights (sum to 1.0)
   - Compute per-strategy budgets
   - Net conflicting multi-strategy intents
5. **Execute orders** with risk limits:
   - Max order size: $100
   - Max daily loss: $250
   - Reconcile current vs target positions
6. **Sleep** for 3600 seconds (1 hour)
7. **Repeat** from step 1

### Output Logs

All runs are logged to timestamped files:

| File | Description |
|------|-------------|
| `logs/loop_status.log` | High-level status (SUCCESS/ERROR) per iteration |
| `logs/loop_errors.log` | Detailed error messages if failures occur |
| `logs/paper_run_YYYYMMDD_HHMMSS_ET.jsonl` | Full trade results (JSON lines) |

## Monitoring Loop Mode

### View Real-Time Status

PowerShell:
```powershell
Get-Content logs\loop_status.log -Tail 20 -Wait
```

Bash:
```bash
tail -f logs/loop_status.log
```

### Check Account Status

```bash
.venv/Scripts/python.exe -c "
from dotenv import load_dotenv
load_dotenv(override=True)
import os
from alpaca.trading.client import TradingClient

client = TradingClient(
    os.getenv('ALPACA_PAPER_KEY_ID'),
    os.getenv('ALPACA_PAPER_SECRET_KEY'),
    paper=True
)

account = client.get_account()
print(f'Equity: \${float(account.equity):,.2f}')
print(f'Cash: \${float(account.cash):,.2f}')
print(f'Positions: {len(client.get_all_positions())}')
"
```

## Stopping Loop Mode

### Foreground Mode
- Press `Ctrl+C` in the terminal window
- Or close the terminal window

### Background Mode
1. Find the process ID from startup message
2. Stop it:
   ```powershell
   Stop-Process -Id <PID>
   ```

Or stop all Python processes running the trader:
```powershell
Get-Process python | Where-Object {$_.CommandLine -like "*src.app.runner*"} | Stop-Process
```

## Option 3: Windows Task Scheduler (Advanced)

For fully automated 24/7 operation with auto-restart on failure:

### Setup (requires Administrator)
```powershell
# Run PowerShell as Administrator, then:
cd C:\dev\ai-trader
powershell -ExecutionPolicy Bypass -File tools\setup_task_scheduler.ps1 -Mode paper
```

This creates a scheduled task that:
- ✅ Starts at 9:30 AM daily
- ✅ Repeats every hour for 23.5 hours
- ✅ Runs even if user is not logged in
- ✅ Auto-restarts on failure
- ✅ Only runs when network is available

### Remove Task
```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_task_scheduler.ps1 -Remove
```

## Safety Features

All loop modes include:

✅ **Single-instance guard**: Prevents duplicate runs
✅ **Equity-based allocation**: Sizes positions from actual account equity
✅ **Risk limits**: Max daily loss, max order size, max positions
✅ **Market hours check**: Only trades during configured hours
✅ **Dry-run testing**: Test without placing real orders
✅ **Comprehensive logging**: Full audit trail of all actions

## Troubleshooting

### Loop Stops After First Run
- Check `logs/loop_errors.log` for error messages
- Verify credentials are loaded correctly: `cat .env`
- Ensure `.env` has correct Alpaca paper credentials

### Orders Not Placing
- Verify equity-based allocation is active (check output)
- Check strategies are generating intents (see output)
- Verify risk limits aren't blocking orders

### Data API 401 Errors
- Ensure `.env` contains correct credentials
- Verify `load_dotenv(override=True)` in config.py
- Test credentials: `.venv/Scripts/python.exe test_alpaca_credentials.py`

## Example Output

```
================================================================================
LOOP ITERATION 1 - 2026-01-05T16:30:00-05:00
================================================================================

Allocating capital across strategies...
Account equity: $100,013.51
Allocation mode: EQUITY-BASED (normalized weights)

Strategy weights (normalized among 3 enabled):
  Trend_MA20: configured=0.340, normalized=0.362
  MeanRev_Z1.0: configured=0.300, normalized=0.319
  Momentum_MACD: configured=0.300, normalized=0.319

Strategy budgets:
  Trend_MA20: $36,175.05
  MeanRev_Z1.0: $31,919.16
  Momentum_MACD: $31,919.16

Target positions: {'AAPL': 1, 'SPY': 1}

Execution Summary:
Orders placed: 2
Orders skipped: 0
Total risk used: $199.83

Sleeping for 3600 seconds (1.0 hours)...
Next run at: 2026-01-05 17:30:00 EST
```

## Next Steps

1. **Test in dry-run mode first**:
   ```
   start_loop_mode.cmd  # Edit to add --dry-run flag
   ```

2. **Monitor first few iterations**:
   ```powershell
   Get-Content logs\loop_status.log -Tail 20 -Wait
   ```

3. **When satisfied, run for real**:
   ```
   start_loop_mode.cmd  # Remove --dry-run flag
   ```

4. **Consider Task Scheduler for 24/7 automation**

Enjoy automated equity-based trading! 🚀
