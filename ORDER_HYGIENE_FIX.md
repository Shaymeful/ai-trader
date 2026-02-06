# Order Hygiene Fix - Capital Limit & Duplicate Orders

## Issues Identified

### Issue #1: Order Accumulation Bug
**Root Cause:** Order hygiene ran BEFORE order slicing, creating a mismatch:
- Hygiene would cancel 2 old orders
- Then the NEW order would get sliced into 20 orders ($50k ÷ $2.5k max_order_usd)
- Net result: 2 canceled, 20 placed = **18 more orders per run**
- Over multiple runs, this created **hundreds of duplicate orders**

**Evidence from logs:**
```
Order Hygiene:
  EOSE BUY: canceled - Duplicate order (found 2)
  EOSE BUY: replaced - Replaced 2 duplicate order(s)

EOSE: Order $48258.17 exceeds cap, slicing into 20 orders

Reserved notional: $78,239.92  ← From accumulated orders!
```

### Issue #2: Capital Limit Working, But Too Late
The $50k capital limit (`total_capital` in `out/account_summary.json`) is being enforced correctly:
- Allocator respects the cap when calculating budgets
- Executor blocks new orders when `positions + reserved + new > $50k`
- **BUT** the damage was already done by accumulated orders from previous runs

**Evidence:**
```
Total exposure $80736.36 (positions: $0.00 + reserved: $78239.92 + new: $2496.44)
would exceed max $50000
```

The system correctly blocked new orders, but $78k in open orders were already consuming buying power.

## Solution Implemented

### Code Fix: Aggressive Order Cancellation (alpaca_executor.py)

**OLD POLICY:**
```python
if len(existing_orders) > max_open_orders_per_symbol_side:
    cancel_all()
elif existing_order_matches(new_instruction):
    skip_new_instruction()
else:
    cancel_and_replace()
```
**Problem:** This ran BEFORE slicing, so canceling 2 orders then placing 1 instruction that becomes 20 orders = net +18 orders

**NEW POLICY:**
```python
if any_existing_order_matches(new_instruction):
    skip_new_instruction()  # Don't create duplicates
else:
    cancel_ALL_existing_orders()  # Clear the slate
    place_new_instruction()  # May get sliced into multiple orders
```
**Benefit:**
- Each run cancels ALL previous orders for (symbol, side) before placing new ones
- Prevents accumulation even when slicing creates many orders
- Next run will cancel all sliced orders if anything changes

### File Changed
- `src/app/execution/alpaca_executor.py`: Updated `_perform_order_hygiene()` method

## Cleanup Required

The code fix prevents FUTURE accumulation, but you need to clean up the EXISTING accumulated orders:

### Option 1: Using Python Cleanup Script (Recommended)

```bash
# Dry-run preview (see what will be canceled)
python tools/cancel_all_paper_orders.py

# Actually cancel all orders
python tools/cancel_all_paper_orders.py --confirm
```

This will:
1. Connect to Alpaca paper account
2. Show summary of all open orders (by symbol, side, notional)
3. Cancel ALL open orders
4. Report summary

### Option 2: Using PowerShell Alpaca Script

```powershell
# View current open orders
powershell -ExecutionPolicy Bypass -File tools/alpaca.ps1 orders -Mode paper

# Cancel ALL open orders
powershell -ExecutionPolicy Bypass -File tools/alpaca.ps1 cancel-all -Mode paper
```

### Option 3: Manual via Alpaca Dashboard

1. Visit https://app.alpaca.markets/paper/dashboard/overview
2. Go to Orders tab
3. Click "Cancel All" button

## Verification Steps

### 1. Check Current State (Before Cleanup)

```bash
python tools/cancel_all_paper_orders.py
```

Expected output:
```
OPEN ORDERS SUMMARY
Total open orders: 100+ (varies)
Total reserved buying power: $50,000+ (exceeds cap)

Symbol   Total   BUY  SELL  Reserved $
--------------------------------------------
EOSE        30    30     0   $78,239.92
[other symbols...]
```

### 2. Clean Up Orders

```bash
python tools/cancel_all_paper_orders.py --confirm
# Type "YES" when prompted
```

Expected output:
```
Successfully canceled: [all orders]
Freed up approximately $XXX,XXX in reserved buying power
```

### 3. Verify Cleanup

```bash
python tools/cancel_all_paper_orders.py
```

Expected output:
```
No open orders found. Nothing to cancel.
```

### 4. Test With Fixed Code

```bash
# Run once in dry-run to see what would happen
python -m src.app.runner --mode paper --once --dry-run

# Check logs for "Order Hygiene:" section
# Should show no existing orders to cancel (clean slate)
```

### 5. Run Live (Paper Mode)

