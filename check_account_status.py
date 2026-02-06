#!/usr/bin/env python3
"""Check account status including positions and buying power."""

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
    print("ACCOUNT STATUS")
    print("=" * 80)

    # Get account info
    try:
        account = broker.client.get_account()
        print(f"\nAccount Equity: ${float(account.equity):,.2f}")
        print(f"Buying Power: ${float(account.buying_power):,.2f}")
        print(f"Cash: ${float(account.cash):,.2f}")
        print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"Long Market Value: ${float(account.long_market_value):,.2f}")
        print(f"Short Market Value: ${float(account.short_market_value):,.2f}")
    except Exception as e:
        print(f"ERROR: Failed to get account: {e}")
        return

    # Get positions
    print("\n" + "=" * 80)
    print("POSITIONS")
    print("=" * 80)

    try:
        positions = broker.get_positions()
        if not positions:
            print("\nNo positions")
        else:
            print(f"\nFound {len(positions)} positions:")
            print(f"\n{'Symbol':<8} {'Qty':>10} {'Avg Price':>12} {'Current':>12} {'P&L':>12}")
            print("-" * 80)

            for symbol, (qty, avg_price) in positions.items():
                try:
                    pos = broker.client.get_open_position(symbol)
                    current_price = float(pos.current_price)
                    market_value = float(pos.market_value)
                    unrealized_pl = float(pos.unrealized_pl)
                    print(f"{symbol:<8} {qty:>10} ${float(avg_price):>11.2f} ${current_price:>11.2f} ${unrealized_pl:>11.2f}")
                except:
                    print(f"{symbol:<8} {qty:>10} ${float(avg_price):>11.2f} {'N/A':>12} {'N/A':>12}")
    except Exception as e:
        print(f"ERROR: Failed to get positions: {e}")

    # Get open orders
    print("\n" + "=" * 80)
    print("OPEN ORDERS")
    print("=" * 80)

    try:
        orders = broker.get_open_orders_detailed()
        if not orders:
            print("\nNo open orders")
        else:
            print(f"\nFound {len(orders)} open orders:")
            for order in orders[:20]:
                print(f"  {order['symbol']} {order['side']} {order['qty']} @ ${order.get('limit_price', 'market')}")
    except Exception as e:
        print(f"ERROR: Failed to get orders: {e}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
