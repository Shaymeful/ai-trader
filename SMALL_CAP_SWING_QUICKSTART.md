# Small Cap Swing Mode - Quick Start Guide

## 🚀 Quick Test Commands

### 1. Run Unit Tests
```bash
# Test execution gate
pytest tests/test_tradability_filter.py -v

# Test mode profile
pytest tests/test_small_cap_mode.py -v

# Run all tests
pytest tests/test_tradability_filter.py tests/test_small_cap_mode.py -v
```

**Expected:** All tests pass (30+ tests total)

---

### 2. Switch to Small Cap Swing Mode
```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d "{\"profile\": \"small_cap_swing\"}"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Mode switched to 'small_cap_swing'. Changes will take effect on next loop iteration.",
  "pending_version": 5
}
```

---

### 3. Verify Mode Status
```bash
curl -s http://localhost:8000/api/mode | python -m json.tool
```

**Expected Output:**
```json
{
  "active_profile": "small_cap_swing",
  "available_profiles": ["normal", "aggressive_tech_energy", "small_cap_swing"],
  "profile_description": "Small/mid cap swing trading with market cap constraints and longer hold periods",
  "coordinated_settings": {
    "strategies": {
      "AI_COPILOT_WEIGHTED": {
        "enabled": true,
        "weight": 0.5,
        "params": {"execution_enabled": true}
      }
    },
    "execution_gate": {
      "min_market_cap_usd": 300000000,
      "max_market_cap_usd": 10000000000,
      "min_price": 3.0,
      "max_price": 80.0,
      "min_avg_dollar_volume_20d": 5000000,
      "max_spread_bps": 100,
      "strict_mode": true
    }
  }
}
```

---

### 4. Test Dashboard UI

1. Open: http://localhost:8000
2. Locate "Trading Mode" panel (below health panel)
3. Click "Small Cap Swing" button
4. Observe:
   - Badge changes to "Small Cap Swing" (purple)
   - Success notification appears
   - **Execution Filters panel appears** showing:
     - Market cap range: $300M - $10B
     - Price range: $3.00 - $80.00
     - Min daily volume: $5M/day
     - Max spread: 100 bps

---

### 5. Verify Execution Gate in Action

#### Start Loop in Dry-Run Mode:
```bash
cd C:\dev\ai-trader
.venv\Scripts\python.exe -m src.app.runner paper --dry-run
```

**Expected Console Output:**
```
Execution gate ENABLED (mode: small_cap_swing)
  Market cap range: $300,000,000 - $10,000,000,000
  Price range: $3.00 - $80.00
  Min liquidity: $5,000,000/day

...

Executing orders...
  AAPL: BLOCKED - Market cap $3,500,000,000,000 above maximum $10,000,000,000
  NVDA: BLOCKED - Market cap $1,800,000,000,000 above maximum $10,000,000,000
  AFRM: ALLOWED (all checks passed, fundamentals_checked=True)
  [DRY-RUN] AFRM  BUY      50 @ $ 35.00  (Target=50, Current=0, Delta=50)
```

---

### 6. Check Blocked Trades in Logs
```bash
# Find latest loop log
ls logs\loop\ -Sort LastWriteTime | Select-Object -Last 1

# Search for blocked orders
Select-String -Path "logs\loop\loop_*.log" -Pattern "BLOCKED by execution gate"
```

**Expected Output:**
```
AAPL: BLOCKED by execution gate: Market cap $3,500,000,000,000 above maximum $10,000,000,000 (reason: market_cap_above_maximum)
NVDA: BLOCKED by execution gate: Market cap $1,800,000,000,000 above maximum $10,000,000,000 (reason: market_cap_above_maximum)
MSFT: BLOCKED by execution gate: Market cap $3,000,000,000,000 above maximum $10,000,000,000 (reason: market_cap_above_maximum)
```

---

### 7. Switch Back to Normal Mode
```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d "{\"profile\": \"normal\"}"
```

**Expected Result:**
- Mode switches to "normal"
- Execution gate DISABLED
- Next loop allows mega caps again

---

## 📊 Expected Behavior Matrix

