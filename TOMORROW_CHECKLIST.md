# Tomorrow Morning Checklist - Monday, January 6, 2026

**Paper Mode Test - Scheduled Run**

---

## Pre-Market (Before 8:45 AM ET)

### 1. System Health Check (8:30 AM - 8:40 AM)
```powershell
# Run comprehensive health check
powershell -ExecutionPolicy Bypass -File tools\windows\health_check.ps1
```

**Expected Status:**
- ✅ All 3 Task Scheduler tasks: Ready/Running
- ✅ Dashboard endpoint: Reachable
- ✅ Selector endpoint: Reachable
- ✅ Recent loop logs: Within last hour
- ✅ Uvicorn process: Running
- ⚠️ Alpaca API: May fail (non-critical)

**If issues found:**
- Dashboard not reachable → Check if uvicorn crashed, restart if needed
- Task not Ready → Check Task Scheduler for errors
- Loop logs stale → Check if loop stopped, investigate pause flag

---

### 2. Verify Paper Mode Configuration (8:40 AM)
```bash
# Check current mode
cat state/bot_state.json | grep -E "mode|pause"
```

**Expected:**
```json
"mode": "paper",
"is_paused": false
```

**If wrong mode:**
```bash
# Switch to paper mode
python -m src.app.cli set-mode paper
```

---

### 3. Check Alpaca Connectivity (8:40 AM)
```powershell
# Test paper account status
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status
```

**Expected:**
- Account status: ACTIVE
- Buying power: > $0

**If fails:**
- Verify env vars: `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`
- Check if credentials expired
- Wait and retry (may be temporary API issue)

---

## Market Open (8:45 AM - 9:00 AM ET)

### 4. Verify Dashboard Starts (8:45 AM)
**Task:** `AITrader-Dashboard` should auto-start

```bash
# Check if dashboard is running
curl http://localhost:8000/health
```

**Expected:**
```json
{"status":"ok","registry_loaded":true,"ledger_available":true}
```

**If not running:**
```powershell
# Manually start dashboard
powershell -ExecutionPolicy Bypass -File tools\windows\start_dashboard.ps1
```

**Access dashboard:**
- Open browser: http://localhost:8000
- Verify strategies are loaded
- Check account summary displays correctly

---

### 5. Verify Selector Starts (8:50 AM)
**Task:** `AITrader-Selector` should auto-run

```bash
# Check selector endpoint
curl http://localhost:8000/selector/status
```

**Expected:**
- `last_run`: Recent timestamp (within 5 minutes)
- `candidates_count`: > 0 (if news available)

**Check detailed stats:**
```bash
python -m src.app.selector.run_once --stats
```

**Review rejection reasons:**
```bash
tail -50 out/selector/events.jsonl | grep candidate_rejected
```

**If selector didn't run:**
```powershell
# Manually trigger selector
powershell -ExecutionPolicy Bypass -File tools\windows\run_selector.ps1
```

---

### 6. Monitor First Loop Execution (9:00 AM)
**Task:** `AITrader-Loop` should execute at 9:00 AM

```bash
# Watch loop logs in real-time
tail -f logs/loop_status.log
```

**Expected log entry:**
```
[2026-01-06T09:00:XX] SUCCESS | mode=paper | dry_run=False | orders_placed=X | orders_skipped=X
```

**Key checks:**
- `mode=paper` ✅
- `dry_run=False` ✅ (real paper execution)
- `orders_placed > 0` (if signals present)
- No `ERROR` or `exception` messages

**If errors:**
- Check pause flag: `cat state/bot_state.json | grep pause`
- Check risk limits: Dashboard → Account Summary
- Review exception message in logs

---

## During Market Hours (9:00 AM - 4:00 PM ET)

### 7. Periodic Health Checks (Every 2-3 Hours)

**Quick health check:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\health_check.ps1
```

**Check loop activity:**
```bash
# Last 5 loop executions
tail -20 logs/loop_status.log | grep SUCCESS
```

**Check dashboard:**
- Visit http://localhost:8000
- Verify recent activity shows up
- Check positions (if any)
- Verify PnL updates

---

### 8. Monitor Selector Activity (Runs every 15 min)

**Check selector freshness:**
```bash
# Check age of snapshot
ls -lh out/selector/snapshot.json
```

**Should be:** < 20 minutes old

**Review candidates:**
```bash
# View current candidates
cat out/selector/snapshot.json | grep -A 10 candidates
```

**If stale:**
- Check Task Scheduler: `AITrader-Selector` status
- Check selector logs: `out/selector/events.jsonl`
- Manually trigger if needed

---

### 9. Alpaca Orders Verification (After Any Execution)

**Check paper orders:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
```

**Expected:**
- Orders show up in Alpaca paper account
- Order status: `new`, `partially_filled`, `filled`, `pending_new`

