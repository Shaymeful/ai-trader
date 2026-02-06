"""Check current positions and exposure."""
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker
from decimal import Decimal

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials('paper')
broker = AlpacaBroker(api_key, secret_key, trading_base_url)

# Get positions as dict[str, tuple[int, Decimal]]
positions = broker.get_positions()

# Also get raw positions for current price
raw_positions = broker.client.get_all_positions()
current_prices = {pos.symbol: Decimal(str(pos.current_price)) for pos in raw_positions}

print("\n" + "="*80)
print("CURRENT POSITIONS")
print("="*80)
print(f"Total positions: {len(positions)}")

total_market_value = Decimal("0")
total_cost_basis = Decimal("0")

for symbol, (qty, avg_entry) in positions.items():
    current_price = current_prices.get(symbol, avg_entry)
    cost_basis = Decimal(qty) * avg_entry
    market_value = Decimal(qty) * current_price

    total_market_value += market_value
    total_cost_basis += cost_basis

    pnl = market_value - cost_basis
    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else Decimal("0")

    print(f"\n{symbol}:")
    print(f"  Qty: {qty}")
    print(f"  Avg Entry: ${avg_entry:.2f}")
    print(f"  Current: ${current_price:.2f}")
    print(f"  Cost Basis: ${cost_basis:,.2f}")
    print(f"  Market Value: ${market_value:,.2f}")
    print(f"  P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")

print("\n" + "="*80)
print("PORTFOLIO SUMMARY")
print("="*80)
print(f"Total Cost Basis: ${total_cost_basis:,.2f}")
print(f"Total Market Value: ${total_market_value:,.2f}")
print(f"Total P&L: ${total_market_value - total_cost_basis:,.2f}")
print(f"Capital Cap: ${config.max_positions_notional:,.2f}")
print(f"Over Cap: ${total_cost_basis - config.max_positions_notional:,.2f}")
print(f"Utilization: {(total_cost_basis / config.max_positions_notional * 100):.1f}%")
print("="*80)
print()
