#!/usr/bin/env python3
"""Check positions using native Alpaca API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.app.config import load_config
from src.broker.base import AlpacaBroker

def main():
    config = load_config()

    broker = AlpacaBroker(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        trading_base_url=config.alpaca_trading_base_url,
    )

    print("=" * 80)
    print("POSITIONS (Native Alpaca API)")
    print("=" * 80)

    try:
        # Use native Alpaca client directly
        positions = broker.client.get_all_positions()

        if not positions:
            print("\nNo positions found via native API")
        else:
            print(f"\nFound {len(positions)} positions via native API:")
            print(f"\n{'Symbol':<8} {'Qty':>10} {'Side':>6} {'Avg Price':>12} {'Current':>12} {'Market Val':>12} {'P&L':>12}")
            print("-" * 100)

            total_value = 0
            for pos in positions:
                symbol = pos.symbol
                qty = float(pos.qty)
                side = pos.side
                avg_price = float(pos.avg_entry_price)
                current_price = float(pos.current_price)
                market_value = float(pos.market_value)
                unrealized_pl = float(pos.unrealized_pl)

                total_value += abs(market_value)

                print(f"{symbol:<8} {qty:>10.2f} {side:>6} ${avg_price:>11.2f} ${current_price:>11.2f} ${market_value:>11.2f} ${unrealized_pl:>11.2f}")

            print("-" * 100)
            print(f"{'TOTAL':<8} {'':<10} {'':<6} {'':<12} {'':<12} ${total_value:>11.2f}")

    except Exception as e:
        print(f"ERROR: Failed to get positions: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