```bash
# Single iteration
python -m src.app.runner --mode paper --once

# Check that orders placed are reasonable (not hundreds)
python tools/cancel_all_paper_orders.py
```

Expected:
- Small number of orders (10-20 max from current run)
- Total reserved notional within budget ($50k cap)

### 6. Run Loop and Monitor

```bash
# Run loop for 2 iterations
python -m src.app.runner --mode paper --loop --sleep-seconds 300

# After 2 iterations, check orders
python tools/cancel_all_paper_orders.py
```

Expected:
- Order count stays stable or decreases
- No accumulation across iterations
- Hygiene cancels old orders before placing new ones

## Configuration Settings

The fix relies on these config settings (already enabled in `config/config.yaml`):

```yaml
risk:
  use_total_capital_as_equity_cap: true  # Uses $50k cap from account_summary.json
  max_order_usd: 2500  # Triggers order slicing for large orders
  max_gross_exposure_usd: 50000  # Total portfolio cap

execution:
  cancel_stale_orders: true  # REQUIRED: Enables order hygiene
  max_open_orders_per_symbol_side: 1  # Target (may be exceeded by slicing)
```

## Expected Behavior After Fix

### Scenario 1: No Signal Change
```
Run 1: Places 20 EOSE BUY orders (sliced from $48k order)
Run 2:
  - Hygiene finds 20 existing EOSE BUY orders
  - Checks if new instruction matches (it does)
  - SKIPS new order (avoids duplicates)
  - Result: Still 20 orders, no accumulation
```

### Scenario 2: Signal Changes
```
Run 1: Places 20 EOSE BUY orders @ $18.00 (sliced)
Run 2 (price changed):
  - Hygiene finds 20 existing EOSE BUY orders
  - New instruction has different price ($18.50)
  - Cancels ALL 20 existing orders
  - Places new instruction @ $18.50 (gets sliced into 18 orders)
  - Result: 20 old orders canceled, 18 new orders placed
```

### Scenario 3: Signal Reverses
```
Run 1: Places 20 EOSE BUY orders
Run 2 (signal flips to SELL):
  - Hygiene checks for EOSE SELL orders (none exist)
  - Places SELL instruction (no cancellation needed)
  - BUY orders remain (different side)
  - Result: 20 BUY orders + 1 SELL order

Run 3 (BUY signal returns):
  - Hygiene finds 20 existing EOSE BUY orders (now stale)
  - Cancels ALL 20
  - Places new BUY instruction (sliced)
```

## Monitoring & Alerts

### Key Metrics to Watch

1. **Open Order Count**
   - Should stay stable (10-30 orders typical)
   - Alert if > 50 orders

2. **Reserved Buying Power**
   - Should stay under $50k cap
   - Alert if > $45k (90% utilization)

3. **Order Hygiene Actions**
   - Check logs for "Order Hygiene:" section
   - Should see "canceled" or "skipped" actions, not "none"

4. **Execution Errors**
   - No more "insufficient buying power" errors (if cleaned up)
   - No more "Total exposure would exceed max $50000" (after cleanup)

### Logging to Monitor

```bash
# Watch for order hygiene in real-time
tail -f logs/loop/loop_$(date +%Y%m%d).log | grep -A5 "Order Hygiene"

# Check for exposure warnings
grep "Total exposure" logs/loop/*.log

# Check for Alpaca errors
grep "insufficient buying power" logs/loop/*.log
```

## Rollback Plan

If the fix causes issues, you can temporarily disable order hygiene:

```yaml
# config/config.yaml
execution:
  cancel_stale_orders: false  # Disables hygiene (not recommended)
```

Then manually cancel orders as needed:
```bash
python tools/cancel_all_paper_orders.py --confirm
```

## Summary

**What was broken:**
- Order hygiene canceled 2 orders, then slicing created 20 orders → net +18 per run
- Orders accumulated to $78k, consuming all buying power
- Capital limit was working but couldn't prevent orders already placed

**What was fixed:**
- Order hygiene now cancels ALL existing orders before placing new ones
- Prevents accumulation even when slicing creates multiple orders
- Each run starts with a clean slate for changed signals

**What you need to do:**
1. **Cancel existing accumulated orders** (one-time cleanup):
   ```bash
   python tools/cancel_all_paper_orders.py --confirm
   ```

2. **Verify fix is working** (after cleanup):
   ```bash
   python -m src.app.runner --mode paper --once
   python tools/cancel_all_paper_orders.py  # Should show reasonable order count
   ```

3. **Resume normal operation** (loop should work correctly now):
   ```bash
   python -m src.app.runner --mode paper --loop --sleep-seconds 3600
   ```

The $50k capital limit will now be respected, and duplicate orders will not accumulate.
