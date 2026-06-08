#!/usr/bin/env python3
"""
Emergency cleanup utility: Cancel ALL open orders on Alpaca paper account.

Usage:
    python tools/cancel_all_paper_orders.py [--confirm]

This script will:
1. Connect to Alpaca paper trading account
2. Fetch all open orders
3. Cancel each order individually
4. Report summary of canceled orders

Safety features:
- Requires --confirm flag to actually cancel (dry-run by default)
- Only works with paper trading account (ALPACA_PAPER_KEY_ID/SECRET_KEY)
- Logs all cancellations for audit trail
"""

import argparse
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
except ImportError:
    print("python-dotenv not installed, using system environment variables only")

from src.broker.base import AlpacaBroker


def main():
    parser = argparse.ArgumentParser(description="Cancel all open orders on Alpaca paper account")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually cancel orders (default: dry-run preview only)",
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Check environment variables
    api_key = os.getenv("ALPACA_PAPER_KEY_ID")
    api_secret = os.getenv("ALPACA_PAPER_SECRET_KEY")

    if not api_key or not api_secret:
        logger.error(
            "Missing environment variables: ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY"
        )
        logger.error("Please set these variables before running this script")
        sys.exit(1)

    # Initialize broker
    logger.info("Connecting to Alpaca paper trading account...")
    trading_base_url = "https://paper-api.alpaca.markets"
    broker = AlpacaBroker(
        api_key=api_key,
        secret_key=api_secret,
        trading_base_url=trading_base_url,
    )

    # Fetch all open orders
    logger.info("Fetching open orders...")
    try:
        open_orders = broker.get_open_orders_detailed()
    except Exception as e:
        logger.error(f"Failed to fetch open orders: {e}")
        sys.exit(1)

    if not open_orders:
        logger.info("No open orders found. Nothing to cancel.")
        return

    # Calculate statistics
    total_orders = len(open_orders)
    total_reserved = Decimal("0")
    orders_by_symbol = {}

    for order in open_orders:
        symbol = order["symbol"]
        if symbol not in orders_by_symbol:
            orders_by_symbol[symbol] = {"count": 0, "buy": 0, "sell": 0, "notional": Decimal("0")}

        orders_by_symbol[symbol]["count"] += 1
        if order["side"] == "BUY":
            orders_by_symbol[symbol]["buy"] += 1
        else:
            orders_by_symbol[symbol]["sell"] += 1

        if order["limit_price"]:
            notional = Decimal(str(order["qty"])) * order["limit_price"]
            orders_by_symbol[symbol]["notional"] += notional
            if order["side"] == "BUY":
                total_reserved += notional

    # Print summary
    print("\n" + "=" * 80)
    print("OPEN ORDERS SUMMARY")
    print("=" * 80)
    print(f"Total open orders: {total_orders}")
    print(f"Total reserved buying power (BUY orders): ${total_reserved:,.2f}")
    print()
    print(f"{'Symbol':<8} {'Total':>6} {'BUY':>5} {'SELL':>5} {'Reserved $':>12}")
    print("-" * 80)

    for symbol, stats in sorted(orders_by_symbol.items()):
        print(
            f"{symbol:<8} {stats['count']:>6} {stats['buy']:>5} {stats['sell']:>5} "
            f"${stats['notional']:>11,.2f}"
        )

    print("=" * 80)
    print()

    # Confirm or dry-run
    if not args.confirm:
        print("DRY-RUN MODE (use --confirm to actually cancel orders)")
        print()
        print("To cancel all these orders, run:")
        print("  python tools/cancel_all_paper_orders.py --confirm")
        return

    # Confirm with user
    print("WARNING: This will cancel ALL open orders!")
    print()
    response = input("Type 'YES' to confirm cancellation: ")
    if response != "YES":
        print("Cancellation aborted.")
        return

    # Cancel all orders
    print()
    print("Canceling orders...")
    print()

    canceled_count = 0
    failed_count = 0

    for order in open_orders:
        order_id = order["order_id"]
        symbol = order["symbol"]
        side = order["side"]
        qty = order["qty"]

        try:
            broker.client.cancel_order_by_id(order_id)
            logger.info(f"Canceled: {symbol} {side} {qty} (order_id: {order_id})")
            canceled_count += 1
        except Exception as e:
            logger.error(f"Failed to cancel {symbol} {side} {qty} (order_id: {order_id}): {e}")
            failed_count += 1

    # Final summary
    print()
    print("=" * 80)
    print("CANCELLATION SUMMARY")
    print("=" * 80)
    print(f"Successfully canceled: {canceled_count}")
    print(f"Failed to cancel: {failed_count}")
    print(f"Total orders processed: {total_orders}")
    print("=" * 80)

    if canceled_count > 0:
        logger.info(f"Successfully canceled {canceled_count} orders")
        logger.info(f"Freed up approximately ${total_reserved:,.2f} in reserved buying power")


if __name__ == "__main__":
    main()
