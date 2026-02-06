"""Create manual exit order for TLN."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.broker.base import AlpacaBroker, OrderSide, OrderType
from src.app.config import load_config_with_yaml

config = load_config_with_yaml()
broker = AlpacaBroker(
    api_key=config.alpaca_api_key,
    secret_key=config.alpaca_secret_key,
    trading_base_url=config.alpaca_trading_base_url,
)

print("Creating exit order for TLN (energy sector - disabled)...")
print("=" * 60)

# Get current position
positions = broker.get_positions()
if 'TLN' not in positions:
    print("[ERROR] No TLN position found")
    sys.exit(1)

qty_info = positions['TLN']
qty = qty_info[0] if isinstance(qty_info, tuple) else qty_info

print(f"Current TLN position: {qty} shares")
print(f"Creating market sell order...")

try:
    # Generate unique client order ID
    client_order_id = f"manual_exit_TLN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    order = broker.submit_order(
        symbol='TLN',
        side=OrderSide.SELL,
        quantity=abs(int(qty)),
        client_order_id=client_order_id,
        order_type=OrderType.MARKET,
    )
    
    print(f"\n[SUCCESS] Exit order created!")
    print(f"Order ID: {order.id if hasattr(order, 'id') else 'N/A'}")
    print(f"Client Order ID: {client_order_id}")
    print(f"Symbol: TLN")
    print(f"Qty: {abs(int(qty))}")
    print(f"Side: SELL")
    print(f"Type: MARKET")
    print(f"Status: {order.status if hasattr(order, 'status') else 'N/A'}")
    print(f"\nReason: Disabled energy sector exit (manual)")
    
except Exception as e:
    print(f"[ERROR] Failed to create order: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
