#!/usr/bin/env python3
"""Quick script to cancel all paper orders using the same config as runner."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.app.config import load_config
from src.broker.base import AlpacaBroker

def main():
    print("Loading configuration...")
    config = load_config()

    if not config.alpaca_api_key or not config.alpaca_secret_key:
        print("ERROR: No Alpaca credentials found in config")
        print("Check .env file has ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY")
        sys.exit(1)

    print(f"Connecting to {config.alpaca_trading_base_url}...")
    broker = AlpacaBroker(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        trading_base_url=config.alpaca_trading_base_url,
    )

    print("Fetching open orders...")
    try:
        open_orders = broker.get_open_orders_detailed()
    except Exception as e:
        print(f"ERROR: Failed to fetch orders: {e}")
        sys.exit(1)

    if not open_orders:
        print("[OK] No open orders found")
        return

    print(f"\nFound {len(open_orders)} open orders:")
    for order in open_orders[:10]:  # Show first 10
        print(f"  {order['symbol']} {order['side']} {order['qty']} @ ${order.get('limit_price', 'market')}")
    if len(open_orders) > 10:
        print(f"  ... and {len(open_orders) - 10} more")

    # Cancel all orders
    print(f"\nCanceling {len(open_orders)} orders...")
    canceled = 0
    failed = 0

    for order in open_orders:
        try:
            broker.client.cancel_order_by_id(order["order_id"])
            canceled += 1
            if canceled % 10 == 0:
                print(f"  Canceled {canceled}/{len(open_orders)}...")
        except Exception as e:
            print(f"  Failed to cancel {order['symbol']}: {e}")
            failed += 1

    print(f"\n[OK] Canceled {canceled} orders")
    if failed > 0:
        print(f"[WARN] Failed to cancel {failed} orders")

if __name__ == "__main__":
    main()
