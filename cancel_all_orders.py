"""Cancel all open orders in Alpaca paper account.

This is useful for cleanup when you have stale open orders from previously
active symbols that are no longer in your universe.
"""

import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.broker import AlpacaBroker
from src.app.config import get_alpaca_credentials


def main():
    mode = "paper"  # Change to "live" if needed (BE CAREFUL!)

    print(f"{'=' * 80}")
    print(f"CANCEL ALL OPEN ORDERS - {mode.upper()} MODE")
    print(f"{'=' * 80}\n")

    # Get credentials
    api_key, secret_key, trading_base_url, data_base_url = get_alpaca_credentials(mode)

    if not api_key or not secret_key:
        print(f"ERROR: No credentials found for {mode} mode")
        print("Set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY environment variables")
        return 1

    # Initialize broker
    print(f"Connecting to {trading_base_url}...")
    broker = AlpacaBroker(api_key, secret_key, trading_base_url)

    # Get open orders
    print("Fetching open orders...\n")
    try:
        open_orders = broker.get_open_orders_detailed()

        if not open_orders:
            print("✅ No open orders found - account is clean!")
            return 0

        print(f"Found {len(open_orders)} open orders:\n")
        print(f"{'Symbol':<8} {'Side':<6} {'Qty':<10} {'Limit Price':<12} {'Order ID':<40}")
        print("-" * 80)

        # Group by symbol
        from collections import defaultdict

        by_symbol = defaultdict(list)
        total_reserved = 0

        for order in open_orders:
            by_symbol[order["symbol"]].append(order)
            qty = order["qty"]
            limit_price = order["limit_price"]
            notional = float(qty) * float(limit_price) if limit_price else 0
            total_reserved += notional

            print(
                f"{order['symbol']:<8} {order['side']:<6} {qty:<10.2f} ${float(limit_price) if limit_price else 0:<11.2f} {order['order_id']}"
            )

        print(f"\nTotal reserved notional: ${total_reserved:,.2f}")

        # Show duplicates
        duplicates = {symbol: orders for symbol, orders in by_symbol.items() if len(orders) > 1}
        if duplicates:
            print("\n⚠️  DUPLICATES DETECTED:")
            for symbol, orders in sorted(duplicates.items()):
                print(f"  {symbol}: {len(orders)} open {orders[0]['side']} orders")

        # Confirm cancellation
        print("\n" + "=" * 80)
        response = input(f"Cancel all {len(open_orders)} orders? (yes/no): ").strip().lower()

        if response != "yes":
            print("Cancelled - no orders were canceled")
            return 0

        # Cancel all orders
        print(f"\nCanceling {len(open_orders)} orders...")
        canceled = 0
        failed = 0

        for order in open_orders:
            order_id = order["order_id"]
            symbol = order["symbol"]
            try:
                broker.client.cancel_order_by_id(order_id)
                print(f"  ✅ Canceled {symbol} {order['side']} order {order_id}")
                canceled += 1
            except Exception as e:
                print(f"  ❌ Failed to cancel {symbol} order {order_id}: {e}")
                failed += 1

        print(f"\n{'=' * 80}")
        print(f"SUMMARY: Canceled {canceled} orders, {failed} failed")
        print(f"{'=' * 80}")

        if canceled > 0:
            print(
                "\n✅ Cleanup complete! Your account should now have full buying power available."
            )
            print("Run the loop again to see normal operation without duplicate orders.")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
