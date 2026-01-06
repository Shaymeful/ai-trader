# AI Trader Loop Mode Guide

## Overview

Loop mode enables continuous automated trading throughout the trading day. The bot runs in a loop, periodically fetching candidates from the selector, analyzing positions, and placing orders.

**Key Features:**
- Continuous operation with configurable sleep intervals
- Integration with RSS selector for candidate generation
- Windows Task Scheduler support for morning auto-start
- Safety controls (pause_trading.flag, dry-run mode)
- Comprehensive logging and monitoring

## Architecture

```
Morning Startup (Automated)
    ↓
8:45 AM: Dashboard starts (monitoring UI)
    ↓
8:50 AM: Selector starts (every 15 min)
    ↓
9:00 AM: Trading Loop starts (hourly)
    ↓
Loop Iteration:
    1. Read snapshot.json (candidates)
    2. Check pause_trading.flag
    3. Analyze positions & risk
    4. Generate orders
    5. Submit orders (via RiskManager)
    6. Log activity
    7. Sleep (default: 1 hour)
    ↓
Repeat until market close
```

## Windows Task Scheduler Setup

### Installation

**Prerequisites:**
- Windows 10/11
- Administrator privileges
- Virtual environment configured (`.venv`)
- RSS feeds configured in `config/selector.yaml`

**Install all tasks:**
```powershell
# Open PowerShell as Administrator
cd C:\dev\ai-trader
.\tools\windows\install_tasks.ps1
```

**Install with safety options:**
```powershell
# Install with pause_trading.flag for safe warm start
.\tools\windows\install_tasks.ps1 -CreatePauseFlag

# Install with dry-run mode (no real orders)
.\tools\windows\install_tasks.ps1 -DryRun

# Install in shadow mode (market data only)
.\tools\windows\install_tasks.ps1 -Mode shadow
```

### Scheduled Tasks Created

| Task Name | Schedule | Purpose |
|-----------|----------|---------|
| **AITrader-Dashboard** | Daily 8:45 AM | Starts monitoring dashboard |
| **AITrader-Selector** | Every 15 min, 8:50 AM - 4:10 PM | Generates candidates from RSS feeds |
| **AITrader-Loop** | Daily 9:00 AM, repeats hourly | Processes candidates and places orders |

### Task Management

**View tasks:**
```powershell
Get-ScheduledTask -TaskName "AITrader-*"
```

**Start task manually:**
```powershell
Start-ScheduledTask -TaskName "AITrader-Loop"
```

**Stop running task:**
```powershell
Stop-ScheduledTask -TaskName "AITrader-Loop"
```

**Remove all tasks:**
```powershell
.\tools\windows\install_tasks.ps1 -Remove
```

**Remove specific task:**
```powershell
.\tools\windows\install_tasks.ps1 -RemoveTask Selector
```

## Safe Morning Startup Sequence

### Default Sequence (Safe)

1. **8:45 AM**: Dashboard starts
   - Provides monitoring UI at `http://localhost:8000`
   - Shows bot status, selector status, loop controls

2. **8:50 AM**: Selector starts (first run)
   - Fetches RSS feeds
   - Generates candidates → `out/selector/snapshot.json`
   - Repeats every 15 minutes

3. **9:00 AM**: Trading loop starts
   - Reads candidates from snapshot
   - Checks `pause_trading.flag`
   - If paused: Runs in DryRun mode (no orders)
   - If not paused: Places real orders

### Recommended: Safe Warm Start

**Use `pause_trading.flag` to prevent immediate trading:**

```powershell
# Install tasks with pause flag
.\tools\windows\install_tasks.ps1 -CreatePauseFlag
```

This creates `state/pause_trading.flag` on startup, preventing live orders until you're ready.

**Morning routine:**
1. **9:00 AM**: Loop starts (paused, dry-run mode)
2. **9:05-9:25 AM**: Review dashboard:
   - Check selector candidates: `http://localhost:8000/selector/status`
   - Check bot status: `http://localhost:8000/status`
   - Review logs: `logs/loop/loop_YYYYMMDD.log`
