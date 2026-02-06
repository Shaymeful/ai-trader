# Order Hygiene Implementation - Bug Fix Summary

## Problem Statement

The Alpaca paper trading account was experiencing buying power collapse due to:
1. **Duplicate order spam**: Multiple open BUY limit orders for the same symbols
2. **No order management**: Stale orders were never canceled or replaced
3. **Reserved buying power not tracked**: Open orders reserve cash but weren't included in exposure calculations
4. **Total capital cap not enforced**: Dashboard configured $50k cap, but account had ~$100k equity

## Root Cause

The `AlpacaExecutor` was placing new orders without:
- Checking for existing open orders
- Canceling stale/duplicate orders
- Including reserved notional from open orders in exposure calculations

## Solution Implemented

### 1. Order Hygiene Configuration

**File: `config/config.yaml`**

Added new execution settings:
```yaml
execution:
  # Order hygiene settings
  cancel_stale_orders: true  # Cancel/replace stale open orders before placing new ones
  max_open_orders_per_symbol_side: 1  # Maximum open orders allowed per (symbol, side) pair
  order_price_tolerance_pct: 0.001  # 0.1% tolerance for considering orders equivalent
  order_qty_tolerance: 0.0001  # Quantity tolerance for fractional shares
```

### 2. Config Class Updates

**File: `src/app/config.py`**

Added fields to `Config` class:
- `cancel_stale_orders: bool` (default: True)
- `max_open_orders_per_symbol_side: int` (default: 1)
- `order_price_tolerance_pct: float` (default: 0.001)
- `order_qty_tolerance: float` (default: 0.0001)

Updated `load_config_with_yaml()` to load these from YAML.

### 3. Broker Interface Enhancement

**File: `src/broker/base.py`**

Added new method to both `AlpacaBroker` and `MockBroker`:
```python
def get_open_orders_detailed(self) -> list[dict]:
    """
    Get detailed information about all open orders.

    Returns:
        List of dicts with keys: order_id, client_order_id, symbol, side, qty,
        limit_price, order_type, status, created_at
    """
```

### 4. Order Hygiene Logic in Executor

**File: `src/app/execution/alpaca_executor.py`**

#### New Components:

1. **OrderHygieneAction dataclass**: Tracks hygiene actions (canceled, skipped, replaced)

2. **`_perform_order_hygiene()` method**:
   - Fetches all open orders from broker
   - Indexes by (symbol, side)
   - For each new instruction:
     - **If >1 existing orders**: Cancel ALL, place new one (fixes duplicates)
     - **If 1 existing order matches**: Skip new instruction (avoids duplicates)
     - **If 1 existing order doesn't match**: Cancel and replace (updates stale orders)
   - Returns filtered instructions and hygiene actions

3. **`_orders_match()` method**:
   - Compares new instruction vs existing order
   - Checks quantity within tolerance
   - Checks limit price within tolerance percentage

4. **Reserved Notional Tracking**:
   - Calculates reserved notional from remaining open BUY orders
   - Includes in exposure checks: `new_exposure = current_exposure + reserved_notional + slice_notional`
   - Prevents new orders if total would exceed `max_positions_notional`

#### Integration in `_execute_orders()`:

```python
# STEP 1: Perform order hygiene (cancel stale/duplicate orders, filter instructions)
filtered_instructions, hygiene_actions = self._perform_order_hygiene(
    instructions, current_prices
)

# Print hygiene summary
if hygiene_actions:
    print("\nOrder Hygiene:")
    for action in hygiene_actions:
        print(f"  {action.symbol} {action.side}: {action.action} - {action.reason}")

# Calculate reserved notional from remaining open BUY orders
reserved_notional = Decimal("0")
try:
    remaining_open_orders = self.broker.get_open_orders_detailed()
    for order in remaining_open_orders:
        if order["side"] == "BUY" and order["limit_price"]:
            reserved_notional += Decimal(str(order["qty"])) * order["limit_price"]
except Exception as e:
    self.logger.warning(f"Failed to calculate reserved notional: {e}")

# Include reserved notional in exposure checks
new_exposure = current_exposure + reserved_notional + slice_notional
if new_exposure > self.config.max_positions_notional:
    # Skip order
```

### 5. Test Coverage

**File: `tests/test_order_hygiene.py`**

Added comprehensive unit tests:
1. `test_skip_matching_open_order`: Verifies matching orders are skipped
2. `test_cancel_and_replace_stale_order`: Verifies stale orders are canceled/replaced
3. `test_cancel_duplicate_orders`: Verifies multiple duplicates are all canceled
4. `test_hygiene_disabled`: Verifies bypass when config disabled
5. `test_reserved_notional_calculation`: Verifies reserved notional calculation

All tests pass.

## How It Works

### Before (Broken):

```
Loop iteration 1: Place BUY AAPL 10 @ $150 (order-1)
Loop iteration 2: Place BUY AAPL 10 @ $150 (order-2) <- DUPLICATE!
Loop iteration 3: Place BUY AAPL 10 @ $150 (order-3) <- DUPLICATE!
...
Result: 3 open orders reserving 3x the cash
Buying power collapses
```

