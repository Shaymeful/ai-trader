# Tomorrow Morning: Automated Trading Timeline

## 🕐 8:45 AM - Dashboard Startup

**Task:** AITrader-Dashboard
**Status:** Will start automatically via Windows Task Scheduler

### What Happens:
- FastAPI web server starts on port 8000
- Loads system health, strategies, and candidates
- Web interface becomes available at http://localhost:8000

### What You'll See:
✓ Dashboard web interface accessible
✓ System status shows: Market CLOSED (pre-market)
✓ All metrics and charts ready for monitoring
✓ 3 strategies enabled with weight allocation visible

---

## 🕐 8:50 AM - First Selector Run (+ Every 15 Minutes)

**Task:** AITrader-Selector
**Repeat:** Every 15 minutes until 4:10 PM (30 runs per day)

### What Happens:
1. **Fetches RSS feeds** from 5 sources:
   - Robotics & Automation News
   - Investing.com Stock Market News
   - Investing.com Energy Analysis
   - Investing.com Commodities & Futures News
   - EnergyWatch

2. **Parses headlines** for automation/energy keywords
   - Automation: robot, robotics, automation, PLC, industrial, manufacturing
   - Energy: oil, gas, solar, wind, nuclear, battery, renewable, utility

3. **Extracts stock symbols** using conservative patterns:
   - `(SYMBOL)` - e.g., "Tesla (TSLA) announces..."
   - `SYMBOL:` - e.g., "TSLA: Tesla expands..."
   - `$SYMBOL` - e.g., "Investors watch $TSLA..."

4. **Classifies sentiment** as BUY/SELL/WATCH:
   - BUY: beats, raises guidance, contract, record revenue, exceeds
   - SELL: misses, cuts guidance, lawsuit, bankruptcy, investigation
   - WATCH: neutral or sector news

5. **Computes confidence scores** (0.60-0.90):
   - Base: 0.55
   - +0.10 per strong keyword match
   - -0.15 if symbol uncertain
   - Clamped to [0.60, 0.90]

6. **Writes output**:
   - `out/selector/snapshot.json` - Current candidates
   - `out/selector/events.jsonl` - Event log (append-only)
   - `logs/selector/selector_YYYYMMDD.log` - Run log

### What You'll See:
✓ New candidates appear in dashboard Candidates section
✓ Selector status updates: "Last Run: 8:50 AM"
✓ Dashboard shows candidate count by action (BUY/SELL/WATCH)
✓ Candidate details: symbol, action, confidence, sector, reason, expiry

### Expected Output Per Run:
- **Headlines processed:** ~20-50 per run
- **Candidates generated:** ~0-5 per run (conservative extraction)
- **TTL (time-to-live):**
  - BUY candidates: 3 hours
  - SELL candidates: 2 hours
  - WATCH candidates: 4 hours

**Note:** Most RSS headlines don't include ticker symbols in `(SYMBOL)` format, so candidate generation rate is intentionally low for high precision.

---

## 🕐 9:00 AM - Trading Loop Startup (+ Hourly)

**Task:** AITrader-Loop
**Repeat:** Every 1 hour for 23.5 hours (8 runs during market hours)
**Mode:** PAPER (safe mode, no real money)

### What Happens:

1. **Pre-flight checks:**
   - Checks for `pause_trading.flag` (PAUSES if exists)
   - Verifies environment (Python venv, config files)
   - Connects to Alpaca Paper API

2. **Loads candidates:**
   - Reads `out/selector/snapshot.json`
   - Filters expired candidates
   - Validates schema and data quality

3. **Runs strategies (3 enabled):**
   - **Trend Following (MA20)** - 34% weight
     - SMA crossover with 10/20 periods
     - Max position: $5,000
     - Max positions: 3
   - **Mean Reversion (Z-Score 1.0)** - 30% weight
     - SMA crossover with 5/15 periods
     - Max position: $3,000
     - Max positions: 5
   - **Momentum (MACD-like)** - 30% weight
     - SMA crossover with 12/26 periods
     - Max position: $4,000
     - Max positions: 4

4. **Generates trading signals:**
   - Analyzes market data for each candidate symbol
   - Computes indicators (SMA, price trends)
   - Produces BUY/SELL signals with conviction scores

5. **Risk checks (CRITICAL):**
   - Daily loss limit: $1,000 max
   - Max total positions: 10
   - Max position notional: $3,000-$5,000 per strategy
   - Existing position checks (avoid over-concentration)

6. **Places orders (if risk checks pass):**
   - Submits orders to Alpaca Paper API
   - Logs order details to ledger
   - Writes to `out/YYYYMMDD_HHMMSS/trades.csv`

7. **Waits and repeats:**
   - Sleeps for 1 hour (3,600 seconds)
   - Loops back to step 1

### What You'll See:
✓ Dashboard shows: "Last Loop Tick: 9:00 AM"
✓ Activity feed updates with:
  - `signal_generated` events
  - `order_placed` events (if signals pass risk checks)
  - `fill` events (when orders execute)
✓ Status log updates: `logs/loop_status.log`
✓ Trade history: `out/YYYYMMDD_HHMMSS/trades.csv`
✓ Strategy metrics update (PnL, positions, orders)

### Risk Protection:
🛡️ **Max Daily Loss:** $1,000
🛡️ **Max Positions:** 10
🛡️ **Max Position Size:** $3,000-$5,000 per strategy
🛡️ **PAPER MODE:** No real money at risk
🛡️ **Kill Switch:** Pause trading flag/toggle

---

## 🕐 9:30 AM - Market Opens

