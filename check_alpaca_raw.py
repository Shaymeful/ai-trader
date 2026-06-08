"""Check Alpaca positions using raw API."""

from src.app.config import load_config_with_yaml, get_alpaca_credentials
from alpaca.trading.client import TradingClient

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials("paper")

client = TradingClient(api_key, secret_key, paper=True)

print("\n" + "=" * 80)
print("RAW ALPACA API - POSITIONS")
print("=" * 80)

try:
    positions = client.get_all_positions()
    print(f"Total positions: {len(positions)}")

    for pos in positions:
        print(f"\n{pos.symbol}:")
        print(f"  Qty: {pos.qty}")
        print(f"  Avg Entry: ${pos.avg_entry_price}")
        print(f"  Current: ${pos.current_price}")
        print(f"  Market Value: ${pos.market_value}")
        print(f"  Unrealized P&L: ${pos.unrealized_pl}")
        print(f"  Unrealized P&L %: {pos.unrealized_plpc}%")
except Exception as e:
    print(f"Error: {e}")

print("=" * 80)
print()
