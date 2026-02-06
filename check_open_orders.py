"""Check open orders in Alpaca paper account."""

from src.broker import AlpacaBroker
from src.app.config import get_alpaca_credentials

# Get credentials
api_key, secret_key, trading_base_url, data_base_url = get_alpaca_credentials("paper")

# Initialize broker
broker = AlpacaBroker(api_key, secret_key, trading_base_url)

# Get open orders
print("Fetching open orders...")
try:
    open_orders = broker.get_open_orders_detailed()

    if not open_orders:
        print("\nNo open orders found!")
    else:
        print(f"\nFound {len(open_orders)} open orders:\n")
        print(f"{'Symbol':<8} {'Side':<6} {'Qty':<10} {'Limit Price':<12} {'Order ID':<40}")
        print("-" * 80)

        # Group by symbol
        from collections import defaultdict
        by_symbol = defaultdict(list)
        for order in open_orders:
            by_symbol[order['symbol']].append(order)

        total_reserved = 0
        for symbol, orders in sorted(by_symbol.items()):
            for order in orders:
                qty = order['qty']
                limit_price = order['limit_price']
                notional = float(qty) * float(limit_price) if limit_price else 0
                total_reserved += notional

                print(f"{symbol:<8} {order['side']:<6} {qty:<10.2f} ${float(limit_price):<11.2f} {order['order_id']}")

            if len(orders) > 1:
                print(f"  ⚠️  WARNING: {len(orders)} duplicate orders for {symbol}!")
            print()

        print(f"\nTotal reserved notional (BUY orders): ${total_reserved:,.2f}")

        # Summary
        print("\n" + "="*80)
        print("DUPLICATES DETECTED:")
        for symbol, orders in sorted(by_symbol.items()):
            if len(orders) > 1:
                print(f"  {symbol}: {len(orders)} open {orders[0]['side']} orders")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