**Action:**
- Dashboard updates: Market Status = OPEN 🟢
- Trading conditions checked
- Orders may be placed (if not paused)
- Loop continues hourly execution

---

## 📊 Throughout the Day (8:50 AM - 4:10 PM)

### Timeline:

| Time     | Event                          | Details                           |
|----------|--------------------------------|-----------------------------------|
| 8:45 AM  | Dashboard starts               | Web interface live                |
| 8:50 AM  | Selector run #1                | Fetch RSS, generate candidates    |
| 9:00 AM  | Loop tick #1                   | Pre-market, load candidates       |
| 9:05 AM  | Selector run #2                | +15 min                           |
| 9:20 AM  | Selector run #3                | +15 min                           |
| 9:30 AM  | **Market opens**               | Trading active                    |
| 9:35 AM  | Selector run #4                | +15 min                           |
| 9:50 AM  | Selector run #5                | +15 min                           |
| 10:00 AM | Loop tick #2                   | +1 hour                           |
| 10:05 AM | Selector run #6                | +15 min                           |
| ...      | ...                            | Continues every 15 min / 1 hour   |
| 11:00 AM | Loop tick #3                   | +1 hour                           |
| 12:00 PM | Loop tick #4                   | +1 hour                           |
| 1:00 PM  | Loop tick #5                   | +1 hour                           |
| 2:00 PM  | Loop tick #6                   | +1 hour                           |
| 3:00 PM  | Loop tick #7                   | +1 hour                           |
| 4:00 PM  | Loop tick #8, **Market closes**| Final trading tick                |
| 4:10 PM  | Selector final run             | Last RSS fetch of the day         |

### Total Runs Per Day:
- **Selector:** ~30 runs (every 15 min × 7.33 hours)
- **Loop:** ~8 runs (hourly from 9 AM to 4 PM)

---

## 🔔 Monitoring & Alerts

### Dashboard (http://localhost:8000):
- Real-time system health
- Current candidates list with filters
- Strategy performance metrics
- Activity feed (last 20 events)
- Trading pause control (emergency stop)

### Log Files:
- **Dashboard:** Background task (view via TaskOutput or logs)
- **Selector:** `logs/selector/selector_YYYYMMDD.log`
- **Loop:** `logs/loop_status.log`
- **Events:** `out/selector/events.jsonl`

### Safety Features:
⏸️ **pause_trading.flag** - Emergency stop (create to pause)
🛡️ **Daily loss limit** - $1,000 max
🛡️ **Position limits** - Max 10 positions
📋 **Paper mode** - No real money
✋ **Manual override** - Via dashboard toggle

---

## 🎯 Expected First-Day Results

### Candidates Generated (by 4:10 PM):
- **Typical:** 5-15 candidates total
- **Distribution:** ~20% BUY, ~10% SELL, ~70% WATCH
- **Sectors:** automation, energy
- **Quality:** High precision (conservative extraction)

### Trading Activity (if not paused):
- **Signals:** 2-10 signals generated
- **Orders:** 1-5 orders placed (after risk checks)
- **Positions:** 0-3 positions opened
- **Capital used:** ~$5,000-$15,000 (paper money)

**Note:** Conservative symbol extraction means fewer but higher-quality candidates. Most RSS headlines don't include ticker symbols in `(SYMBOL)` format, so candidate rate is intentionally low.

---

## 🚀 How to Prepare

### Optional: Create Pause Flag for Safe Warm Start
```cmd
powershell -ExecutionPolicy Bypass -File tools/windows/start_loop.ps1 -CreatePauseFlag
```

This creates `pause_trading.flag` which will prevent the loop from placing orders tomorrow morning. You can remove it when ready.

### To Disable Pause Tomorrow Morning:

**Option 1: Via Dashboard**
1. Open dashboard: http://localhost:8000
2. Toggle "Pause Trading" switch OFF

**Option 2: Via File System**
```cmd
del pause_trading.flag
```

### To Monitor in Real-Time:
- Keep dashboard open in browser tab
- Refresh periodically or use "Refresh Now" button
- Check Activity feed for recent events
- Monitor Candidates section for new opportunities

---

## 📝 Quick Reference Commands

### Check Task Status:
```cmd
schtasks /query /tn "AITrader-Dashboard" /fo LIST
schtasks /query /tn "AITrader-Selector" /fo LIST
schtasks /query /tn "AITrader-Loop" /fo LIST
```

### Manual Testing (Before Tomorrow):
```cmd
# Test selector
.venv\Scripts\python.exe -m src.app.selector.run_once

# Test loop (dry-run)
.venv\Scripts\python.exe -m src.app -m paper --dry-run --once
```

### View Logs:
```cmd
# Selector logs
type logs\selector\selector_YYYYMMDD.log

# Loop status
type logs\loop_status.log

# Selector events
type out\selector\events.jsonl
```

### Emergency Stop:
```cmd
# Create pause flag
echo. > pause_trading.flag

# Or stop tasks
schtasks /End /TN "AITrader-Loop"
schtasks /End /TN "AITrader-Selector"
```

---

## ✅ System Readiness Checklist

- [x] Windows Task Scheduler tasks installed (3/3)
- [x] RSS feeds configured (5 feeds)
- [x] Strategies enabled (3/3)
- [x] Risk limits configured
- [x] Dashboard tested and working
- [x] Selector tested with real feeds
- [x] Paper mode verified
- [x] All tests passing (484/484)

**Status:** ✅ Ready for automated trading tomorrow morning!

---

Generated: 2026-01-05 20:20:00
Next scheduled start: 2026-01-06 08:45:00