**Check positions:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions
```

**If orders missing:**
- Check loop logs for `orders_placed` count
- Verify not in dry-run mode: `cat state/bot_state.json`
- Check risk manager didn't block all orders

---

### 10. Risk Manager Monitoring

**Check daily loss limit:**
```bash
# View current state
cat state/bot_state.json | grep -E "daily_loss|daily_date"
```

**Watch for:**
- `daily_realized_pnl` approaching `MAX_DAILY_LOSS`
- `daily_date` matches today (2026-01-06)

**If approaching limit:**
- Monitor closely - bot will pause at limit
- Check dashboard for PnL breakdown
- Review order history for losses

---

## Market Close (4:00 PM - 4:30 PM ET)

### 11. End-of-Day Review

**Check final loop execution (4:00 PM):**
```bash
tail -5 logs/loop_status.log
```

**Expected:**
- Final execution at ~4:00 PM
- No pending errors

**Review daily summary:**
```bash
# Check ledger for today's activity
ls -lh logs/ledger.jsonl
tail -50 logs/ledger.jsonl | grep "2026-01-06"
```

**Count orders placed:**
```bash
grep "orders_placed" logs/loop_status.log | grep "2026-01-06"
```

---

### 12. Alpaca Reconciliation

**Get all orders:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
```

**Get all positions:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions
```

**Verify:**
- Order count matches loop logs
- All filled orders show in positions
- No unexpected orders (verify all are from bot)

---

### 13. Save Results for Analysis

**Create daily snapshot:**
```bash
# Copy logs
mkdir -p archive/2026-01-06
cp logs/loop_status.log archive/2026-01-06/
cp logs/ledger.jsonl archive/2026-01-06/
cp out/selector/snapshot.json archive/2026-01-06/
cp out/selector/events.jsonl archive/2026-01-06/
cp state/bot_state.json archive/2026-01-06/
```

**Export Alpaca data:**
```powershell
# Save orders
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders > archive/2026-01-06/alpaca_orders.txt

# Save positions
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions > archive/2026-01-06/alpaca_positions.txt

# Save account status
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status > archive/2026-01-06/alpaca_status.txt
```

---

## Post-Market Analysis (After 4:30 PM)

### 14. Selector Performance

**Total candidates generated:**
```bash
python -m src.app.selector.run_once --stats
```

**Rejection breakdown:**
```bash
grep candidate_rejected out/selector/events.jsonl | wc -l
```

**By reason:**
```bash
grep candidate_rejected out/selector/events.jsonl | \
  jq -r '.rejection_reason' | sort | uniq -c
```

---

### 15. Loop Execution Stats

**Success/failure rate:**
```bash
# Count successes
grep SUCCESS logs/loop_status.log | grep "2026-01-06" | wc -l

# Count errors
grep ERROR logs/loop_status.log | grep "2026-01-06" | wc -l
```

**Orders placed:**
```bash
grep "orders_placed" logs/loop_status.log | grep "2026-01-06" | \
  grep -oP 'orders_placed=\K\d+' | \
  awk '{sum+=$1} END {print "Total orders:", sum}'
```

---

### 16. Final Health Check

**Run one last time:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\health_check.ps1
```

**Document:**
- Any issues encountered
- System behavior observations
- Improvements needed
- Tomorrow's action items

---

## Emergency Procedures

### If System Becomes Unstable

**Pause trading immediately:**
```bash
python -m src.app.cli pause "Emergency stop - investigating issue"
```

**Stop all tasks:**
```powershell
# Stop loop
schtasks /End /TN "AITrader-Loop"

# Stop selector
schtasks /End /TN "AITrader-Selector"
```

**Cancel all open orders:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 cancel-all
```

---

### If Need to Restart

**Restart dashboard:**
```powershell
# Find and kill uvicorn
taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*"

# Restart
powershell -ExecutionPolicy Bypass -File tools\windows\start_dashboard.ps1
```

**Restart loop:**
```powershell
# Stop task
schtasks /End /TN "AITrader-Loop"

# Start task
schtasks /Run /TN "AITrader-Loop"
```

**Resume trading:**
```bash
python -m src.app.cli resume "Issue resolved"
```

---

## Quick Reference Commands

**Health check:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\health_check.ps1
```

**Selector with stats:**
```bash
python -m src.app.selector.run_once --stats
```

**Alpaca status:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions
```

**Watch logs:**
```bash
tail -f logs/loop_status.log
```

**Check mode:**
```bash
cat state/bot_state.json | grep -E "mode|pause"
```

**Dashboard:**
```
http://localhost:8000
```

---

## Success Criteria

At end of day, expect:
- ✅ Dashboard accessible all day
- ✅ Selector ran every 15 minutes (8:50 AM - 4:10 PM)
- ✅ Loop executed every hour (9 AM, 10 AM, 11 AM, 12 PM, 1 PM, 2 PM, 3 PM, 4 PM)
- ✅ At least some orders placed (if signals present)
- ✅ Orders visible in Alpaca paper account
- ✅ No system crashes or hangs
- ✅ Pause flag remained `false` throughout
- ✅ Daily loss tracking working (state persisted)

---

**Good luck with tomorrow's test! 🚀**
