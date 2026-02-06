"""Check open orders."""
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials('paper')
broker = AlpacaBroker(api_key, secret_key, trading_base_url)

print("\n" + "="*80)
print("OPEN ORDERS")
print("="*80)

from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
orders = broker.client.get_orders(filter=request)
print(f"Total open orders: {len(orders)}")

for order in orders:
    print(f"\n{order.symbol}:")
    print(f"  Order ID: {order.id}")
    print(f"  Side: {order.side}")
    print(f"  Qty: {order.qty}")
    print(f"  Type: {order.type}")
    print(f"  Status: {order.status}")
    print(f"  Submitted: {order.submitted_at}")

print("="*80)
print()