| Symbol | Market Cap | Small Cap Mode | Normal Mode | Reason |
|--------|-----------|----------------|-------------|---------|
| AAPL | $3.5T | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| NVDA | $1.8T | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| MSFT | $3T | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| META | $1.2T | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| TSLA | $800B | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| AMD | $180B | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| PLTR | $45B | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| RIVN | $12B | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| AFRM | $9B | ✅ ALLOWED | ✅ ALLOWED | Within range |
| SOFI | $8B | ✅ ALLOWED | ✅ ALLOWED | Within range |
| IONQ | $3.5B | ✅ ALLOWED | ✅ ALLOWED | Within range |
| SPY | $500B (ETF) | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| QQQ | $250B (ETF) | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |
| XLE | $30B (ETF) | ❌ BLOCKED | ✅ ALLOWED | Cap > $10B max |

---

## 🛠️ Troubleshooting

### Gate Not Blocking Orders

**Check:**
1. Mode is `small_cap_swing`: `curl http://localhost:8000/api/mode`
2. Execution gate config present in response
3. Runner restarted after mode switch
4. Fundamentals data available: `cat data\cache\fundamentals_manual.json`

### Unexpected Blocks

**Check:**
1. Fundamentals data for symbol: `grep "SYMBOL" data\cache\fundamentals_manual.json`
2. Market cap within range: $300M - $10B
3. Price within range: $3.00 - $80.00
4. Symbol not in `exclude_symbols` list

### Dashboard Filters Not Showing

**Check:**
1. Dashboard server restarted: Ctrl+C, restart
2. Browser cache cleared: Ctrl+Shift+R
3. Mode switched to `small_cap_swing`
4. `execution_gate` in API response: `curl http://localhost:8000/api/mode | grep execution_gate`

---

## 📝 Adding New Symbols to Fundamentals Cache

Edit `data\cache\fundamentals_manual.json`:

```json
{
  "NEWSYMBOL": {
    "symbol": "NEWSYMBOL",
    "market_cap_usd": 5000000000,
    "avg_dollar_volume_20d": 50000000,
    "price": 25.0,
    "spread_bps": 15
  }
}
```

**Restart runner** to reload cache.

---

## 🔧 Temporarily Allowing a Mega Cap

Edit `config\modes.yaml`:

```yaml
small_cap_swing:
  execution_gate:
    allow_symbols: ["NVDA"]  # Bypass all checks for NVDA
```

**Restart dashboard**, switch modes, restart runner.

---

## 📊 Monitoring in Production

### Check Active Mode:
```bash
curl -s http://localhost:8000/api/mode | jq -r '.active_profile'
```

### Count Blocked Orders (last 24h):
```bash
Select-String -Path "logs\loop\loop_*.log" -Pattern "BLOCKED by execution gate" | Measure-Object -Line
```

### List Blocked Symbols:
```bash
Select-String -Path "logs\loop\loop_*.log" -Pattern "BLOCKED by execution gate" |
  Select-String -Pattern "^(\w+):" |
  ForEach-Object { $_.Matches[0].Groups[1].Value } |
  Sort-Object -Unique
```

### Tail Live Log:
```bash
Get-Content -Path "logs\loop\loop_manual_$(Get-Date -Format 'yyyyMMdd')_*.log" -Tail 50 -Wait
```

---

## ✅ Success Checklist

- [ ] Tests pass: `pytest tests/test_tradability_filter.py tests/test_small_cap_mode.py -v`
- [ ] Mode switches via API: `POST /api/mode {"profile": "small_cap_swing"}`
- [ ] Dashboard shows "Small Cap Swing" button and filters panel
- [ ] Execution gate blocks mega caps: AAPL, NVDA, MSFT
- [ ] Execution gate allows small caps: AFRM, SOFI, IONQ
- [ ] Logs show block reasons: `Select-String -Pattern "BLOCKED by execution gate"`
- [ ] Documentation updated: `docs\ARCHITECTURE.md`

---

**All tests passing?** ✅ Ready for production!

**Questions?** See `PR_SUMMARY_SMALL_CAP_SWING.md` for full details.