3. **9:30 AM** (market open): If everything looks good:
   ```powershell
   Remove-Item state\pause_trading.flag
   ```
4. Loop detects flag removal and enables live trading

### Emergency Stop

**Immediately stop all trading:**
```powershell
# Create pause flag
"" | Out-File -FilePath state\pause_trading.flag -Encoding utf8

# Or stop the loop task
Stop-ScheduledTask -TaskName "AITrader-Loop"
```

## Manual Execution

### Dashboard

```powershell
.\tools\windows\start_dashboard.ps1
```

Access at: `http://localhost:8000`

**Custom port:**
```powershell
.\tools\windows\start_dashboard.ps1 -Port 8080
```

### Selector

```powershell
.\tools\windows\run_selector.ps1
```

**With logging:**
```powershell
.\tools\windows\run_selector.ps1 -LogToFile
# Output: logs/selector/selector_YYYYMMDD.log
```

### Loop

```powershell
.\tools\windows\start_loop.ps1
```

**Options:**
```powershell
# Dry-run mode (no orders)
.\tools\windows\start_loop.ps1 -DryRun

# Shadow mode (market data only)
.\tools\windows\start_loop.ps1 -Mode shadow

# Custom sleep interval (30 minutes)
.\tools\windows\start_loop.ps1 -SleepSeconds 1800

# With logging
.\tools\windows\start_loop.ps1 -LogToFile

# Safe warm start (creates pause flag)
.\tools\windows\start_loop.ps1 -CreatePauseFlag
```

## Configuration

### Loop Parameters

**Mode:**
- `shadow`: Market data only, no orders
- `paper`: Paper trading (default)

**Dry-Run:**
- `--dry-run`: Simulates orders without submitting

**Sleep Interval:**
- `--sleep-seconds 3600`: Sleep 1 hour between iterations (default)
- `--sleep-seconds 1800`: Sleep 30 minutes (more frequent)
- `--sleep-seconds 7200`: Sleep 2 hours (less frequent)

### Selector Configuration

Edit `config/selector.yaml`:

**RSS Feeds:**
```yaml
rss_feeds:
  - https://seekingalpha.com/sector/industrials.xml
  - https://www.oilprice.com/rss/main
```

**Confidence Thresholds:**
```yaml
defaults:
  min_confidence: 0.60  # Minimum confidence to generate candidate
```

**Candidate TTL:**
```yaml
defaults:
  ttl_minutes_buy: 180   # Buy candidates expire after 3 hours
  ttl_minutes_sell: 120  # Sell candidates expire after 2 hours
  ttl_minutes_watch: 240 # Watch candidates expire after 4 hours
```

### Risk Configuration

Edit `config/risk.yaml` (if exists) or environment variables:

```bash
# Position sizing
MAX_POSITIONS=5
POSITION_SIZE=0.20  # 20% of portfolio per position

# Daily loss limit
MAX_DAILY_LOSS=500.00
```

## Monitoring

### Dashboard

**Main dashboard:**
```
http://localhost:8000
```

**Selector status:**
```
http://localhost:8000/selector/status
```

**Response:**
```json
{
  "last_run": "2026-01-05T10:00:00-05:00",
  "candidates_count": 5,
  "candidates_by_action": {
    "buy": 2,
    "sell": 1,
    "watch": 2
  },
  "last_error": null
}
```

### Logs

**Loop logs:**
```
logs/loop/loop_YYYYMMDD.log
```

**Selector logs:**
```
logs/selector/selector_YYYYMMDD.log
```

**Task Scheduler logs:**
```
logs/task_scheduler.log
```

**View recent loop activity:**
```powershell
Get-Content logs\loop\loop_20260105.log -Tail 50
```

**Monitor selector runs:**
```powershell
Get-Content logs\selector\selector_20260105.log -Tail 50
```

### Snapshot Files

**Current candidates:**
```bash
cat out/selector/snapshot.json
```

**Selector events:**
```bash
tail -20 out/selector/events.jsonl
```

## Troubleshooting

### Loop Not Starting

**Check task status:**
```powershell
Get-ScheduledTask -TaskName "AITrader-Loop" | Select-Object State, LastRunTime, LastTaskResult
```