### After (Fixed):

```
Loop iteration 1: Place BUY AAPL 10 @ $150 (order-1)
Loop iteration 2:
  - Hygiene: Found existing order-1 for AAPL BUY
  - Orders match (same qty, same price)
  - Action: SKIP new order
  - Result: Still only 1 open order
Loop iteration 3:
  - Hygiene: Found existing order-1 for AAPL BUY
  - Price changed to $152
  - Action: CANCEL order-1, PLACE new order-2
  - Result: Still only 1 open order (updated)
```

### Duplicate Cleanup:

```
Current state: 5 duplicate BUY AAPL orders exist (order-1 through order-5)
Next loop iteration:
  - Hygiene: Found 5 existing orders for AAPL BUY
  - max_open_orders_per_symbol_side = 1
  - Action: CANCEL all 5 orders, PLACE 1 new consolidated order
  - Result: Only 1 open order
```

## Exposure Calculation Enhancement

### Before:
```python
new_exposure = current_positions_notional + new_order_notional
```

### After:
```python
new_exposure = current_positions_notional + reserved_notional + new_order_notional
# Where reserved_notional = sum of all open BUY order notionals
```

This prevents the loop from placing new orders when buying power is already reserved by existing open orders.

## Total Capital Cap Enforcement

The existing allocator already respects `total_capital` from `out/account_summary.json` when `risk.use_total_capital_as_equity_cap` is true. The enhancement ensures:
1. Open order reserved notional is included in exposure checks
2. New orders are blocked if total exposure (positions + reserved + new) exceeds cap

## Configuration Options

### To Enable (Default):
```yaml
execution:
  cancel_stale_orders: true
  max_open_orders_per_symbol_side: 1
```

### To Disable (Not Recommended):
```yaml
execution:
  cancel_stale_orders: false
```

### Tolerance Tuning:
```yaml
execution:
  order_price_tolerance_pct: 0.001  # 0.1% - orders within this are "matching"
  order_qty_tolerance: 0.0001       # For fractional shares
```

## Logging & Visibility

The executor now logs:
```
Order Hygiene:
  AAPL BUY: canceled - Duplicate order (found 3)
  AAPL BUY: canceled - Duplicate order (found 3)
  AAPL BUY: canceled - Duplicate order (found 3)
  AAPL BUY: replaced - Replaced 3 duplicate order(s)

Current portfolio exposure: $25000.00
Reserved notional (open orders): $15000.00
Total exposure (positions + reserved): $40000.00
```

## Verification Steps

### 1. Check Open Orders Before Fix:
```bash
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode paper
```
Expected: Multiple duplicate open orders for same symbols

### 2. Run Loop Once With Fix:
```bash
python -m src.app.runner --mode paper --once
```
Expected: Order hygiene summary showing cancellations

### 3. Check Open Orders After Fix:
```bash
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode paper
```
Expected: Only 1 open order per (symbol, side), or none if all filled

### 4. Run Unit Tests:
```bash
python -m pytest tests/test_order_hygiene.py -v
```
Expected: All 5 tests pass

### 5. Monitor Loop Behavior:
```bash
# Run loop for a few iterations
python -m src.app.runner --mode paper --loop --sleep-seconds 300
```
Expected:
- First iteration: May place new orders
- Second iteration: Hygiene skips matching orders
- No duplicate orders accumulate

## Files Modified

1. `config/config.yaml` - Added order hygiene settings
2. `src/app/config.py` - Added config fields and loading logic
3. `src/broker/base.py` - Added `get_open_orders_detailed()` to AlpacaBroker and MockBroker
4. `src/app/execution/alpaca_executor.py` - Implemented order hygiene logic and reserved notional tracking
5. `tests/test_order_hygiene.py` - New test file with comprehensive coverage

## Safety Features

1. **Fail-open**: If fetching open orders fails, hygiene is skipped and orders proceed (preserves functionality)
2. **Dry-run support**: Hygiene actions are logged but not executed in dry-run mode
3. **Configurable**: Can be disabled via config if needed
4. **Risk-reducing orders always proceed**: SELL orders to close positions are never blocked
5. **Deterministic**: Running loop twice with no signal change won't create duplicate orders

## Performance Impact

- Minimal: One additional API call per loop iteration to fetch open orders
- Benefit: Prevents hundreds of duplicate orders from accumulating
- Net result: Significantly reduced API calls and improved buying power management

## Next Steps (Optional Enhancements)

1. Add `--status` command enhancement to show open orders summary
2. Add ledger events for order hygiene actions
3. Consider time-based staleness detection (cancel orders older than N hours)
4. Add dashboard UI showing open orders and reserved buying power

## Summary

This implementation solves the duplicate order spam bug by:
1. ✅ Checking for existing open orders before placing new ones
2. ✅ Canceling duplicate orders (keeping only 1 per symbol/side)
3. ✅ Updating stale orders when price/quantity changes
4. ✅ Tracking reserved notional from open orders in exposure calculations
5. ✅ Enforcing total capital cap including reserved buying power

The fix is backward compatible, configurable, and extensively tested.
