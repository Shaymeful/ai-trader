#!/usr/bin/env python3
"""Close all positions in the paper account."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.app.config import load_config
from src.broker.base import AlpacaBroker
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


def main():
    config = load_config()

    broker = AlpacaBroker(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        trading_base_url=config.alpaca_trading_base_url,
    )

    print("=" * 80)
    print("CLOSING ALL POSITIONS")
    print("=" * 80)

    try:
        positions = broker.client.get_all_positions()

        if not positions:
            print("\n[OK] No positions to close")
            return

        print(f"\nFound {len(positions)} positions to close:")
        for pos in positions:
            print(
                f"  {pos.symbol}: {float(pos.qty)} shares @ ${float(pos.current_price):.2f} = ${float(pos.market_value):.2f}"
            )

        print("\nClosing all positions...")

        closed = 0
        failed = 0

        for pos in positions:
            symbol = pos.symbol
            qty = abs(float(pos.qty))
            side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY

            try:
                # Close position with market order
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
                order = broker.client.submit_order(order_request)
                print(f"  [OK] Closed {symbol}: {qty} shares (order {order.id})")
                closed += 1
            except Exception as e:
                print(f"  [ERROR] Failed to close {symbol}: {e}")
                failed += 1

        print("\n" + "=" * 80)
        print(f"Closed: {closed}")
        print(f"Failed: {failed}")
        print("=" * 80)

        if closed > 0:
            print("\nWait a few seconds for orders to fill, then check account status:")
            print("  python check_account_status.py")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
