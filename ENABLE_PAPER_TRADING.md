# Getting Paper Trading Running

## Current Status ✅

### What's Already Working
- ✅ **Dashboard UI**: Running on port 8000
  - Access at: **http://localhost:8000**
  - Provides real-time monitoring, controls, and performance tracking

- ✅ **Trading Loop**: Running hourly (9 AM - 11:30 PM ET)
  - **Mode**: Paper trading
  - **Safety**: DRY-RUN enabled (simulated trades only)
  - **Universe**: 4 symbols (SPY, QQQ, DIA, IWM)
  - **Strategies**: Trend_MA20, MeanRev_Z1.0, Momentum_MACD
  - **Schedule**: Executes every hour

- ✅ **All Bugs Fixed**:
  - Universe configuration working correctly
  - MockBroker errors resolved
  - Loop executing without errors

---

## What You Need to Know

### Current Mode: DRY-RUN (Safe)
Your system is currently in **DRY-RUN mode**:
- ✅ **Safe**: No real orders are placed
- ✅ **Simulated**: Trades are logged but not sent to Alpaca
- ✅ **Testing**: Perfect for verifying strategies work correctly
- ⚠️ **Not Trading**: No actual fills or positions on Alpaca

### Live Paper Trading Mode
To enable **real paper trading**:
- 📊 **Real Orders**: Orders sent to Alpaca paper account
- 💰 **Paper Money**: Uses Alpaca's simulated $100k account
- 🔒 **No Real Risk**: Still using paper trading (not live money)
- ✅ **Real Fills**: Actual market fills and positions tracked

---

## Steps to Enable Live Paper Trading

### Step 1: Access the Dashboard
Open your browser and go to:
```
http://localhost:8000
```

**Dashboard Features**:
- View current positions and performance
- Monitor strategy signals and allocations
- See universe configuration
- Track equity curve and PnL
- View execution history

### Step 2: Enable Live Paper Trading (Optional)

⚠️ **IMPORTANT**: Only do this when you're ready for real orders on your paper account!

**To enable live paper trading**:
1. Right-click: `enable_live_paper_trading.cmd`
2. Select: **"Run as administrator"**
3. Confirm the action
4. The loop will restart in LIVE mode

**What changes**:
- ❌ Removes `-DryRun` flag
- ✅ Orders sent to Alpaca paper API
- ✅ Real fills and positions tracked
- ✅ Alpaca dashboard shows your orders

**To revert back to dry-run**:
1. Right-click: `revert_to_dryrun.cmd`
2. Select: **"Run as administrator"**
3. System returns to simulation mode

---

## Current Configuration

### Loop Schedule
```
Start: 9:00 AM ET
End: 11:30 PM ET
Interval: 1 hour
Mode: Paper (DRY-RUN)
```

### Universe (Active Symbols)
```
SPY  - S&P 500 ETF
QQQ  - Nasdaq-100 ETF
DIA  - Dow Jones ETF
IWM  - Russell 2000 ETF
```

### Strategies (Equal Weight)
```
Trend_MA20     - 35% allocation
MeanRev_Z1.0   - 35% allocation
Momentum_MACD  - 30% allocation
```

### Risk Controls
```
Max Order Size: $100
Max Daily Loss: $250
Max Gross Exposure: $10,000
```

---

## Monitoring Your System

### Dashboard Sections

1. **Account Summary**
   - Current equity and PnL
   - Daily performance
   - Cash available

2. **Positions**
   - Current holdings
   - Unrealized PnL
   - Entry prices

3. **Strategies**
   - Active strategy status
   - Current signals
   - Performance metrics

4. **Universe**
   - Enabled sectors
   - Symbol list
   - Configuration controls

5. **Activity Feed**
   - Recent orders
   - Trade executions
   - System events

### Log Files

**Loop Execution**:
```
logs\loop\loop_YYYYMMDD.log
```
Shows each iteration's execution

**Errors**:
```
logs\loop_errors.log
```
Shows any errors that occurred

**Performance**:
```
out\perf\equity.jsonl
```
Tracks equity over time

---

## Safety Features

### Built-in Protections
- ✅ **Position Sizing**: Never exceeds max order size
- ✅ **Daily Loss Limit**: Stops trading if daily loss threshold hit
- ✅ **Exposure Limit**: Caps total gross exposure
- ✅ **Universe Control**: Only trades enabled sectors
- ✅ **Strategy Registry**: Strategies can be enabled/disabled
- ✅ **Dry-Run Mode**: Test before going live