**Common issues:**
1. **Task disabled**: Enable task in Task Scheduler
2. **Script not found**: Verify `tools\windows\start_loop.ps1` exists
3. **Virtual environment missing**: Ensure `.venv` is configured
4. **Permissions**: Run installation as Administrator

**Manual test:**
```powershell
.\tools\windows\start_loop.ps1 -DryRun
```

### No Candidates Generated

**Check selector status:**
```
http://localhost:8000/selector/status
```

**Diagnose:**
1. **RSS feeds configured?**
   ```bash
   cat config/selector.yaml | grep -A 5 "rss_feeds"
   ```

2. **Selector running?**
   ```powershell
   Get-ScheduledTask -TaskName "AITrader-Selector" | Select-Object State, LastRunTime
   ```

3. **Check selector logs:**
   ```powershell
   Get-Content logs\selector\selector_20260105.log
   ```

**Manual test:**
```powershell
.\tools\windows\run_selector.ps1
```

### Orders Not Placed

**Possible causes:**

1. **pause_trading.flag exists:**
   ```powershell
   Test-Path state\pause_trading.flag  # Should be False
   ```
   Solution: Remove flag if ready to trade

2. **Dry-run mode enabled:**
   Check task configuration - was it installed with `-DryRun`?

3. **No candidates in snapshot:**
   ```bash
   cat out/selector/snapshot.json
   ```

4. **Risk limits exceeded:**
   - Check daily loss limit
   - Check max positions limit
   - Review logs for "REJECTED" messages

5. **Candidates expired:**
   Candidates have TTL (time-to-live). Check `expires_at` field.

### Dashboard Not Accessible

**Check if dashboard is running:**
```powershell
Get-ScheduledTask -TaskName "AITrader-Dashboard" | Select-Object State
```

**Check port availability:**
```powershell
netstat -ano | findstr :8000
```

**Manual start:**
```powershell
.\tools\windows\start_dashboard.ps1
```

**Access:**
```
http://localhost:8000
```

### High CPU or Memory Usage

**Identify process:**
```powershell
Get-Process python | Sort-Object CPU -Descending | Select-Object -First 5
```

**Check loop sleep interval:**
- Default: 3600 seconds (1 hour)
- If too frequent, increase sleep interval

**Restart tasks:**
```powershell
Stop-ScheduledTask -TaskName "AITrader-Loop"
Start-ScheduledTask -TaskName "AITrader-Loop"
```

## Integration with Selector

### How Loop Uses Candidates

1. **Loop iteration starts**
2. **Reads `out/selector/snapshot.json`**
3. **Filters expired candidates** (based on `expires_at`)
4. **Sorts by confidence** (highest first)
5. **Checks risk constraints:**
   - Max positions
   - Daily loss limit
   - Position sizing
6. **Generates orders** for top candidates
7. **Submits orders** (if not paused)

### Candidate Priority

**Factors:**
1. **Action**: Sell > Buy > Watch (sell signals prioritized for risk management)
2. **Confidence**: Higher confidence = higher priority
3. **Sector**: Both automation and energy treated equally
4. **Symbol presence**: Candidates with symbols preferred over null symbols

### Candidate Expiration

Candidates expire after TTL:
- **Buy**: 180 minutes (3 hours)
- **Sell**: 120 minutes (2 hours)
- **Watch**: 240 minutes (4 hours)

Expired candidates are automatically filtered out by the loop.

## Best Practices

### 1. Start with Dry-Run

```powershell
.\tools\windows\install_tasks.ps1 -DryRun
```

Run for a few days to verify behavior before enabling live trading.

### 2. Use Pause Flag for Warm Start

```powershell
.\tools\windows\install_tasks.ps1 -CreatePauseFlag
```

Review candidates and system status before removing the pause flag.

### 3. Monitor Daily

**Morning routine (9:00-9:30 AM):**
1. Check dashboard: `http://localhost:8000`
2. Review selector candidates
3. Check logs for errors
4. Verify positions and orders

