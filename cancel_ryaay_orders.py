"""Cancel all pending RYAAY orders."""
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials('paper')
broker = AlpacaBroker(api_key, secret_key, trading_base_url)

print("Fetching open orders...")
orders = broker.list_open_orders_detailed()

ryaay_orders = [o for o in orders if o.symbol == "RYAAY"]
print(f"\nFound {len(ryaay_orders)} open RYAAY orders")

if ryaay_orders:
    print("\nRYAAY Orders:")
    for order in ryaay_orders:
        print(f"  {order.id}: {order.side.name} {order.quantity} @ {order.price if order.price else 'market'} - {order.status.name}")

    confirm = input("\nCancel all RYAAY orders? (yes/no): ")
    if confirm.lower() == "yes":
        for order in ryaay_orders:
            try:
                broker.cancel_order(order.id)
                print(f"  Cancelled {order.id}")
            except Exception as e:
                print(f"  Failed to cancel {order.id}: {e}")
        print("\nDone.")
    else:
        print("Cancelled.")
else:
    print("No RYAAY orders to cancel.")