### Current Safety Status
- ✅ Running in **DRY-RUN mode** (safest)
- ✅ Universe properly configured (4 symbols)
- ✅ All bugs fixed and tested
- ✅ Loop executing successfully

---

## Next Steps

### Recommended Workflow

1. **Monitor in Dry-Run** (Current State)
   - Access dashboard: http://localhost:8000
   - Watch loop iterations (hourly)
   - Review strategy signals
   - Check performance metrics
   - **Stay in this mode for several days**

2. **Verify Everything Works**
   - Check logs for clean execution
   - Confirm strategies generate signals
   - Review allocation logic
   - Ensure risk controls work
   - Verify no errors occur

3. **Enable Live Paper Trading** (When Ready)
   - Run `enable_live_paper_trading.cmd` as admin
   - Monitor first few iterations closely
   - Check Alpaca paper account for orders
   - Verify fills match expectations
   - Continue monitoring daily

4. **Fine-Tune Configuration**
   - Adjust strategy weights via dashboard
   - Enable/disable sectors as needed
   - Modify risk parameters if desired
   - Add more symbols to universe

---

## Quick Reference Commands

### Check System Status
```cmd
# Dashboard status
netstat -ano | findstr :8000

# Loop status
schtasks /query /tn AITrader-Loop /fo LIST

# View recent logs
type logs\loop\loop_20260107.log

# Check for errors
type logs\loop_errors.log
```

### Control Loop
```cmd
# Stop loop
schtasks /End /TN AITrader-Loop

# Start loop
schtasks /run /tn AITrader-Loop

# Check next run time
schtasks /query /tn AITrader-Loop
```

---

## Troubleshooting

### Dashboard Not Loading
```cmd
# Check if dashboard is running
netstat -ano | findstr :8000

# If not running, start it
schtasks /run /tn AITrader-Dashboard

# Wait 10 seconds then access:
# http://localhost:8000
```

### Loop Not Executing
```cmd
# Check task status
schtasks /query /tn AITrader-Loop /fo LIST

# Check for errors
type logs\loop_errors.log

# Restart loop
schtasks /End /TN AITrader-Loop
schtasks /run /tn AITrader-Loop
```

### No Trades Executing
- **If in DRY-RUN**: This is expected (simulated only)
- **If in LIVE mode**: Check:
  - Strategies generating signals? (Dashboard > Strategies)
  - Universe enabled? (Dashboard > Universe)
  - Within risk limits? (Check daily loss, exposure)
  - Market hours? (Loop runs 9 AM - 11:30 PM ET)

---

## Important Notes

### Paper Trading vs Live Trading
This system is configured for **Alpaca Paper Trading**:
- ✅ Uses paper trading API endpoint
- ✅ Simulated $100k account
- ✅ No real money at risk
- ✅ Real market data and fills
- ⚠️ **Still requires paper API credentials**

To switch to **LIVE trading** (real money):
- ❌ **NOT RECOMMENDED without extensive testing**
- Requires different API keys (live credentials)
- Requires changing `--mode paper` to `--mode live`
- **DO NOT do this without understanding the risks**

### Current Mode Summary
```
Mode:     Paper Trading
Safety:   DRY-RUN enabled
Risk:     ZERO (simulated only)
Action:   Monitor and test
```

---

## Files Created

1. **enable_live_paper_trading.cmd**
   - Removes DryRun flag
   - Enables real orders on paper account
   - Requires admin privileges

2. **revert_to_dryrun.cmd**
   - Restores DryRun flag
   - Returns to simulation mode
   - Requires admin privileges

3. **AITrader-Loop-Live.xml**
   - Modified task configuration
   - Used by enable script

4. **ENABLE_PAPER_TRADING.md**
   - This guide

---

## Support

### Check Documentation
- `docs/ARCHITECTURE.md` - System design
- `docs/CHANGELOG.md` - Recent changes
- `SCHEDULER_FIXES_SUMMARY.md` - Recent fixes

### View Dashboard
- **URL**: http://localhost:8000
- **Features**: Real-time monitoring and control
- **No Auth**: Secure your network

---

**You're all set! The system is running in safe DRY-RUN mode.**
**Access the dashboard at http://localhost:8000 to monitor performance.**
