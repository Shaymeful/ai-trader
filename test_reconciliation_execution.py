"""Test reconciliation execution with forced low cap.

This script temporarily sets a low cap ($1000) to force reconciliation
to trigger sells, allowing us to verify the entire execution chain.
"""
import os
import sys
from pathlib import Path

# Ensure we're using the venv
venv_python = Path(".venv/Scripts/python.exe")
if not venv_python.exists():
    print("ERROR: Virtual environment not found at .venv/Scripts/python.exe")
    sys.exit(1)

print("="*80)
print("RECONCILIATION EXECUTION TEST")
print("="*80)
print(f"Using Python: {venv_python.absolute()}")
print()

# Step 1: Check if we have any positions
print("[Step 1] Checking current positions...")
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker
from decimal import Decimal

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, data_base_url = get_alpaca_credentials("paper")
broker = AlpacaBroker(api_key, secret_key, trading_base_url)
positions = broker.get_positions()

total_exposure = Decimal("0")
for symbol, pos_data in positions.items():
    if isinstance(pos_data, dict):
        qty = pos_data.get('qty', 0)
        avg_price = Decimal(str(pos_data.get('avg_entry_price', 0)))
    else:
        qty = getattr(pos_data, 'qty', 0)
        avg_price = Decimal(str(getattr(pos_data, 'avg_entry_price', 0)))
    total_exposure += Decimal(qty) * avg_price
    print(f"  {symbol}: qty={qty}, avg_price=${avg_price:.2f}, notional=${Decimal(qty) * avg_price:,.2f}")

print(f"\nCurrent exposure: ${total_exposure:,.2f}")
current_cap = config.max_positions_notional
print(f"Current cap: ${current_cap:,.2f}")

if total_exposure == 0:
    print("\n[RESULT] No positions found - cannot test reconciliation execution")
    print("Portfolio needs positions before reconciliation can trigger sells")
    sys.exit(0)

# Step 2: Temporarily patch config to use low cap for testing
print("\n[Step 2] Patching config with LOW CAP for testing...")
original_cap = config.max_positions_notional
test_cap = Decimal("1000")  # Force violation
config.max_positions_notional = test_cap
print(f"  Original cap: ${original_cap:,.2f}")
print(f"  Test cap: ${test_cap:,.2f}")
print(f"  Forced violation: ${total_exposure - test_cap:,.2f} over cap")

# Step 3: Run reconciliation manually
print("\n[Step 3] Running reconciliation with test cap...")
from src.app.portfolio_reconciler import PortfolioReconciler
from src.app.ticker_exclusions import TickerExclusionManager

exclusion_manager = TickerExclusionManager()
reconciler = PortfolioReconciler(
    config=config,
    universe_registry=None,  # Not testing sector rotation
    excluded_tickers=exclusion_manager.get_excluded_dict(),
)

# Convert positions to reconciler format
reconcile_positions = {}
current_prices = {}
for symbol, pos_data in positions.items():
    if isinstance(pos_data, dict):
        qty = pos_data.get('qty', 0)
        avg_price = Decimal(str(pos_data.get('avg_entry_price', 0)))
        current_price = Decimal(str(pos_data.get('current_price', avg_price)))
    else:
        qty = getattr(pos_data, 'qty', 0)
        avg_price = Decimal(str(getattr(pos_data, 'avg_entry_price', 0)))
        current_price = Decimal(str(getattr(pos_data, 'current_price', avg_price)))

    if qty > 0:
        reconcile_positions[symbol] = (int(qty), avg_price)
        current_prices[symbol] = current_price

result = reconciler.reconcile(reconcile_positions, current_prices)

print("\n[Step 4] Analyzing results...")
print(f"  Violations: {len(result.violations)}")
print(f"  Sell intents: {len(result.sell_intents)}")
print(f"  Target exposure: ${result.target_exposure:,.2f}")

if len(result.sell_intents) == 0:
    print("\n[FAIL] Reconciliation did NOT generate sell intents despite cap violation!")
    print("This indicates a bug in the reconciliation logic.")
    sys.exit(1)

print("\n[SUCCESS] Reconciliation generated sell intents:")
for intent in result.sell_intents:
    print(f"  - {intent.symbol}: qty={intent.quantity}, reason={intent.reason.value}")

# Step 4: Restore original cap
print("\n[Step 5] Restoring original cap...")
config.max_positions_notional = original_cap
print(f"  Cap restored to: ${original_cap:,.2f}")

print("\n"+"="*80)
print("TEST COMPLETE - Reconciliation logic verified")
print("="*80)
print("\nNext: Run full loop iteration to verify sell orders are executed:")
print("  .venv\\Scripts\\python.exe -m src.app.runner --mode paper --once")
print()