**End of day routine (4:00-4:30 PM):**
1. Review trading activity
2. Check PnL and risk metrics
3. Archive logs if needed

### 4. Configure RSS Feeds Carefully

- Use reputable sources (Seeking Alpha, Yahoo Finance, etc.)
- Test feeds manually before adding to config
- Monitor selector logs for fetch errors

### 5. Set Conservative Risk Limits

```yaml
# Example conservative settings
MAX_POSITIONS: 3
POSITION_SIZE: 0.15  # 15% per position
MAX_DAILY_LOSS: 300.00
```

### 6. Regular Backups

Backup critical files:
- `config/selector.yaml`
- `state/bot_state.json`
- `logs/*.log` (weekly archive)

### 7. Test Changes in Shadow Mode

Before deploying changes:
```powershell
.\tools\windows\start_loop.ps1 -Mode shadow
```

Verify behavior without placing orders.

## Advanced Usage

### Custom Scheduled Times

**Modify trigger in Task Scheduler:**
1. Open Task Scheduler
2. Find task (e.g., `AITrader-Loop`)
3. Edit trigger → Change start time or repetition interval

**Or recreate task with custom times:**
```powershell
# Remove existing task
.\tools\windows\install_tasks.ps1 -RemoveTask Loop

# Manually create with custom schedule using New-ScheduledTask
```

### Multiple Instances

**WARNING**: Multiple loop instances can cause conflicts.

If you need multiple strategies:
1. Use separate repositories
2. Different ports for dashboards
3. Different state directories

### Remote Monitoring

**Expose dashboard on network:**
```powershell
.\tools\windows\start_dashboard.ps1 -Port 8000
# Dashboard accessible at http://<your-ip>:8000
```

**Security considerations:**
- Use firewall rules
- Consider VPN access
- Enable authentication (future feature)

## FAQ

**Q: What happens if the machine reboots?**
A: Scheduled tasks will restart on next scheduled time. Use Task Scheduler option "Start when available" to run immediately if missed.

**Q: Can I run the loop 24/7?**
A: The loop respects market hours. Outside market hours, it will still run but may not place orders depending on broker availability.

**Q: How do I change the sleep interval?**
A: Recreate the task with different `-SleepSeconds` parameter, or edit the task action in Task Scheduler.

**Q: Can I use this on Linux/Mac?**
A: The PowerShell scripts are Windows-specific. For Linux/Mac, use cron jobs with equivalent bash scripts.

**Q: What if selector and loop run at the same time?**
A: This is safe. Selector writes to `snapshot.json` atomically, and loop reads it. No conflicts.

**Q: How do I test without scheduled tasks?**
A: Run scripts manually:
```powershell
.\tools\windows\start_dashboard.ps1
.\tools\windows\run_selector.ps1
.\tools\windows\start_loop.ps1 -DryRun
```

**Q: Can I modify candidates after selector generates them?**
A: Yes. Edit `out/selector/snapshot.json` manually before loop runs. Useful for testing.

**Q: How do I know if loop is paused?**
A: Check for `state/pause_trading.flag`. If file exists, loop is paused.

**Q: What's the difference between DryRun and pause_trading.flag?**
A:
- **DryRun**: Loop simulates orders but doesn't submit (logs "would place order")
- **pause_trading.flag**: Loop skips order generation entirely (logs "trading paused")

## Next Steps

1. **Install scheduled tasks**: `.\tools\windows\install_tasks.ps1 -CreatePauseFlag`
2. **Configure RSS feeds**: Edit `config/selector.yaml`
3. **Test manually**:
   ```powershell
   .\tools\windows\run_selector.ps1
   .\tools\windows\start_dashboard.ps1
   .\tools\windows\start_loop.ps1 -DryRun
   ```
4. **Monitor first run**: Check dashboard and logs
5. **Enable live trading**: Remove `state/pause_trading.flag` when ready

## Related Documentation

- `docs/SELECTOR.md` - RSS selector configuration and usage
- `docs/ARCHITECTURE.md` - Overall system architecture
- `config/selector.yaml` - Selector configuration
- `CLAUDE.md` - Repository rules and guidelines
