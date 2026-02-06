"""Check current positions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.broker.base import AlpacaBroker
from src.app.config import load_config_with_yaml

config = load_config_with_yaml()
broker = AlpacaBroker(
    api_key=config.alpaca_api_key,
    secret_key=config.alpaca_secret_key,
    trading_base_url=config.alpaca_trading_base_url,
)

print("Current Positions:")
print("=" * 50)

positions = broker.get_positions()
if positions:
    for symbol, qty in positions.items():
        print(f"  {symbol}: {qty} shares")
else:
    print("  No positions")

print()

# Check what energy sector tickers are
try:
    from src.app.universe_registry import UniverseRegistry
    registry = UniverseRegistry()

    if "energy" in registry.sectors:
        energy_sector = registry.sectors["energy"]
        print(f"Energy Sector Tickers: {energy_sector.symbols}")
        print(f"Energy Sector Enabled: {energy_sector.enabled}")
        print()

        # Check for overlaps
        energy_positions = [s for s in positions.keys() if s in energy_sector.symbols]
        if energy_positions:
            print(f"Energy sector positions to exit: {energy_positions}")
        else:
            print("No energy sector positions found")
    else:
        print("Energy sector not found in registry")

except Exception as e:
    print(f"Error checking energy sector: {e}")
